"""
macOS menu bar application — built with `rumps`.

Shows the agent status, contribution stats, and quick controls
in the macOS status bar. Installed as part of the .dmg package.

Requirements: macOS 12+, Python 3.11+
Install: pip install rumps requests
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
import urllib.error

import rumps

AGENT_URL = "http://127.0.0.1:7777"
REFRESH_INTERVAL = 15   # seconds


class DTMenuBarApp(rumps.App):
    """
    Distributed Training node menu bar icon.

    States:
      ● (green)  — agent running, contributing
      ◐ (yellow) — agent running, idle (no task assigned)
      ○ (gray)   — agent stopped
    """

    def __init__(self):
        super().__init__(
            name="Distributed Training",
            title="○ DT",
            quit_button="Quit",
        )
        self._agent_running = False
        self._status_cache: dict = {}

        # Menu items
        self.status_item = rumps.MenuItem("Status: checking…")
        self.contribution_item = rumps.MenuItem("Contribution: —")
        self.credits_item = rumps.MenuItem("Credits: —")
        self.peers_item = rumps.MenuItem("Peers: —")
        self.separator1 = None  # rumps uses None for separators
        self.start_stop_item = rumps.MenuItem("Start Agent", callback=self._toggle_agent)
        self.open_dashboard_item = rumps.MenuItem("Open Dashboard", callback=self._open_dashboard)

        self.menu = [
            self.status_item,
            self.contribution_item,
            self.credits_item,
            self.peers_item,
            None,   # separator
            self.start_stop_item,
            self.open_dashboard_item,
        ]

        # Start background refresh
        self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._refresh_thread.start()

    # ------------------------------------------------------------------
    # Background refresh
    # ------------------------------------------------------------------

    def _refresh_loop(self) -> None:
        while True:
            self._refresh()
            time.sleep(REFRESH_INTERVAL)

    def _refresh(self) -> None:
        try:
            with urllib.request.urlopen(f"{AGENT_URL}/status", timeout=2) as r:
                status = json.loads(r.read())
            with urllib.request.urlopen(f"{AGENT_URL}/credits", timeout=2) as r:
                credits = json.loads(r.read())

            self._agent_running = status.get("running", False)
            units = status.get("total_compute_units", 0)

            # Update menu items (must be on main thread via rumps.Window)
            def _update():
                tier_emoji = self._tier_emoji(units)
                self.title = f"● DT" if self._agent_running else "○ DT"
                self.status_item.title = (
                    f"Status: {'Running ✓' if self._agent_running else 'Stopped'}"
                )
                self.contribution_item.title = (
                    f"{tier_emoji} Contribution: {units:.1f} units"
                )
                self.credits_item.title = (
                    f"Credits: {credits.get('available', 0):.0f} available"
                )
                self.peers_item.title = (
                    f"Peers: {status.get('peers_known', 0)} online"
                )
                self.start_stop_item.title = (
                    "Stop Agent" if self._agent_running else "Start Agent"
                )
            rumps.Timer(_update, 0).start()

        except (urllib.error.URLError, Exception):
            def _offline():
                self.title = "○ DT"
                self.status_item.title = "Status: Agent offline"
            rumps.Timer(_offline, 0).start()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _toggle_agent(self, _) -> None:
        if self._agent_running:
            try:
                urllib.request.urlopen(
                    urllib.request.Request(f"{AGENT_URL}/stop", method="POST"), timeout=3
                )
            except Exception:
                pass
        else:
            # Launch the agent subprocess
            import subprocess, sys, os
            subprocess.Popen(
                [sys.executable, "-m", "node_agent.__main__"],
                env={**os.environ},
                start_new_session=True,
            )
        time.sleep(1)
        self._refresh()

    def _open_dashboard(self, _) -> None:
        import subprocess
        subprocess.run(["open", "http://localhost:8000"], check=False)

    @staticmethod
    def _tier_emoji(units: float) -> str:
        if units >= 72_000:
            return "⚡"   # power tier
        if units >= 3_600:
            return "★"    # contributor
        return "☆"         # free


def main():
    logging.basicConfig(level=logging.WARNING)
    DTMenuBarApp().run()


if __name__ == "__main__":
    main()
