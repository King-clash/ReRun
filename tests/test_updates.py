"""Updates (rerun/updates.py + tools/publish_update.py) against a local web server, with a
throwaway signing key - nothing touches the project's templates or the real key."""
from __future__ import annotations

import functools
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun import ed25519, updates  # noqa: E402
from rerun.vision import TemplateStore  # noqa: E402
from tools import publish_update  # noqa: E402

SECRET = bytes(range(32))
PUBLIC = ed25519.public_key(SECRET)
updates.PUBLIC_KEY = PUBLIC          # this suite trusts its own test key only


class Site:
    """A temp publisher source, update site and install folder, plus an http server."""

    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rerun_upd_"))
        self.src, self.site, self.inst = self.tmp / "src", self.tmp / "site", self.tmp / "inst"
        for d in (self.src / "templates", self.src / "routines", self.inst / "templates",
                  self.inst / "routines"):
            d.mkdir(parents=True)
        handler = functools.partial(_Quiet, directory=str(self.site))
        self.site.mkdir()
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.config = {"updates": {"url": f"http://127.0.0.1:{self.httpd.server_port}",
                                   "channel": "stable", "content_in_source": True}}

    def write(self, base: Path, rel: str, data: bytes | str):
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data.encode() if isinstance(data, str) else data)

    def publish(self, **kw):
        return publish_update.publish(self.site, "stable", SECRET, src=self.src, **kw)

    def baseline(self, files: dict[str, bytes]):
        """The install folder as a build shipped it."""
        for rel, data in files.items():
            self.write(self.inst, rel, data)
        base = {rel: updates.sha256_file(self.inst / rel) for rel in files}
        (self.inst / updates.BASELINE_FILE).write_text(json.dumps({"files": base}))

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def with_site(fn):
    @functools.wraps(fn)
    def run():
        s = Site()
        try:
            fn(s)
        finally:
            s.close()
    return run


# ---------------------------------------------------------------- pure functions
def test_signature_roundtrip_and_tampering():
    raw = json.dumps({"format": 1, "serial": 5, "content": {"files": {}}}).encode()
    sig = updates.sign_manifest(raw, SECRET)
    assert updates.parse_manifest(raw, sig)["serial"] == 5
    for bad_raw, bad_sig in ((raw.replace(b"5", b"6"), sig), (raw, sig[:-4] + "AAA="),
                             (raw, "not base64!"), (raw, "")):
        try:
            updates.parse_manifest(bad_raw, bad_sig)
        except updates.UpdateError:
            continue
        raise AssertionError("tampered manifest accepted")
    other = updates.sign_manifest(raw, bytes(32))
    try:
        updates.parse_manifest(raw, other)
        raise AssertionError("manifest signed by another key accepted")
    except updates.UpdateError:
        pass


def test_versions():
    assert updates.is_newer("1.0.1", "1.0.0") and updates.is_newer("1.10", "1.9.9")
    assert not updates.is_newer("1.0.0", "1.0.0") and not updates.is_newer("v0.9", "1.0")


def test_unsafe_paths_refused():
    for rel in ("../x.png", "templates/../../x", "C:/x.png", "other/x.png", "templates/_meta.json",
                "templates", "templates//a.png"):
        try:
            updates._safe_rel(rel)
            raise AssertionError(f"accepted {rel}")
        except updates.UpdateError:
            pass
    assert updates._safe_rel("templates\\a.png") == "templates/a.png"


def test_http_refused_except_localhost():
    try:
        updates.fetch("http://example.com/manifest.json")
        raise AssertionError("plain http accepted")
    except updates.UpdateError:
        pass


def test_helper_script():
    bat = updates.helper_script(Path(r"C:\R\Rerun.exe"), Path(r"C:\R\Rerun.update.exe"),
                                Path(r"C:\R\Rerun.old.exe"), [11, 22])
    assert 'PID eq 11' in bat and 'PID eq 22' in bat and 'start "" "C:\\R\\Rerun.exe"' in bat
    assert 'move /Y "C:\\R\\Rerun.update.exe" "C:\\R\\Rerun.exe"' in bat
    quiet = updates.helper_script(Path("a.exe"), Path("b.exe"), Path("c.exe"), [1], restart=False)
    assert "start " not in quiet


def test_template_store_reload_bumps_generation():
    with tempfile.TemporaryDirectory() as d:
        st = TemplateStore(d)
        (Path(d) / "_meta.json").write_text(json.dumps({"a": {"threshold": 0.9}}))
        g = st.generation("a")
        st.reload()
        assert st.generation("a") == g + 1 and st.threshold("a") == 0.9


# ---------------------------------------------------------------- content end to end
@with_site
def test_content_update_keeps_your_files(s: Site):
    # the build shipped a(v1), b(v1), r(v1); you re-captured b and tuned a's threshold
    s.baseline({"templates/a.png": b"a1", "templates/b.png": b"b1", "routines/r.yaml": "v1"})
    s.write(s.inst, "templates/b.png", b"b-yours")
    (s.inst / "templates/_meta.json").write_text(json.dumps({
        "a": {"w": 1, "threshold": 0.77}, "b": {"w": 1, "x": 5}, "mine": {"x": 1}}))
    # the release: a(v2), b(v2), new c, r(v2)
    for rel, data in {"templates/a.png": b"a2", "templates/b.png": b"b2", "templates/c.png": b"c1",
                      "routines/r.yaml": "v2"}.items():
        s.write(s.src, rel, data)
    (s.src / "templates/_meta.json").write_text(json.dumps({
        "a": {"w": 2}, "b": {"w": 2}, "c": {"w": 3, "threshold": 0.8}}))
    m = s.publish(content_version="2026.11.14")

    res = updates.check(s.inst, s.config)
    assert not res.error, res.error
    assert sorted(res.plan.install) == ["routines/r.yaml", "templates/a.png", "templates/c.png"]
    assert res.plan.kept == ["templates/b.png"] and res.app is None
    updates.stage_content(s.inst, s.config, res.plan)
    assert (s.inst / "templates/a.png").read_bytes() == b"a1"     # nothing moved yet
    msg = updates.commit_staged(s.inst)
    assert "3 file(s) updated" in msg and "1 of yours kept" in msg, msg

    assert (s.inst / "templates/a.png").read_bytes() == b"a2"
    assert (s.inst / "templates/b.png").read_bytes() == b"b-yours"
    assert (s.inst / "templates/c.png").read_bytes() == b"c1"
    assert (s.inst / "routines/r.yaml").read_text() == "v2"
    meta = json.loads((s.inst / "templates/_meta.json").read_text())
    assert meta["a"] == {"w": 2, "threshold": 0.77}       # your threshold kept
    assert meta["b"] == {"w": 1, "x": 5}                   # your template, your meta
    assert meta["c"]["threshold"] == 0.8 and meta["mine"] == {"x": 1}
    state = updates.load_state(s.inst)
    assert state["serial"] == m["serial"] and state["content_version"] == "2026.11.14"
    assert not (s.inst / updates.STAGING_DIR).exists()

    again = updates.check(s.inst, s.config)
    assert not again.error and again.plan.empty, again.plan
    assert updates.commit_staged(s.inst) == ""


@with_site
def test_removed_files_only_when_untouched(s: Site):
    s.baseline({"templates/old.png": b"o1", "templates/old2.png": b"p1"})
    s.write(s.inst, "templates/old2.png", b"p-yours")
    s.write(s.src, "templates/new.png", b"n1")
    s.publish(remove=["templates/old.png", "templates/old2.png"])
    res = updates.check(s.inst, s.config)
    assert res.plan.remove == ["templates/old.png"], res.plan
    updates.stage_content(s.inst, s.config, res.plan)
    updates.commit_staged(s.inst)
    assert not (s.inst / "templates/old.png").exists()
    assert (s.inst / "templates/old2.png").read_bytes() == b"p-yours"


@with_site
def test_file_you_edit_after_download_is_kept(s: Site):
    s.baseline({"templates/a.png": b"a1"})
    s.write(s.src, "templates/a.png", b"a2")
    s.publish()
    res = updates.check(s.inst, s.config)
    updates.stage_content(s.inst, s.config, res.plan)
    s.write(s.inst, "templates/a.png", b"recaptured")      # while it waited for scripts to stop
    assert "of yours kept" in updates.commit_staged(s.inst)
    assert (s.inst / "templates/a.png").read_bytes() == b"recaptured"


@with_site
def test_older_release_and_bad_files_refused(s: Site):
    s.write(s.src, "templates/a.png", b"a1")
    m = s.publish()
    updates._write_json(s.inst / updates.STATE_FILE, {"serial": m["serial"] + 10, "files": {}})
    res = updates.check(s.inst, s.config)
    assert "older release" in res.error, res.error
    # a host serving a different file than the manifest says
    (s.inst / updates.STATE_FILE).unlink()
    sha = m["content"]["files"]["templates/a.png"]["sha256"]
    (s.site / "stable/content" / sha).write_bytes(b"evil")
    res = updates.check(s.inst, s.config)
    try:
        updates.stage_content(s.inst, s.config, res.plan)
        raise AssertionError("bad download accepted")
    except updates.UpdateError:
        pass
    assert not (s.inst / "templates/a.png").exists()


@with_site
def test_no_host_or_missing_manifest_is_reported(s: Site):
    assert updates.check(s.inst, {"updates": {"url": ""}}).error
    res = updates.check(s.inst, s.config)            # nothing published yet: 404
    assert "404" in res.error, res.error


# ---------------------------------------------------------------- app update
@with_site
def test_app_update_download_and_check(s: Site):
    exe = s.tmp / "Rerun.exe"
    exe.write_bytes(b"MZ new rerun")
    s.write(s.src, "templates/a.png", b"a1")
    m = s.publish(exe=exe, notes="Faster")
    assert m["app"]["version"] == publish_update.__version__
    real = updates.__version__
    try:
        updates.__version__ = "0.0.1"   # pretend this Rerun is older
        res = updates.check(s.inst, s.config)
        assert res.app and res.app["notes"] == "Faster"
        got = updates.download_app(s.inst, s.config, res.app)
        assert got.read_bytes() == b"MZ new rerun"
        bad = dict(res.app, sha256="0" * 64)
        try:
            updates.download_app(s.inst, s.config, bad)
            raise AssertionError("exe with wrong hash accepted")
        except updates.UpdateError:
            pass
    finally:
        updates.__version__ = real
    assert updates.app_update(m) is None             # same version: nothing offered
    # a template-only release keeps the app entry
    m2 = s.publish()
    assert m2["app"] == m["app"] and m2["serial"] > m["serial"]


if __name__ == "__main__":
    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
    failed = 0
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            import traceback
            failed += 1
            print(f"FAIL {t.__name__}: {e!r}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
