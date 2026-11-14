"""Fetch just the Crest Palace stage guides (and their pictures):

    py gsc_app/fetch_guides.py

Same as  py gsc_app/update_data.py --only guides,pictures  (see update_data.py)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gsc_app import update_data  # noqa: E402

if __name__ == "__main__":
    sys.exit(update_data.main(["--only", "guides,pictures"] + sys.argv[1:]))
