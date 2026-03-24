"""Disk Quota Widget - shows filesystem quota usage."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static
from textual.widget import Widget
from textual.worker import get_current_worker

from ..utils.quota import QuotaMonitor, DiskQuota


BAR_HEIGHT = 8
BAR_WIDTH = 3
COL_WIDTH = 10  # total width per column including padding
BLOCKS = " ▁▂▃▄▅▆▇█"


def _color_for(percent: float) -> str:
    if percent < 50:
        return "#9ece6a"
    elif percent < 80:
        return "#e0af68"
    return "#f7768e"


def _short_fs(filesystem: str) -> str:
    """Shorten filesystem path for display."""
    # Show last component, e.g. /dev/mapper/home -> home
    return filesystem.rstrip("/").rsplit("/", 1)[-1] if "/" in filesystem else filesystem


class DiskQuotaWidget(Widget):
    """Widget showing disk quota usage with auto-refresh."""

    DEFAULT_CSS = """
    DiskQuotaWidget {
        background: transparent;
        border: none;
        height: auto;
        padding: 0 2;
        margin: 0 0 1 0;
    }

    DiskQuotaWidget > .section-header {
        layout: horizontal;
        height: 1;
        margin-bottom: 0;
    }

    DiskQuotaWidget > .section-header > .section-title {
        width: 1fr;
        color: #565f89;
    }

    DiskQuotaWidget > .section-header > .section-info {
        width: auto;
        color: #414868;
    }

    DiskQuotaWidget > .separator {
        color: #414868;
        margin-bottom: 1;
    }

    DiskQuotaWidget > .quota-content {
        height: auto;
        padding: 0;
    }
    """

    def __init__(
        self,
        quota_monitor: QuotaMonitor | None = None,
        refresh_interval: float = 60.0,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.quota_monitor = quota_monitor or QuotaMonitor()
        self.refresh_interval = refresh_interval
        self._timer = None
        self._collapsed = False
        self._quotas: list[DiskQuota] = []

    def compose(self) -> ComposeResult:
        with Horizontal(classes="section-header"):
            yield Static("Disk Quota", classes="section-title")
            yield Static(f"{int(self.refresh_interval)}s", classes="section-info")

        yield Static("─" * 56, classes="separator")
        yield Static("[#565f89]Loading quota data...[/]", classes="quota-content")

    def on_mount(self) -> None:
        """Start auto-refresh timer (6s offset to stagger with other widgets)."""
        self.set_timer(6.0, self._start_refresh)

    def _start_refresh(self) -> None:
        self.refresh_data()
        self._timer = self.set_interval(self.refresh_interval, self.refresh_data)

    @work(thread=True, exclusive=True)
    def refresh_data(self) -> None:
        """Refresh quota data in background thread."""
        worker = get_current_worker()
        try:
            quotas = self.quota_monitor.get_quotas()
            if not worker.is_cancelled:
                self.app.call_from_thread(self._apply_data, quotas)
        except Exception:
            pass

    def _apply_data(self, quotas: list[DiskQuota]) -> None:
        """Update display imperatively."""
        self._quotas = quotas
        content = self.query_one(".quota-content", Static)

        if not quotas:
            content.update("[#565f89]No quota data available[/]")
            return

        if self._collapsed:
            self._render_collapsed(content)
        else:
            self._render_expanded(content)

    def _render_expanded(self, content: Static) -> None:
        """Render vertical bars side by side."""
        if not self._quotas:
            content.update("[#565f89]No quota data[/]")
            return

        # Build vertical bars row by row (top to bottom)
        rows: list[str] = []
        for row in range(BAR_HEIGHT, 0, -1):
            parts = []
            for q in self._quotas:
                pct = q.usage_percent
                color = _color_for(pct)
                filled_rows = pct / 100 * BAR_HEIGHT
                if filled_rows >= row:
                    # Fully filled row
                    block = "█" * BAR_WIDTH
                elif filled_rows >= row - 1:
                    # Partial row — use fractional block
                    frac = filled_rows - (row - 1)
                    idx = int(frac * (len(BLOCKS) - 1))
                    block = BLOCKS[idx] * BAR_WIDTH
                else:
                    # Empty row
                    block = "░" * BAR_WIDTH
                pad = COL_WIDTH - BAR_WIDTH
                parts.append(f"[{color}]{block}[/]{' ' * pad}")
            rows.append("  ".join(parts))

        # Labels row (filesystem name)
        name_parts = []
        for q in self._quotas:
            name = _short_fs(q.filesystem)[:COL_WIDTH]
            name_parts.append(f"[#c0caf5]{name:<{COL_WIDTH}}[/]")
        rows.append("  ".join(name_parts))

        # Percent row
        pct_parts = []
        for q in self._quotas:
            color = _color_for(q.usage_percent)
            pct_str = f"{q.usage_percent:.0f}%"
            size_str = f"{q.used}/{q.quota}"
            label = f"{pct_str} {size_str}"[:COL_WIDTH]
            pct_parts.append(f"[{color}]{label:<{COL_WIDTH}}[/]")
        rows.append("  ".join(pct_parts))

        content.update("\n".join(rows))

    def _render_collapsed(self, content: Static) -> None:
        """Render compact one-line summary."""
        if not self._quotas:
            content.update("[#565f89]No quota data[/]")
            return

        parts = []
        for q in self._quotas:
            name = _short_fs(q.filesystem)
            pct = q.usage_percent
            if pct < 50:
                color = "#9ece6a"
            elif pct < 80:
                color = "#e0af68"
            else:
                color = "#f7768e"
            parts.append(f"[#c0caf5]{name}[/] [{color}]{pct:.0f}%[/]")

        content.update("  ".join(parts) + "  [#414868]f to expand[/]")

    def toggle_collapsed(self) -> None:
        """Toggle between expanded and collapsed view."""
        self._collapsed = not self._collapsed
        content = self.query_one(".quota-content", Static)
        if self._collapsed:
            self._render_collapsed(content)
        else:
            self._render_expanded(content)

    def toggle_visible(self) -> None:
        """Toggle widget visibility."""
        self.display = not self.display
