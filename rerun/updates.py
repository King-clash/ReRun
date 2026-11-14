"""Update check: asks GitHub for the latest release of the configured repo and says whether
it is newer than this build. Read-only - nothing is downloaded or installed; the user opens
the release page. Only works for public repos. Set `update_repo` in config.yaml, e.g.
"owner/rerun" or "https://github.com/owner/rerun"."""
from __future__ import annotations

import json
import re
import urllib.request

from . import __version__

TIMEOUT_S = 8


def parse_repo(value: str) -> str | None:
    """'owner/name' from 'owner/name' or a github.com URL; None when it is not one."""
    m = re.fullmatch(r"(?:https?://github\.com/)?([\w.-]+)/([\w.-]+?)(?:\.git)?/?", (value or "").strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


def parse_version(tag: str) -> tuple[int, ...]:
    """'v1.2.3' -> (1, 2, 3); () when there are no numbers."""
    return tuple(int(n) for n in re.findall(r"\d+", (tag or "").split("-")[0]))


def is_newer(latest: str, current: str = __version__) -> bool:
    a, b = parse_version(latest), parse_version(current)
    return bool(a) and a > b


def check(repo_setting: str, current: str = __version__) -> dict | None:
    """{'version', 'url'} when a newer release exists, None when up to date.
    Raises ValueError for a bad repo setting and OSError/URLError on network trouble."""
    repo = parse_repo(repo_setting)
    if repo is None:
        raise ValueError(f"update_repo '{repo_setting}' is not 'owner/name' or a github.com URL")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Rerun-update-check"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        data = json.load(r)
    tag = str(data.get("tag_name", ""))
    if is_newer(tag, current):
        return {"version": tag.lstrip("vV"),
                "url": data.get("html_url") or f"https://github.com/{repo}/releases/latest"}
    return None
