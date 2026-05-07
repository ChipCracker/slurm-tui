"""GPU Hours Widget — two-section panel for the GPU hours leaderboard and
running-jobs summary.

Layout (matching the DiskQuotaWidget pattern):

    GPU Hours 2026                          h hide · H expand  60s
    ────────────────────────────────────────
    Top 10  ·  #2 18,942h

    Running Jobs                            o hide · O expand  10s
    ────────────────────────────────────────
    17 jobs  ·  17 GPUs  ·  136 CPUs

Each section has its own Horizontal header with a right-aligned hint, a
separator, and a content Static.  ``h``/``o`` toggle visibility (hide
completely), ``H``/``O`` toggle between collapsed one-liner and expanded
detail view.

Performance:
    - The leaderboard is fetched via ``sreport`` every 60 s in a background
      thread (``@work(thread=True, exclusive=True)``).
    - Running-jobs data comes from ``JobTableWidget.JobsRefreshed`` messages
      (10 s cycle) — no extra subprocess calls.
    - All UI updates are imperative ``Static.update()`` calls; no
      ``recompose()`` is ever triggered.
"""

from __future__ import annotations

import os
from datetime import datetime

from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Static
from textual.widget import Widget
from textual.worker import get_current_worker

from ..utils.gpu import GPUMonitor, GPUHoursEntry
from ..utils.slurm import Job


# ── Helpers ──────────────────────────────────────────────────────────


def make_hours_bar(hours: float, max_hours: float, width: int = 20) -> str:
    """Create a horizontal bar proportional to *hours / max_hours*."""
    if max_hours <= 0:
        return "░" * width
    percent = min(hours / max_hours, 1.0)
    filled = int(percent * width)
    empty = width - filled
    return "█" * filled + "[#565f89]" + "░" * empty + "[/]"


# ── Widget ───────────────────────────────────────────────────────────


class GPUHoursWidget(Widget):
    """Two-section panel: GPU hours leaderboard + running-jobs summary.

    Public API consumed by MainScreen:
        - ``refresh_data()``      — force-fetch GPU hours
        - ``update_running_jobs()`` — push fresh job list
        - ``toggle_hours_visible()`` / ``toggle_hours()``
        - ``toggle_running_visible()`` / ``toggle_expanded()``
    """

    DEFAULT_CSS = """
    GPUHoursWidget {
        background: transparent;
        border: none;
        height: auto;
        padding: 0 2;
        margin: 0 0 1 0;
    }

    /* ── Hours section ───────────────────────────── */
    GPUHoursWidget > #hours-section { height: auto; }

    GPUHoursWidget > #hours-section > .section-header {
        layout: horizontal;
        height: 1;
        margin-bottom: 0;
    }

    GPUHoursWidget > #hours-section > .section-header > .section-title {
        width: 1fr;
        color: #565f89;
    }

    GPUHoursWidget > #hours-section > .section-header > .section-info {
        width: auto;
        color: #414868;
    }

    GPUHoursWidget > #hours-section > .separator {
        color: #414868;
        margin-bottom: 0;
    }

    GPUHoursWidget > #hours-section > .hours-content {
        height: auto;
    }

    /* ── Running section (single summary line) ──── */
    GPUHoursWidget > #running-section { height: auto; margin-top: 1; }

    GPUHoursWidget > #running-section > .running-content {
        height: auto;
    }
    """

    # ── Init ──────────────────────────────────────────────────────

    def __init__(
        self,
        gpu_monitor: GPUMonitor | None = None,
        refresh_interval: float = 60.0,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.gpu_monitor = gpu_monitor or GPUMonitor()
        self.refresh_interval = refresh_interval
        self.current_user = os.environ.get("USER", "")
        self._timer = None
        self._entries: list[GPUHoursEntry] = []
        self._running_jobs: list[Job] = []
        # Section states — both start hidden; user presses h/o to show.
        self._hours_collapsed: bool = False
        self._hours_visible: bool = False
        self._running_visible: bool = False

    # ── Compose ───────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        """Build the two-section layout (hours + running), each with a
        DiskQuota-style header, separator, and content Static."""
        year = datetime.now().year

        # GPU Hours section
        with Container(id="hours-section"):
            with Horizontal(classes="section-header"):
                yield Static(f"GPU Hours {year}", classes="section-title")
                yield Static(
                    self._hours_hint_text(),
                    classes="section-info",
                    id="hours-info",
                )
            yield Static("─" * 56, classes="separator")
            yield Static(
                "[#565f89]Loading hours data...[/]",
                classes="hours-content",
            )

        # Running Jobs — single summary line, toggled via 'o'
        with Container(id="running-section"):
            yield Static("", classes="running-content")

    # ── Data fetching ─────────────────────────────────────────────

    def on_mount(self) -> None:
        """Start auto-refresh timer (5 s offset so sreport loads last)."""
        # Both sections start hidden — hide the entire widget to free space.
        self._sync_widget_visibility()
        self.set_timer(5.0, self._start_refresh)

    def _start_refresh(self) -> None:
        """Kick off the first fetch and schedule periodic refreshes."""
        self.refresh_data()
        self._timer = self.set_interval(self.refresh_interval, self.refresh_data)

    @work(thread=True, exclusive=True)
    def refresh_data(self) -> None:
        """Fetch GPU hours via ``sreport`` in a background thread."""
        worker = get_current_worker()
        try:
            entries = self.gpu_monitor.get_gpu_hours(limit=10)
            if not worker.is_cancelled:
                self.app.call_from_thread(self._apply_hours, entries)
        except Exception:
            pass

    def _apply_hours(self, entries: list[GPUHoursEntry]) -> None:
        """Store fetched entries and re-render the hours section."""
        self._entries = entries
        self._render_hours()

    def update_running_jobs(self, jobs: list[Job]) -> None:
        """Push a fresh job list from the job-table refresh cycle (10 s)."""
        self._running_jobs = [j for j in jobs if j.state == "R"]
        self._render_running()

    # ── Hint text helpers ─────────────────────────────────────────

    def _hours_hint_text(self) -> str:
        """Build the right-aligned hint for the hours section header."""
        return f"h to toggle  {int(self.refresh_interval)}s"

    def _update_hours_hint(self) -> None:
        """Sync the hours header hint with the current state."""
        try:
            self.query_one("#hours-info", Static).update(self._hours_hint_text())
        except Exception:
            pass

    # ── Hours rendering ───────────────────────────────────────────

    def _render_hours(self) -> None:
        """Re-render the hours content Static based on visibility/state."""
        try:
            section = self.query_one("#hours-section", Container)
            content = self.query_one(".hours-content", Static)
        except Exception:
            return

        # Hidden → collapse the entire section container
        if not self._hours_visible:
            section.display = False
            return

        section.display = True
        self._update_hours_hint()

        # Collapsed one-liner
        if self._hours_collapsed:
            content.update(self._render_hours_collapsed())
            return

        # Expanded leaderboard
        lines: list[str] = []
        if not self._entries:
            lines.append("[#565f89]No data available[/]")
        else:
            max_hours = max(e.hours for e in self._entries)
            for i, entry in enumerate(self._entries, 1):
                is_current = entry.user == self.current_user

                # Podium colours: gold / silver / bronze / muted
                if i == 1:
                    rank_color = "#e0af68"
                elif i == 2:
                    rank_color = "#c0caf5"
                elif i == 3:
                    rank_color = "#bb9af7"
                else:
                    rank_color = "#565f89"

                user_color = "#9ece6a" if is_current else "#c0caf5"
                hours_color = "#9ece6a" if is_current else "#565f89"
                bar_color = "#9ece6a" if is_current else "#7aa2f7"
                marker = " ←" if is_current else ""

                bar = make_hours_bar(entry.hours, max_hours)
                lines.append(
                    f"[{rank_color}]{i:2}.[/]"
                    f"[{user_color}]{entry.user[:10]:<10}[/]  "
                    f"[{hours_color}]{entry.hours:>8,.0f}[/]  "
                    f"[{bar_color}]{bar}[/]"
                    f"[#9ece6a]{marker}[/]"
                )

        content.update("\n".join(lines))

    def _render_hours_collapsed(self) -> str:
        """Build the one-liner summary for the collapsed hours view."""
        parts = ["[#565f89]Top 10[/]"]

        # Highlight the current user's rank and hours
        for i, entry in enumerate(self._entries, 1):
            if entry.user == self.current_user:
                parts.append(f"[#565f89]·[/]  [#9ece6a]#{i} {entry.hours:,.0f}h[/]")
                break

        return "  ".join(parts)

    # ── Running rendering ─────────────────────────────────────────

    @staticmethod
    def _parse_mem_gb(mem_str: str) -> float:
        """Parse a SLURM memory string like '4G', '16384M' to GB."""
        mem_str = mem_str.strip()
        if not mem_str or mem_str == "0":
            return 0.0
        try:
            if mem_str.endswith("G"):
                return float(mem_str[:-1])
            if mem_str.endswith("M"):
                return float(mem_str[:-1]) / 1024
            if mem_str.endswith("K"):
                return float(mem_str[:-1]) / (1024 * 1024)
            if mem_str.endswith("T"):
                return float(mem_str[:-1]) * 1024
            return float(mem_str) / 1024  # plain number = MB
        except ValueError:
            return 0.0

    def _render_running(self) -> None:
        """Re-render the running-jobs one-liner summary."""
        try:
            section = self.query_one("#running-section", Container)
            content = self.query_one(".running-content", Static)
        except Exception:
            return

        # Hidden → collapse the entire section container
        if not self._running_visible:
            section.display = False
            return

        section.display = True

        if not self._running_jobs:
            content.update("")
            return

        total_gpus = sum(j.gpus for j in self._running_jobs)
        total_cpus = sum(j.cpus for j in self._running_jobs)
        total_ram = sum(self._parse_mem_gb(j.memory) for j in self._running_jobs)

        content.update(
            f"[#565f89]── [/][#9ece6a]Running[/]  "
            f"[#565f89]{len(self._running_jobs)} jobs  ·  "
            f"{total_gpus} GPUs  ·  {total_cpus} CPUs  ·  "
            f"{total_ram:.0f}G RAM[/]  "
            f"[#414868]o to toggle[/]"
        )

    # ── Toggle methods (called by MainScreen actions) ─────────────

    def _sync_widget_visibility(self) -> None:
        """Hide the entire widget when both sections are hidden, show otherwise."""
        self.display = self._hours_visible or self._running_visible

    def toggle_hours_visible(self) -> None:
        """Toggle entire GPU hours section visibility (h key)."""
        self._hours_visible = not self._hours_visible
        self._render_hours()
        self._sync_widget_visibility()

    def toggle_running_visible(self) -> None:
        """Toggle running-jobs summary line visibility (o key)."""
        self._running_visible = not self._running_visible
        self._render_running()
        self._sync_widget_visibility()

    # Legacy alias — kept so MainScreen doesn't break if called.
    def toggle_expanded(self) -> None:
        """Alias for toggle_running_visible (expanded view was removed)."""
        self.toggle_running_visible()
