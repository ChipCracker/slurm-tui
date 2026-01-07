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
        border: solid $secondary;
        height: auto;
        min-height: 10;
        padding: 0 1;
    }

    GPUHoursWidget > .hours-title {
        text-style: bold;
        color: $text;
        padding: 0 0 1 0;
    }

    GPUHoursWidget > DataTable {
        height: auto;
        max-height: 12;
    }

    GPUHoursWidget .no-data {
        color: $text-muted;
        text-style: italic;
        padding: 1;
    }

    GPUHoursWidget .current-user {
        text-style: bold;
        color: $success;
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
        yield Static(f"GPU Hours ({year})", classes="hours-title")

        table = DataTable(zebra_stripes=True)
        table.cursor_type = "row"
        table.add_columns("#", "User", "Hours", "Account")
        yield table

    def on_mount(self) -> None:
        """Start timer and load initial data."""
        self.refresh_data()
        self._timer = self.set_interval(self.refresh_interval, self.refresh_data)

    def refresh_data(self) -> None:
        """Refresh GPU hours data."""
        try:
            self.entries = self.gpu_monitor.get_gpu_hours(limit=15)
            self._update_table()
        except Exception:
            pass

    def _update_table(self) -> None:
        """Update the data table with current entries."""
        table = self.query_one(DataTable)
        table.clear()

        for i, entry in enumerate(self.entries, 1):
            is_current = entry.user == self.current_user
            user_display = f"[bold green]{entry.user}[/]" if is_current else entry.user
            hours_display = f"[bold green]{entry.hours:,.1f}[/]" if is_current else f"{entry.hours:,.1f}"

            table.add_row(
                str(i),
                user_display,
                hours_display,
                entry.account,
            )
