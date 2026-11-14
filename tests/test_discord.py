"""Discord bot (Phase 6) without connecting: alert colours, status board content, control
buttons and their permission check, /energy."""
from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from rerun.discord_bot import (ACTIONS, COLORS, DiscordBot, alert_kind, board_fields)  # noqa: E402
from rerun.manager import Manager  # noqa: E402


def manager() -> Manager:
    d = Path(tempfile.mkdtemp())
    shutil.copytree(ROOT / "routines", d / "routines")
    m = Manager(d)
    m.config["discord"]["token"] = "x"
    m.config["discord"]["allowed_user_ids"] = [111]
    return m


def test_alert_colours_on_real_messages():
    gold = ["Crest Burst (5+) found on Instance 1! Script stopped - check your emulator.",
            "4+ crest found on Instance 1! Left on the Equip Crest screen for you.",
            "Hyper rare drop on Instance 1!"]
    red = ["Crest: couldn't find the new crest on the Equip Crest screen. Stopped so nothing is scrapped by mistake.",
           "Crest made no progress for 10 minutes - stopped.",
           "Crest: out of energy - no potions left. Stopped.",
           "Crest: the game says \"Communication error\". Stopped - this needs you."]
    green = ["Compendium Counter: 193 unit(s) counted - saved to compendium_report.csv.",
             "Login & Mail finished: 12 mails claimed."]
    for msg in gold:
        assert alert_kind(msg) == "gold", msg
    for msg in red:
        assert alert_kind(msg) == "red", msg
    for msg in green:
        assert alert_kind(msg) == "green", msg
    assert alert_kind("Crest: Past Party applied") == "info"
    assert COLORS["gold"] == 0xF1C40F and COLORS["red"] == 0xE74C3C and COLORS["green"] == 0x2ECC71


def test_status_board_content():
    m = manager()
    name = next(iter(m.instances))
    f = dict(board_fields(m, name))
    for k in ("Status", "Script", "Quest", "Mode", "Runs", "Energy", "Up", "Last action", "Errors (24 h)"):
        assert k in f, k
    assert "idle" in f["Status"] and f["Script"] and f["Energy"] == "-"
    m.stats.incr(name, f"{m.instances[name].script}.runs", 7)
    m._energy = {name: (65, 517, 0.0)}
    f = dict(board_fields(m, name))
    assert f["Runs"] == "7" and f["Energy"] == "65/517"


class FakeResponse:
    def __init__(self):
        self.sent = []

    async def send_message(self, text, ephemeral=False):
        self.sent.append((text, ephemeral))

    async def defer(self, thinking=False):
        self.sent.append(("defer", thinking))


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, text=None, file=None, embed=None):
        self.sent.append((text, file))


class FakeUser:
    def __init__(self, uid):
        self.id = uid

    def __str__(self):
        return f"user{self.id}"


class FakeInter:
    def __init__(self, uid, custom_id):
        self.user = FakeUser(uid)
        self.data = {"custom_id": custom_id}
        self.response = FakeResponse()
        self.followup = FakeFollowup()


def test_buttons_check_permission_and_act():
    m = manager()
    name = next(iter(m.instances))
    bot = DiscordBot(m)
    started = []
    m.start = lambda inst, script=None: started.append((inst, script)) or f"Started {script} on {inst}"
    m.stop = lambda inst: f"Stopping {inst}"
    m.screenshot = lambda inst: np.zeros((20, 10, 3), np.uint8)

    async def no_board(force=False):
        return None
    bot.update_board = no_board

    async def run():
        # the view: four buttons with the instance in their ids
        view = bot.controls(name)
        ids = [c.custom_id for c in view.children]
        assert ids == [f"rerun:{a}:{name}" for a in ACTIONS], ids
        # someone not in allowed_user_ids: refused, nothing happens
        bad = FakeInter(999, f"rerun:crest:{name}")
        await bot.on_button(bad)
        assert bad.response.sent[0][1] is True and "not allowed" in bad.response.sent[0][0]
        assert started == []
        # allowed user: Start Crest, Stop, Resume (idle -> start), Screenshot
        ok = FakeInter(111, f"rerun:crest:{name}")
        await bot.on_button(ok)
        assert started == [(name, "crest")] and "Start Crest" in ok.response.sent[0][0]
        stop = FakeInter(111, f"rerun:stop:{name}")
        await bot.on_button(stop)
        assert "Stopping" in stop.response.sent[0][0]
        res = FakeInter(111, f"rerun:resume:{name}")
        await bot.on_button(res)
        assert started[-1] == (name, None)
        shot = FakeInter(111, f"rerun:shot:{name}")
        await bot.on_button(shot)
        assert shot.response.sent[0][0] == "defer" and shot.followup.sent[0][1] is not None
        unknown = FakeInter(111, "rerun:stop:Nope")
        await bot.on_button(unknown)
        assert "No instance" in unknown.response.sent[0][0]
    asyncio.run(run())


def test_board_embed_and_client_build():
    m = manager()
    bot = DiscordBot(m)
    name = next(iter(m.instances))

    async def run():
        e = bot.board_embed(name)
        assert e.title == f"{name} - live status" and len(e.fields) >= 9
        client = bot._build_client()
        assert client is not None
    asyncio.run(run())


def test_energy_falls_back_to_cache_and_reads_running_script():
    m = manager()
    name = next(iter(m.instances))
    assert m.energy(name) is None
    m.screenshot = lambda inst: (_ for _ in ()).throw(RuntimeError("no device"))
    assert m.energy(name, fresh=True) is None          # no emulator: unknown, no crash
    m._energy = {name: (10, 20, 1.0)}
    assert m.energy(name) == (10, 20, 1.0)


if __name__ == "__main__":
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
