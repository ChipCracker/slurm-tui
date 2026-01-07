"""GPU Hours Widget - shows GPU hours per user."""

from __future__ import annotations

import os
from datetime import datetime

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static, DataTable
from textual.widget import Widget

from ..utils.gpu import GPUMonitor, GPUHoursEntry


class GPUHoursWidget(Widget):
    """Widget showing GPU hours per user."""

    DEFAULT_CSS = """
    GPUHoursWidget {
        background: #24283b;
        border: round #414868;
        height: auto;
        min-height: 10;
        padding: 1 2;
        margin: 0 0 1 0;
    }

    GPUHoursWidget > .hours-title {
        color: #bb9af7;
        text-style: bold;
        padding: 0 0 1 0;
    }

    GPUHoursWidget > DataTable {
        height: auto;
        max-height: 10;
        background: transparent;
    }

    GPUHoursWidget .no-data {
        color: #565f89;
        text-style: italic;
        padding: 1;
    }
    """

    entries: reactive[list[GPUHoursEntry]] = reactive(list)

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
        yield Static(f"GPU Hours {year}", classes="hours-title")

        table = DataTable(zebra_stripes=True)
        table.cursor_type = "row"
        table.add_columns("", "User", "Hours")
        yield table

    def on_mount(self) -> None:
        """Start timer and load initial data."""
        self.refresh_data()
        self._timer = self.set_interval(self.refresh_interval, self.refresh_data)

    def refresh_data(self) -> None:
        """Refresh GPU hours data."""
        try:
            self.entries = self.gpu_monitor.get_gpu_hours(limit=10)
            self._update_table()
        except Exception:
            pass

    def _update_table(self) -> None:
        """Update the data table with current entries."""
        table = self.query_one(DataTable)
        table.clear()

        for i, entry in enumerate(self.entries, 1):
            is_current = entry.user == self.current_user

            # Rank indicator
            if i == 1:
                rank = "[#e0af68]1.[/]"
            elif i == 2:
                rank = "[#565f89]2.[/]"
            elif i == 3:
                rank = "[#9d7cd8]3.[/]"
            else:
                rank = f"[#414868]{i}.[/]"

            # User with highlight for current
            if is_current:
                user_display = f"[#9ece6a bold]{entry.user}[/]"
                hours_display = f"[#9ece6a bold]{entry.hours:,.0f}h[/]"
            else:
                user_display = f"[#c0caf5]{entry.user}[/]"
                hours_display = f"[#565f89]{entry.hours:,.0f}h[/]"

            table.add_row(rank, user_display, hours_display)
