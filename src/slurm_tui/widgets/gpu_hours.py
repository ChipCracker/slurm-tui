"""GPU Hours Widget - shows GPU hours per user."""

from __future__ import annotations

import os
from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Static
from textual.widget import Widget

from ..utils.gpu import GPUMonitor, GPUHoursEntry


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
        min-height: 8;
        padding: 0 2;
        margin: 0 0 1 0;
    }

    GPUHoursWidget > .section-header {
        layout: horizontal;
        height: 1;
        margin-bottom: 0;
    }

    GPUHoursWidget > .section-header > .section-title {
        width: 1fr;
        color: #565f89;
    }

    GPUHoursWidget > .section-header > .section-info {
        width: auto;
        color: #414868;
    }

    GPUHoursWidget > .separator {
        color: #414868;
        margin-bottom: 1;
    }

    GPUHoursWidget > .hours-row {
        layout: horizontal;
        height: 1;
        padding: 0;
    }

    GPUHoursWidget > .hours-row > .h-rank {
        width: 3;
        color: #565f89;
    }

    GPUHoursWidget > .hours-row > .h-user {
        width: 12;
        color: #c0caf5;
    }

    GPUHoursWidget > .hours-row > .h-hours {
        width: 10;
        text-align: right;
        color: #565f89;
        padding-right: 2;
    }

    GPUHoursWidget > .hours-row > .h-bar {
        width: 22;
    }

    GPUHoursWidget > .hours-row > .h-marker {
        width: 3;
        color: #9ece6a;
    }

    GPUHoursWidget .no-data {
        color: #565f89;
        text-style: italic;
    }
    """

    entries: reactive[list[GPUHoursEntry]] = reactive(list, recompose=True)

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

    def compose(self) -> ComposeResult:
        year = datetime.now().year

        # Section header
        with Horizontal(classes="section-header"):
            yield Static(f"GPU Hours {year}", classes="section-title")
            yield Static("Top 10", classes="section-info")

        # Separator line
        yield Static("─" * 56, classes="separator")

        if not self.entries:
            yield Static("No data available", classes="no-data")
        else:
            # Get max hours for bar scaling
            max_hours = max(e.hours for e in self.entries) if self.entries else 1

            for i, entry in enumerate(self.entries, 1):
                is_current = entry.user == self.current_user

                # Rank color
                if i == 1:
                    rank_color = "#e0af68"  # gold
                elif i == 2:
                    rank_color = "#c0caf5"  # silver
                elif i == 3:
                    rank_color = "#bb9af7"  # bronze/purple
                else:
                    rank_color = "#565f89"

                # User color - highlight current user
                user_color = "#9ece6a" if is_current else "#c0caf5"
                hours_color = "#9ece6a" if is_current else "#565f89"
                bar_color = "#9ece6a" if is_current else "#7aa2f7"

                # Marker for current user
                marker = "←" if is_current else ""

                with Horizontal(classes="hours-row"):
                    yield Static(f"[{rank_color}]{i:2}.[/]", classes="h-rank")
                    yield Static(
                        f"[{user_color}]{entry.user[:10]:<10}[/]",
                        classes="h-user",
                    )
                    yield Static(
                        f"[{hours_color}]{entry.hours:>8,.0f}h[/]",
                        classes="h-hours",
                    )
                    yield Static(
                        f"[{bar_color}]{make_hours_bar(entry.hours, max_hours)}[/]",
                        classes="h-bar",
                    )
                    yield Static(f"[#9ece6a]{marker}[/]", classes="h-marker")

    def on_mount(self) -> None:
        """Start timer and load initial data."""
        self.refresh_data()
        self._timer = self.set_interval(self.refresh_interval, self.refresh_data)

    def refresh_data(self) -> None:
        """Refresh GPU hours data."""
        try:
            self.entries = self.gpu_monitor.get_gpu_hours(limit=10)
        except Exception:
            pass
