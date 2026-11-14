"""Download the pictures the GS Companion scrape links to, for the app to show offline.

    py gsc_app/fetch_images.py

Reads the image links in data/gscompanion/raw/*.md (unit thumbnails, Crest Palace stage
banners, crest level/event icons) and saves each one under data/gscompanion/images/,
keeping the site's path after /images/ (images/crests/lv3.png, images/stages/banner_....webp).

- Only gscompanion.com/images/ links are fetched; anything else is ignored.
- One request at a time with a pause between them; files already saved are skipped,
  so a re-run only fetches what is missing.
- Every file is checked to be a real image before it is kept.
The pictures are the site's / the game's: they stay in data/ (git-ignored) for your own use.
"""
from __future__ import annotations

import io
import re
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "gscompanion"
OUT = DATA / "images"
PREFIX = "https://gscompanion.com/images/"
URL_RE = re.compile(r"https://gscompanion\.com/images/[A-Za-z0-9_./-]+\.(?:png|webp|jpg|jpeg|gif)")
PAUSE_S = 0.3
MAX_BYTES = 3_000_000
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) image-cache/1.0"}


def image_urls() -> list[str]:
    urls: set[str] = set()
    for md in sorted((DATA / "raw").glob("*.md")):
        urls.update(URL_RE.findall(md.read_text(encoding="utf-8")))
    return sorted(u for u in urls if ".." not in u)


def local_path(url: str) -> Path:
    """https://gscompanion.com/images/crests/lv3.png -> data/gscompanion/images/crests/lv3.png"""
    rel = url[len(PREFIX):]
    p = (OUT / rel).resolve()
    if OUT.resolve() not in p.parents:
        raise ValueError(f"unsafe path: {url}")
    return p


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("too large")
    with Image.open(io.BytesIO(data)) as im:
        im.verify()  # raises if it isn't a real image
    return data


def main() -> int:
    urls = image_urls()
    todo = [u for u in urls if not local_path(u).exists()]
    print(f"{len(urls)} pictures linked, {len(urls) - len(todo)} already saved, {len(todo)} to fetch")
    failed = []
    for i, url in enumerate(todo, 1):
        p = local_path(url)
        try:
            data = fetch(url)
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(p.suffix + ".part")
            tmp.write_bytes(data)
            tmp.replace(p)
        except Exception as e:  # noqa: BLE001 - report and carry on
            failed.append((url, str(e)))
        if i % 50 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)}  ({len(failed)} failed)", flush=True)
        time.sleep(PAUSE_S)
    for url, err in failed:
        print(f"FAILED {url}: {err}")
    total = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) if OUT.exists() else 0
    print(f"Done: {len(urls) - len(failed)}/{len(urls)} saved, {total / 1e6:.1f} MB in {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
