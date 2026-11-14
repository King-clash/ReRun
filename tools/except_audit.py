"""List every broad `except Exception` / bare except and whether it tells anyone.

    py tools/except_audit.py            table of all of them
    py tools/except_audit.py --silent   only the ones that swallow the error without a trace

A handler "reports" if it re-raises or calls something that logs/notifies/records (log, notify,
errlog, print, record, flash, put, emit, ...). Otherwise it is "silent": it is fine for purely
cosmetic things (tray icon, DPI call) but suspicious anywhere else."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTING = ("log", "notify", "errlog", "print", "record", "flash", "put", "emit", "warn", "alert",
             "send", "error", "note", "add", "report")


def broad(handler: ast.ExceptHandler) -> bool:
    t = handler.type
    if t is None:
        return True
    names = [t] if not isinstance(t, ast.Tuple) else list(t.elts)
    return any(isinstance(n, ast.Name) and n.id in ("Exception", "BaseException") for n in names)


def reports(handler: ast.ExceptHandler) -> bool:
    for node in ast.walk(ast.Module(body=handler.body, type_ignores=[])):
        if isinstance(node, ast.Raise):
            return True
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if any(k in name.lower() for k in REPORTING):
                return True
    return False


def audit(roots=("rerun", "gsc_app", "tools")) -> list[dict]:
    rows = []
    for root in roots:
        for path in sorted((ROOT / root).rglob("*.py")):
            if "test" in path.name:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler) and broad(node):
                    note = lines[node.lineno - 1].split("#", 1)[1].strip() if "#" in lines[node.lineno - 1] else ""
                    rows.append({"file": str(path.relative_to(ROOT)).replace("\\", "/"),
                                 "line": node.lineno, "reports": reports(node), "note": note})
    return rows


def main() -> int:
    rows = audit()
    only_silent = "--silent" in sys.argv
    shown = [r for r in rows if not (only_silent and r["reports"])]
    for r in shown:
        print(f"{'reports' if r['reports'] else 'SILENT '}  {r['file']}:{r['line']}  {r['note']}")
    print(f"\n{len(rows)} broad handlers; {sum(not r['reports'] for r in rows)} silent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
