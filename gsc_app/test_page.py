"""Tests for the GS Companion app:  py gsc_app/test_page.py

The page is tested with a temporary settings file and a fake Rerun unit scan, so your
own settings and Rerun data are never touched. The last test applies rerun_tab.patch to
a *temporary copy* of Rerun and starts the real App there; rerun/gui.py is never changed."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rerun import ios  # noqa: E402
from gsc_app.page import DAYS, LEVELS, GSCompanionPage, level_icon_name, today_name  # noqa: E402
from gsc_app.store import Settings  # noqa: E402


def make_page(settings: Path | None = None, rerun_dir: Path | None = None):
    tmp = Path(tempfile.mkdtemp(prefix="gsc_t_"))
    win = tk.Tk()
    win.geometry("1300x850")
    ios.init(win, "light")
    opened, flashes = [], []
    page = GSCompanionPage(win, ROOT, flash=lambda t, k="info": flashes.append(t),
                           open_url=opened.append,
                           settings_path=settings or tmp / "settings.json",
                           rerun_dir=rerun_dir or tmp)
    page.pack(fill="both", expand=True)
    errors = []
    win.report_callback_exception = lambda *a: errors.append(a)
    win.update()
    win.tmp = tmp
    return win, page, opened, errors


def close(win):
    win.destroy()
    shutil.rmtree(win.tmp, ignore_errors=True)


def detail_text(page) -> str:
    return page.detail.get("1.0", "end")


def select_where(page, pred) -> dict:
    for iid, r in page._rows.items():
        if r.get("rec") and pred(r["rec"]):
            page.tree.selection_set(iid)
            page.tree.event_generate("<<TreeviewSelect>>")
            page.update()
            return r["rec"]
    raise AssertionError("no row matched")


def test_palace_view():
    win, page, opened, errors = make_page()
    try:
        assert page.view.get() == "Palace"
        assert page.day.get() == f"Today ({today_name()})"
        today = {s["slug"] for s in page.gsc.palace_today()}
        assert {r["rec"]["slug"] for r in page._rows.values()} == today
        page.day.set("Friday")
        page.refresh()
        names = {r["rec"]["name"] for r in page._rows.values()}
        assert "Temple of Heavenly Light" in names and "Shrine of Caliginosity" in names
        page.diff.set("NOVA")
        page._filter_changed()
        assert all(r["rec"]["difficulty"] == "NOVA" for r in page._rows.values())
        page.day.set("Sunday")
        page.refresh()
        assert [r["rec"]["name"] for r in page._rows.values()] == ["Shrine of Sagacity"]
        s = select_where(page, lambda s: True)
        txt = detail_text(page)
        assert s["boss"] in txt and "CRESTS THAT DROP HERE" in txt
        page.open_current()
        assert opened == [s["url"]], opened
        assert not errors, errors
    finally:
        close(win)


def test_crests_view_links_and_back():
    win, page, opened, errors = make_page()
    try:
        page.show_view("Crests")
        assert len(page._rows) == len(page.gsc.crests)
        page.q["Crests"].set("hp up")
        assert {r["rec"]["name"] for r in page._rows.values()} >= {"HP UP"}
        c = select_where(page, lambda c: c["name"] == "HP UP")
        txt = detail_text(page)
        assert "MAX HP 200 UP" in txt and "Lv5+" in txt and "WHERE IT DROPS" in txt
        assert "Shrine of Caliginosity" in txt
        links = [t for t in page.detail.tag_names() if t[:1] == "L" and t[1:].isdigit()]
        assert links and all(page.tk.call(str(page.detail), "tag", "bind", t, "<Button-1>")
                             for t in links), "links not bound"
        stage = sorted(page.gsc.stages_dropping(c["name"]),
                       key=lambda s: ["NOVA", "EXTREME", "PRO"].index(s["difficulty"]))[0]
        page.go("Palace", stage)
        page.update()
        assert page.view.get() == "Palace"
        sel = page.tree.selection()
        assert sel and page._rows[sel[0]]["rec"]["name"] == "Shrine of Caliginosity"
        # Back returns to the crest.
        page.back()
        page.update()
        assert page.view.get() == "Crests" and "MAX HP 200 UP" in detail_text(page)
        page.back()  # nothing left: just a message, no error
        page.go("Crests", next(x for x in page.gsc.crests if x["kind"] == "event"))
        page.update()
        assert "event" in detail_text(page).lower()
        page.kind.set("Unique")
        page._filter_changed()
        assert all(r["rec"]["kind"] == "unique" for r in page._rows.values())
        assert not errors, errors
    finally:
        close(win)


def test_units_stars_and_rerun_scan():
    tmp = Path(tempfile.mkdtemp(prefix="gsc_rr_"))
    (tmp / "units").mkdir()
    (tmp / "units" / "roster.json").write_text(json.dumps({
        "Ragna": {"fields": {"element": {"value": "Fire"}}},
        "Mira": {"fields": {"element": {"value": "Fire"}}},      # -> "Mira (Fire)"
        "Unreadable Nam3": {"fields": {}}}), encoding="utf-8")
    win, page, opened, errors = make_page(rerun_dir=tmp)
    try:
        assert page.my.scanned() == {"Ragna", "Mira (Fire)"}, page.my.scanned()
        page.show_view("Units")
        assert len(page._rows) == len(page.gsc.units)
        page.q["Units"].set("clyde")
        u = select_where(page, lambda u: u["name"] == "Clyde")
        txt = detail_text(page)
        assert "RECOMMENDED CRESTS" in txt and "ATK UP" in txt and "FARM TODAY" in txt
        page.toggle_star(u)
        assert page.my.is_starred("Clyde")
        row = next(r for r in page._rows.values() if r["rec"]["name"] == "Clyde")
        assert row["values"]["mine"] == "★"
        page.q["Units"].set("")
        page.unit_filter.set("My units")
        page._filter_changed()
        assert {r["rec"]["name"] for r in page._rows.values()} == {"Clyde", "Ragna", "Mira (Fire)"}
        page.unit_filter.set("Rerun scan")
        page._filter_changed()
        assert {r["rec"]["name"] for r in page._rows.values()} == {"Ragna", "Mira (Fire)"}
        # Stars and filter were saved.
        s = Settings(page.s.path)
        assert s["starred"] == ["Clyde"] and s["unit_filter"] == "Rerun scan"
        page.open_current()
        assert opened == [u["url"]]
        # Palace/crest lists show how many of your units want them.
        page.show_view("Crests")
        atk = next(r for r in page._rows.values() if r["rec"]["name"] == "ATK UP")
        assert atk["values"]["mine"].startswith("★"), atk["values"]
        assert not errors, errors
    finally:
        close(win)
        shutil.rmtree(tmp, ignore_errors=True)


def test_week_view():
    win, page, opened, errors = make_page()
    try:
        page.show_view("Week")
        page.update()
        assert page.week_sf.winfo_ismapped() and not page.tree.winfo_ismapped()
        slugs = set(page._week_cells)
        assert slugs == {s["slug"] for s in page.gsc.stages}, len(slugs)
        s = page.gsc.stages[0]
        page._week_pick(s)
        assert s["name"] in detail_text(page)
        page.size.set("L")
        page._size_changed()
        page.update()
        assert s["name"] in detail_text(page)  # detail kept across a size change
        assert not errors, errors
    finally:
        close(win)


def test_planner():
    win, page, opened, errors = make_page()
    try:
        page.show_view("Planner")
        assert not page._rows and "Farm planner" in detail_text(page)
        for name in ("Clyde", "Imperial Form Illya"):
            page.toggle_plan(page.gsc.match_unit(name))
        page.show_view("Planner")
        p = page.plan()
        assert set(p["units"]) == {"Clyde", "Imperial Form Illya"}
        # Every needed crest that drops in the palace shows up under its days.
        groups = [r for r in page._rows.values() if r["kind"] == "group"]
        assert groups, "no day groups"
        crests = {r["rec"]["name"] for r in page._rows.values() if r["kind"] == "crest" and r["rec"]}
        assert {"ATK UP", "Arts gauge UP"} <= crests, crests
        child = select_where(page, lambda c: c.get("name") == "ATK UP")
        assert "WHERE IT DROPS" in detail_text(page)
        gid = next(i for i, r in page._rows.items() if r["kind"] == "group")
        page.tree.selection_set(gid)
        page.tree.event_generate("<<TreeviewSelect>>")
        page.update()
        assert "UNITS IN THE PLAN" in detail_text(page)
        page.s["plan"] = []
        page._switch()
        assert not errors, errors
    finally:
        close(win)


def test_compare():
    win, page, opened, errors = make_page()
    try:
        for n in ("HP UP", "ATK UP", "DEF UP", "CRI DMG UP"):
            page.toggle_compare(page.gsc.crest(n))
        assert page.s["compare"] == ["ATK UP", "DEF UP", "CRI DMG UP"]  # max 3, oldest dropped
        page.show_view("Compare")
        page.update()
        assert page.week_sf.winfo_ismapped() and not page.tree.winfo_ismapped()
        t = page.compare_table
        assert len(t) == len(LEVELS) and t[0][0] == "Lv1" and "ATK" in t[0][1], t[:2]
        page.toggle_compare(page.gsc.crest("DEF UP"))
        assert page.s["compare"] == ["ATK UP", "CRI DMG UP"]
        assert len(page.compare_table[0]) == 3
        # Unique crests keep both stat lines.
        page.toggle_compare(page.gsc.crest("Promise of Funeral God"))
        assert any("\n" in v for row in page.compare_table for v in row[1:])
        page.compare_clear()
        assert not page.compare_table
        assert not errors, errors
    finally:
        close(win)


def test_settings_remembered():
    tmp = Path(tempfile.mkdtemp(prefix="gsc_s_"))
    try:
        win, page, *_ = make_page(settings=tmp / "s.json")
        page.show_view("Crests")
        page.size.set("S")
        page._size_changed()
        page.save_state()
        close(win)
        win, page, *_ = make_page(settings=tmp / "s.json")
        assert page.view.get() == "Crests" and page.size.get() == "S"
        close(win)
        (tmp / "s.json").write_text("{broken", encoding="utf-8")
        win, page, *_ = make_page(settings=tmp / "s.json")  # broken file -> defaults
        assert page.view.get() == "Palace"
        close(win)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_every_record_renders_at_every_size():
    win, page, opened, errors = make_page()
    try:
        for size in ("S", "M", "L"):
            page.size.set(size)
            page._size_changed()
            for c in page.gsc.crests:
                page._show_crest(c)
            for u in page.gsc.units:
                page._show_unit(u)
            for foes in (False, True):
                page._show_foes = foes
                for s in page.gsc.stages:
                    page._show_stage(s)
        assert set(DAYS) >= {d for s in page.gsc.stages for d in s["days"]}
        assert not errors, errors
    finally:
        close(win)


def test_stage_guides():
    from gsc_app.guides import Guides
    win, page, opened, errors = make_page()
    try:
        g = page.guides
        assert g.available, "run gsc_app/fetch_guides.py first"
        for s in page.gsc.stages:
            sg = g.for_stage(s)
            assert sg and sg["summary"] and sg["roles"] and sg["waves"], s["name"]
            for name in Guides.recommended(sg):
                assert page.gsc.match_unit(name), (s["name"], name)
        s = page.gsc.stage("Shrine of Cinderplume")
        sg = g.for_stage(s)
        page.go("Palace", s)
        txt = detail_text(page)
        for part in ("STRATEGY", sg["summary"], "RECOMMENDED UNITS", "Mitigation",
                     "Shirou Emiya", "Also fits", "EXAMPLE TEAMS", "WAVES", "Arosdea",
                     "GSGL Official Discord Advisor Team"):
            assert part in txt, part
        assert "Blazing Dragon Rider Arosdea" not in txt  # enemy list starts hidden
        page._actions["Show enemy details"]()
        page.update()
        assert "Blazing Dragon Rider Arosdea" in detail_text(page)
        assert "Taunt Killer 5000%" in detail_text(page)
        page._actions["Team builder ↗"]()
        page._actions["Open guide ↗"]()
        assert opened[0].startswith("https://gscompanion.com/team-builder/"), opened
        assert opened[1].startswith("https://docs.google.com/"), opened
        # Star a recommended unit: the stage, the Palace list and the unit all show it.
        u = page.gsc.match_unit("Shirou Emiya")
        page.toggle_star(u)
        page.go("Palace", s)
        assert "★ 1 of yours are recommended here" in detail_text(page)
        page.day.set(s["days"][0])
        page.refresh()
        row = next(r for r in page._rows.values() if r["rec"] is s)
        assert row["values"]["team"] == "✓ 1", row["values"]
        page.go("Units", u)
        txt = detail_text(page)
        assert "RECOMMENDED IN THE CREST PALACE" in txt and "Shrine of Cinderplume" in txt
        assert "Mitigation" in txt
        page.show_view("Week")
        assert not errors, errors
        # No guides file: the stage panel falls back to the hazards list.
        empty = Path(tempfile.mkdtemp(prefix="gsc_g_"))
        page.guides = Guides(empty)
        page.go("Palace", s)
        assert "HAZARDS" in detail_text(page) and "STRATEGY" not in detail_text(page)
        shutil.rmtree(empty, ignore_errors=True)
        assert not errors, errors
    finally:
        close(win)


def test_pictures():
    win, page, opened, errors = make_page()
    try:
        if not page.pics.available:
            print("  (skipped: no data/gscompanion/images yet - run gsc_app/fetch_images.py)")
            return
        g, pics = page.gsc, page.pics
        missing = [u["name"] for u in g.units if pics.of(u, "unit", 30) is None]
        missing += [s["name"] for s in g.stages if pics.of(s, "stage", 30, 92) is None]
        missing += [c["name"] for c in g.crests if pics.of(c, "crest", 30) is None]
        missing += [lv for lv in LEVELS
                    if pics.get(pics.dir / "crests" / level_icon_name(lv), 18) is None]
        assert not missing, missing[:10]
        page.show_view("Units")
        assert all(page.tree.item(i, "image") for i in list(page._rows)[:20])
        select_where(page, lambda u: u["name"] == "Clyde")
        assert page.detail.image_names(), "no pictures in unit detail"
        page.go("Crests", g.crest("HP UP"))
        page.update()
        assert len(page.detail.image_names()) >= 11  # crest icon + 10 level icons
        page.go("Palace", g.stages[0])
        page.update()
        assert page.detail.image_names(), "no banner in stage detail"
        assert pics.get(pics.dir / "nope.png", 20) is None
        assert not errors, errors
    finally:
        close(win)


def test_rerun_hookup_on_a_copy():
    """Apply rerun_tab.patch to a throwaway copy of Rerun and start the real App."""
    tmp = Path(tempfile.mkdtemp(prefix="gsc_hook_"))
    try:
        shutil.copytree(ROOT / "rerun", tmp / "rerun", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(HERE, tmp / "gsc_app", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "routines", tmp / "routines")
        shutil.copytree(ROOT / "data" / "gscompanion", tmp / "data" / "gscompanion",
                        ignore=shutil.ignore_patterns("companion_settings.json"))
        r = subprocess.run(["git", "apply", str(HERE / "rerun_tab.patch")], cwd=tmp,
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        script = textwrap.dedent("""
            import sys; sys.path.insert(0, r'%s')
            from rerun.gui import App
            from rerun.manager import Manager
            from gsc_app.page import GSCompanionPage
            app = App(Manager(r'%s'))
            errors = []
            app.report_callback_exception = lambda *a: errors.append(a)
            pages = app.nb._pages
            assert len(pages) == 8, len(pages)
            assert isinstance(pages[-1], GSCompanionPage)
            assert app._tab_discord == 5 and pages[5] is not pages[-1]
            def step():
                app.nb.select(7); app.update()
                p = pages[-1]
                for v in ('Week', 'Units', 'Planner', 'Compare', 'Palace'):
                    p.show_view(v); app.update()
                p.show_view('Units'); app.update()
                assert len(p._rows) > 400
                app.after(300, app.destroy)
            app.after(300, step)
            app.after(30000, app.destroy)
            app.mainloop()
            assert not errors, errors
            print('HOOKUP OK')
        """) % (tmp, tmp)
        r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                           timeout=90)
        assert "HOOKUP OK" in r.stdout, r.stdout + r.stderr
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    failed = 0
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
