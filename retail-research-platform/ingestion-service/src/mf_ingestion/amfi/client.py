"""HTTP client for the AMFI scheme master / NAV feed.

Deliberately thin: it fetches bytes and hands them to `parser.parse_navall`.
All the logic worth testing lives in the parser, which needs no network.

Note on environments: some sandboxes (including the one this was developed in)
block amfiindia.com at the egress proxy, so `fetch_scheme_master` cannot run
there. That is an environment policy, not a property of the data -- the feed is
free and public, and this works from an unrestricted host. `load_scheme_master`
exists for exactly that case: point it at a downloaded snapshot and the rest of
the pipeline behaves identically.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx

from ..models import SchemeMaster
from .parser import parse_navall

NAVALL_URL = "https://www.amfiindia.com/spages/NAVAll.txt"
DEFAULT_TIMEOUT_SECONDS = 60.0


def fetch_scheme_master(
    url: str = NAVALL_URL,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> SchemeMaster:
    """Download and parse the current AMFI scheme master + NAV snapshot."""
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return parse_navall(response.text, source_url=url, fetched_at=date.today())


def load_scheme_master(path: str | Path, source_url: str = NAVALL_URL) -> SchemeMaster:
    """Parse a previously downloaded NAVAll snapshot from disk.

    `fetched_at` comes from the file's modification time rather than today, so
    a stale snapshot cannot masquerade as fresh data -- as-of dating has to
    survive the offline path too, not just the network one.
    """
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8", errors="replace")
    fetched_at = date.fromtimestamp(file_path.stat().st_mtime)
    return parse_navall(text, source_url=source_url, fetched_at=fetched_at)
