"""GPU Hours Widget - shows GPU hours per user."""

from __future__ import annotations

import os
from datetime import datetime

from textual import work
from textual.app import ComposeResult
from textual.widgets import Static
from textual.widget import Widget
from textual.worker import get_current_worker

from ..utils.gpu import GPUMonitor, GPUHoursEntry
from ..utils.slurm import Job


def make_hours_bar(hours: float, max_hours: float, width: int = 20) -> str:
    """Create a horizontal bar for GPU hours."""
    if max_hours <= 0:
        return "░" * width
    percent = min(hours / max_hours, 1.0)
    filled = int(percent * width)
    empty = width - filled
    return "█" * filled + "░" * empty


class GPUHoursWidget(Widget):
    """Widget showing GPU hours per user."""

    DEFAULT_CSS = """
    GPUHoursWidget {
        background: transparent;
        border: none;
        height: auto;
        padding: 0 2;
        margin: 0 0 1 0;
    }

    GPUHoursWidget > .hours-all {
        height: auto;
    }

    GPUHoursWidget > .running-section {
        color: #565f89;
        height: auto;
        margin-top: 1;
    }
    """

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
        self._expanded: bool = False
        self._hours_collapsed: bool = True

    def compose(self) -> ComposeResult:
        yield Static(self._render_hours_collapsed(), classes="hours-all")
        yield Static("", classes="running-section")

    def on_mount(self) -> None:
        """Start timer and load initial data (5s offset — sreport is slow, load last)."""
        self.set_timer(5.0, self._start_refresh)

    def _start_refresh(self) -> None:
        self.refresh_data()
        self._timer = self.set_interval(self.refresh_interval, self.refresh_data)

    @work(thread=True, exclusive=True)
    def refresh_data(self) -> None:
        """Refresh GPU hours in background thread."""
        worker = get_current_worker()
        try:
            entries = self.gpu_monitor.get_gpu_hours(limit=10)
            if not worker.is_cancelled:
                self.app.call_from_thread(self._apply_hours, entries)
        except Exception:
            pass

    def _apply_hours(self, entries: list[GPUHoursEntry]) -> None:
        """Update GPU hours display imperatively."""
        self._entries = entries
        self._render_hours()

    def _get_width(self) -> int:
        """Get available content width."""
        try:
            return self.content_size.width or 56
        except Exception:
            return 56

    def _render_collapsed_lines(self) -> tuple[str, str]:
        """Render both collapsed lines with aligned columns.

        Layout:
          ── GPU Hours 2026  Top 10   ·  #3 10,129h  ·  h to expand
          ── Running Jobs    19 jobs  ·  22 GPUs      ·  o to expand
        """
        year = datetime.now().year
        w = self._get_width()

        # Column 1: label (padded to same width)
        h_label = f"GPU Hours {year}"
        r_label = "Running Jobs"
        col1_w = max(len(h_label), len(r_label))

        # Column 2: first info
        h_col2 = "Top 10"
        n_jobs = len(self._running_jobs)
        r_col2 = f"{n_jobs} jobs"
        col2_w = max(len(h_col2), len(r_col2))

        # Column 3: second info
        user_plain = ""
        user_rich = ""
        for i, entry in enumerate(self._entries, 1):
            if entry.user == self.current_user:
                user_plain = f"#{i} {entry.hours:,.0f}h"
                user_rich = f"[#9ece6a]{user_plain}[/]"
                break
        total_gpus = sum(j.gpus for j in self._running_jobs)
        r_col3 = f"{total_gpus} GPUs"
        h_col3 = user_plain
        col3_w = max(len(h_col3), len(r_col3)) if (h_col3 or r_col3) else 0

        # Column 4: third info (only running)
        total_cpus = sum(j.cpus for j in self._running_jobs)
        r_col4 = f"{total_cpus} CPUs"

        # Hints right-aligned
        h_hint = "h to expand"
        r_hint = "o to expand"
        hint_len = max(len(h_hint), len(r_hint))

        # Build hours line
        h_parts_plain = f"── {h_label:<{col1_w}}  {h_col2:<{col2_w}}"
        h_parts_rich = (
            f"[#565f89]── [/][#7aa2f7]{h_label:<{col1_w}}[/]  "
            f"[#565f89]{h_col2:<{col2_w}}[/]"
        )
        if user_rich:
            h_parts_plain += f"  ·  {h_col3:<{col3_w}}"
            h_parts_rich += f"  [#565f89]·[/]  {user_rich}{' ' * max(0, col3_w - len(h_col3))}"

        h_pad = max(2, w - len(h_parts_plain) - hint_len)
        hours_line = f"{h_parts_rich}{' ' * h_pad}[#414868]{h_hint}[/]"

        # Build running line
        if not self._running_jobs:
            return hours_line, ""

        r_parts_plain = f"── {r_label:<{col1_w}}  {r_col2:<{col2_w}}  ·  {r_col3:<{col3_w}}  ·  {r_col4}"
        r_parts_rich = (
            f"[#565f89]── [/][#9ece6a]{r_label:<{col1_w}}[/]  "
            f"[#565f89]{r_col2:<{col2_w}}  ·  {r_col3:<{col3_w}}  ·  {r_col4}[/]"
        )
        r_pad = max(2, w - len(r_parts_plain) - hint_len)
        running_line = f"{r_parts_rich}{' ' * r_pad}[#414868]{r_hint}[/]"

        return hours_line, running_line

    def _render_hours_collapsed(self) -> str:
        """Single-line collapsed view."""
        return self._render_collapsed_lines()[0]

    def _render_hours(self) -> None:
        """Render hours content based on current state."""
        try:
            content = self.query_one(".hours-all", Static)
        except Exception:
            return

        if self._hours_collapsed:
            content.update(self._render_hours_collapsed())
            return

        year = datetime.now().year
        lines = [
            f"[#565f89]GPU Hours {year}[/]                          [#414868]Top 10[/]",
            "[#414868]" + "─" * 56 + "[/]",
        ]

        if not self._entries:
            lines.append("[#565f89]No data available[/]")
        else:
            max_hours = max(e.hours for e in self._entries)
            for i, entry in enumerate(self._entries, 1):
                is_current = entry.user == self.current_user

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

    def _render_running(self) -> str:
        """Build Rich markup for the running jobs section."""
        if not self._running_jobs:
            return ""

        total_gpus = sum(j.gpus for j in self._running_jobs)
        total_cpus = sum(j.cpus for j in self._running_jobs)

        if not self._expanded:
            _, running_line = self._render_collapsed_lines()
            return running_line

        lines = [
            f"Running ({len(self._running_jobs)} jobs, {total_gpus} GPUs)",
            "[#414868]" + "─" * 56 + "[/]",
        ]
        for job in self._running_jobs[:8]:
            gpu_str = f"{job.gpus}×GPU" if job.gpus > 0 else "  —  "
            runtime = job.runtime if job.runtime and job.runtime != "0:00" else "—"
            lines.append(
                f"[#c0caf5]{job.name[:18]:<18}[/]  "
                f"[#7dcfff]{job.partition:<6}[/]  "
                f"[#bb9af7]{gpu_str:>5}[/]  "
                f"[#565f89]{runtime:>10}[/]"
            )
        if len(self._running_jobs) > 8:
            lines.append(f"[#565f89]  +{len(self._running_jobs) - 8} more...[/]")

        return "\n".join(lines)

    def _update_running_section(self) -> None:
        """Update the running section Static widget."""
        try:
            section = self.query_one(".running-section", Static)
            section.update(self._render_running())
            # Re-render hours collapsed line too so columns stay aligned
            if self._hours_collapsed:
                content = self.query_one(".hours-all", Static)
                content.update(self._render_hours_collapsed())
        except Exception:
            pass

    def update_running_jobs(self, jobs: list[Job]) -> None:
        """Update running jobs from external source (e.g. JobTableWidget)."""
        self._running_jobs = [j for j in jobs if j.state == "R"]
        self._update_running_section()

    def toggle_hours(self) -> None:
        """Toggle GPU hours list collapsed/expanded."""
        self._hours_collapsed = not self._hours_collapsed
        self._render_hours()

    def toggle_expanded(self) -> None:
        """Toggle between compact and expanded running jobs view."""
        self._expanded = not self._expanded
        self._update_running_section()
