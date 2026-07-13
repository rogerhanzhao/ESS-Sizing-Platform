"""Global lock serialising native rendering (matplotlib + cairosvg).

Streamlit runs every browser session in its own worker thread. matplotlib's
pyplot global state (Gcf) and libcairo (via cairosvg) are NOT thread-safe:
concurrent figure/SVG rendering from different session threads corrupts native
state and hard-crashes the whole process (SIGSEGV, exit 139), which drops every
user's session ("logged out mid-sizing"). Serialising these calls with one
reentrant lock removes the concurrency without changing any rendering output.
Rendering is infrequent, so the throughput cost is negligible.
"""
from __future__ import annotations

import threading

# Reentrant so a render path that nests (e.g. report -> SLD -> cairosvg) on the
# same thread does not self-deadlock.
RENDER_LOCK = threading.RLock()
