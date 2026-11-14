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
from gsc_app.page import (DAYS, LEVELS, VIEWS, GSCompanionPage, level_icon_name,  # noqa: E402
                          today_name)
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
    return page.detail.get("1.0", "end").replace(" ", " ")  # names keep NBSPs


def select_where(page, pred) -> dict:
    for iid, r in page._rows.items():
        if r.get("rec") and pred(r["rec"]):
            page.tree.selection_set(iid)
            page.tree.event_generate("<<TreeviewSelect>>")
            page.update()
            return r["rec"]
    raise AssertionError("no row matched")


def test_stage_links_open_today_or_week():
    """There is no Palace tab: a stage opens in Today when it's open today, otherwise in
    the Week grid, with its guide in the detail panel."""
    win, page, opened, errors = make_page()
    try:
        assert page.view.get() == "Today" and "Palace" not in VIEWS
        today = {s["slug"] for s in page.gsc.palace_today()}
        assert {r["rec"]["slug"] for r in page._rows.values() if r["kind"] == "stage"} == today
        s = select_where(page, lambda s: "boss" in s)
        txt = detail_text(page)
        assert s["boss"] in txt and "CRESTS THAT DROP HERE" in txt
        page.open_current()
        assert opened == [s["url"]], opened
        not_today = next(x for x in page.gsc.stages if today_name() not in x["days"])
        page.go("Stage", not_today)
        page.update()
        assert page.view.get() == "Week" and not_today["boss"] in detail_text(page)
        page.go("Stage", s)
        page.update()
        assert page.view.get() == "Today"
        sel = page.tree.selection()
        assert sel and page._rows[sel[0]]["rec"] is s
        page.back()
        page.update()
        assert page.view.get() == "Week" and not_today["boss"] in detail_text(page)
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
        page.go("Stage", stage)
        page.update()
        assert page.view.get() in ("Today", "Week")
        assert "Shrine of Caliginosity" in detail_text(page) and stage["boss"] in detail_text(page)
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
        assert page.my.unmatched == ["Unreadable Nam3"], page.my.unmatched
        assert "1 not matched" in page.my.scan_status()
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
        # Crest lists show how many of your units want them.
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
        assert page.view.get() == "Today"
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
            for v in VIEWS:
                page.show_view(v)
                page.update()
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
        page.go("Stage", s)
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
        # Star a recommended unit: the stage, its readiness and the unit all show it.
        u = page.gsc.match_unit("Shirou Emiya")
        page.toggle_star(u)
        page.go("Stage", s)
        assert "★ 1 of yours are recommended here" in detail_text(page)
        assert page._ready_text(s, page.my.all())[0] == f"1/{len(sg['roles'])}"  # Mitigation
        page.go("Units", u)
        txt = detail_text(page)
        assert "RECOMMENDED IN THE CREST PALACE" in txt and "Shrine of Cinderplume" in txt
        assert "Mitigation" in txt
        page.show_view("Week")
        assert not errors, errors
        # No guides file: the stage panel falls back to the hazards list.
        empty = Path(tempfile.mkdtemp(prefix="gsc_g_"))
        page.guides = Guides(empty)
        page.go("Stage", s)
        assert "HAZARDS" in detail_text(page) and "STRATEGY" not in detail_text(page)
        shutil.rmtree(empty, ignore_errors=True)
        assert not errors, errors
    finally:
        close(win)


def test_today_and_crests_you_have():
    win, page, opened, errors = make_page()
    try:
        today = today_name()
        page.show_view("Today")
        stages = [r["rec"] for r in page._rows.values() if r["kind"] == "stage"]
        assert {s["slug"] for s in stages} == {s["slug"] for s in page.gsc.palace_on(today)}
        assert "Today: " + today in detail_text(page)
        # A starred unit whose crest drops today shows up under that stage.
        stage = next(s for s in page.gsc.palace_on(today) if s.get("crests"))
        crest = stage["crests"][0]
        unit = page.gsc.units_wanting(crest)[0]
        page.toggle_star(page.gsc.match_unit(unit))
        page.show_view("Today")
        kids = [r for r in page._rows.values() if r["kind"] == "crest"
                and r["rec"]["name"] == crest]
        assert kids and unit in kids[0]["values"]["units"], kids
        # Mark it as had: it leaves Today, the planner and the "need" counts.
        page.go("Units", page.gsc.match_unit(unit))
        acts = [k for k in page._actions if "has it" in k]
        assert acts, list(page._actions)
        page.toggle_have(page.gsc.match_unit(unit), crest)
        assert page.my.has(unit, crest) and page.s["have"] == {unit: [crest]}
        page.show_view("Today")
        assert not any(r["kind"] == "crest" and r["rec"]["name"] == crest and
                       unit in r["values"]["units"] for r in page._rows.values())
        page.toggle_plan(page.gsc.match_unit(unit))
        p = page.plan()
        assert all(unit not in e["units"] for es in p["days"].values() for e in es
                   if e["crest"] == crest)
        page.go("Crests", page.gsc.crest(crest))
        assert "YOUR UNITS THAT HAVE IT" in detail_text(page)
        page.toggle_have(page.gsc.match_unit(unit), crest)
        assert page.s["have"] == {}
        # New game day: refresh + message, no error.
        page._new_day("Monday")
        assert not errors, errors
    finally:
        close(win)


def test_team_checker():
    from gsc_app.team import hazard_hits
    win, page, opened, errors = make_page()
    try:
        s = page.gsc.stage("Shrine of Cinderplume")  # Taunt Killer, Earth Killer
        page.open_team_for(s)
        assert page.view.get() == "Team" and page.team_stage_rec() is s
        assert "Team check" in detail_text(page)
        page.team_filter.set("All units")
        page._team_filter_changed()
        assert len(page._rows) == len(page.gsc.units)
        # Earth units are flagged by "Earth Killer".
        earth = next(u for u in page.gsc.units if u["element"] == "Earth")
        assert hazard_hits("Earth Killer", earth, None)
        assert not hazard_hits("Earth Killer", {"element": "Fire"}, None)
        assert hazard_hits("MAG DMG negated", {"element": "Fire"},
                           {"details": {"Attack": "Magic"}})
        assert hazard_hits("Demon Killer", {"element": "Fire"}, {"race": "Demon"})
        # Build a team by clicking the Team column (via toggle_team), up to 4.
        for n in ("Shirou Emiya", "Jay", earth["name"], "Ultimate Paladin Roy", "Beta"):
            page.toggle_team(n)
        assert page.s["team"] == ["Shirou Emiya", "Jay", earth["name"], "Ultimate Paladin Roy"]
        txt = detail_text(page)
        assert "✓  Mitigation" in txt and "✓  Debuffers" in txt and "✗  Arts gen" in txt, txt
        assert f"{earth['name']}: Earth unit vs Earth Killer" in txt
        assert "EXAMPLE TEAMS" in txt and "Use this team" in txt
        page._actions["Use this team"]()  # (the last example team's button)
        last = page.guides.for_stage(s)["teams"][-1]
        assert page.s["team"] == [u["name"] for u in last["units"]], page.s["team"]
        page.team_clear()
        assert page.s["team"] == []
        # Suggest from your units: an example team you own wins.
        for n in ("Ultimate Paladin Roy", "Houka Inumuta", "Shirou Emiya", "Jay"):
            page.toggle_star(page.gsc.match_unit(n))
        page.team_suggest()
        assert page.s["team"] == ["Ultimate Paladin Roy", "Houka Inumuta", "Shirou Emiya",
                                  "Jay"], page.s["team"]
        r = page.teams.readiness(s, page.my.all())
        assert r["full_teams"] == [1] and len(r["filled"]) >= 3, r
        # Another stage from the menu; every stage checks without errors.
        for st in page.gsc.stages:
            page.team_stage.set(page._stage_label(st))
            page._team_stage_changed()
        assert not errors, errors
    finally:
        close(win)


def test_search_everything_and_kits():
    win, page, opened, errors = make_page()
    try:
        page.show_view("Crests")
        page.find_q.set("flogassa")
        assert page.view.get() == "Find"
        names = [r["rec"]["name"] for r in page._rows.values() if r.get("rec")]
        assert "Shrine of Cinderplume" in names, names
        page.find_q.set("atk up")
        kinds = {r["kind"] for r in page._rows.values()}
        assert {"crest", "unit"} <= kinds, kinds
        if page.details:
            page.find_q.set("unlimited blade works")
            names = [r["rec"]["name"] for r in page._rows.values() if r.get("rec")]
            assert "Shirou Emiya" in names, names
            select_where(page, lambda u: u.get("name") == "Shirou Emiya")
            txt = detail_text(page)
            assert "KIT" in txt and "Rho Aias" in txt and "Passives" in txt, txt[-800:]
            page._actions["Hide kit"]()
            assert "Rho Aias" not in detail_text(page)
            page._actions["Show kit"]()
        page._clear_search()  # Esc closes the results and returns to the last view
        assert page.view.get() == "Crests" and not page.find_q.get()
        assert not errors, errors
    finally:
        close(win)


def test_scrapers_and_update_offline():
    """The page parsers read today's saved pages the same as the data files, and an
    'Update data' run is wired up (network replaced by the saved pages)."""
    from gsc_app import scrape, update_data
    raw = ROOT / "data" / "gscompanion" / "raw" / "stages"
    stages = json.loads((ROOT / "data/gscompanion/crest_palace.json").read_text("utf-8"))
    st = stages["stages"][0]
    page_html = (raw / f"{st['slug']}.html").read_text(encoding="utf-8")
    g = scrape.parse_stage_guide(page_html, st)
    assert g["summary"] and g["roles"] and g["waves"] and g["source"]["url"]
    # A run into a temp folder with the network faked: guides only.
    tmp = Path(tempfile.mkdtemp(prefix="gsc_up_"))
    try:
        shutil.copy2(ROOT / "data/gscompanion/crest_palace.json", tmp / "crest_palace.json")
        up = update_data.Updater(tmp, parts=("guides",))
        up.page = lambda path: (raw / (path.strip("/").split("/")[-1] + ".html")).read_text(
            encoding="utf-8")
        assert up.run(), up.failed
        out = json.loads((tmp / "stage_guides.json").read_text(encoding="utf-8"))
        assert len(out["stages"]) == len(stages["stages"])
        # A broken list page never replaces good data.
        up2 = update_data.Updater(tmp, parts=("lists",))
        up2.page = lambda path: "<html><main></main></html>"
        assert not up2.run() and up2.failed
        assert not (tmp / "crests.json").exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_update_button_reloads_from_new_folder():
    """The exe's case: Update data writes to a folder next to the exe, starting from the
    bundled copy, then the app reloads from there (network replaced by a no-op run)."""
    from gsc_app import update_data
    tmp = Path(tempfile.mkdtemp(prefix="gsc_ub_"))
    win, page, opened, errors = make_page()
    real_run, real_confirm = update_data.Updater.run, ios.confirm
    try:
        page.data_out = tmp / "data" / "gscompanion"
        update_data.Updater.run = lambda self: (self.summary.append("test run"), True)[1]
        ios.confirm = lambda *a, **k: True
        page.update_data()
        for _ in range(100):
            page.update()
            if page._updater is None:
                break
            win.after(50)
        assert page._updater is None
        assert (page.data_out / "crests.json").exists()  # bundled copy was taken first
        assert page.gsc.dir.resolve() == page.data_out.resolve()
        assert page.details and page.guides.available
        assert not errors, errors
    finally:
        update_data.Updater.run, ios.confirm = real_run, real_confirm
        close(win)
        shutil.rmtree(tmp, ignore_errors=True)


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
        page.go("Stage", g.stages[0])
        page.update()
        assert page.detail.image_names(), "no banner in stage detail"
        assert pics.get(pics.dir / "nope.png", 20) is None
        assert not errors, errors
    finally:
        close(win)


def test_rerun_hookup_on_a_copy():
    """Start the real Rerun App on a throwaway copy (code, data, a small unit scan) and use
    the Companion tab and the links between it and Rerun's Units tab."""
    tmp = Path(tempfile.mkdtemp(prefix="gsc_hook_"))
    try:
        shutil.copytree(ROOT / "rerun", tmp / "rerun", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(HERE, tmp / "gsc_app", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "routines", tmp / "routines")
        shutil.copytree(ROOT / "data" / "gscompanion", tmp / "data" / "gscompanion",
                        ignore=shutil.ignore_patterns("companion_settings.json"))
        # a scan as Rerun saves it: one name as the game shows it, one fodder unit
        sys.path.insert(0, str(tmp))
        ob = lambda n, el, c: {"name": n, "name_conf": 90, "fields": {  # noqa: E731
            "element": {"value": el, "confidence": 90}, "quest_clears": {"value": c, "confidence": 90}}}
        from rerun.units import UnitRoster as _R  # noqa: E402 - the copy is identical
        _R(tmp).apply_scan([ob("Clyde, the Crimson Sword God", "Fire", 12), ob("Troll", "Earth", 3)],
                           "units_list", complete=True)
        script = textwrap.dedent("""
            import sys; sys.path.insert(0, r'%s')
            from rerun.gui import App
            from rerun.manager import Manager
            from gsc_app.page import GSCompanionPage
            m = Manager(r'%s')
            # GS Companion's name took priority over the game's title
            assert 'Clyde' in m.units.units and 'Troll' in m.units.units, list(m.units.units)
            m.config['live_view_fps'] = 0   # no video stream from a real emulator in tests
            app = App(m)
            errors = []
            app.report_callback_exception = lambda *a: errors.append(a)
            pages = app.nb._pages
            assert isinstance(pages[-1], GSCompanionPage) and app._tab_companion == len(pages) - 1
            assert sum(isinstance(p, GSCompanionPage) for p in pages) == 1
            assert pages[app._tab_discord] is not pages[-1]
            def step():
                p = pages[-1]
                app.nb.select(len(pages) - 1); app.update()
                for v in ('Today', 'Week', 'Units', 'Team', 'Planner', 'Compare'):
                    p.show_view(v); app.update()
                p.show_view('Units'); app.update()
                assert len(p._rows) > 400
                # Rerun Units -> Companion
                app.nb.select(4); app.refresh_units(); app.update()
                app.units_tree.selection_set('Clyde'); app.units_gsc(); app.update()
                assert app.nb.index() == app._tab_companion and p._shown[1]['name'] == 'Clyde'
                assert 'Clyde' in p.my.scanned() and p.my.roster_of['Clyde'] == 'Clyde'
                assert '12 quest clears' in p.rerun.unit_line('Clyde')
                # Companion -> Rerun Units
                assert p.rerun.show_unit('Clyde'); app.update()
                assert app.nb.index() == 4 and app.units_tree.selection() == ('Clyde',)
                # a target set in Rerun shows in the Companion panel
                m.compendium.set_target('Clyde', 20); app._companion_refresh(); app.update()
                assert 'target 20' in p.rerun.unit_line('Clyde')
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
