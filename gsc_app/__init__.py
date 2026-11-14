"""GS Companion browser: Crest Palace schedule, crests and per-unit crest picks,
read from data/gscompanion/ (built by tools/gscompanion_build.py).

Standalone:      python -m gsc_app          (or "gsc_app/Run GS Companion.bat")
Inside Rerun:    not wired in yet - see gsc_app/INTEGRATION.md.
"""
from .page import GSCompanionPage

__all__ = ["GSCompanionPage"]
