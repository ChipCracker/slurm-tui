"""GPU Monitor Widget - shows GPU allocation per partition."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static
from textual.widget import Widget
from textual.worker import get_current_worker

from ..utils.gpu import GPUMonitor, PartitionGPU


# Unicode block characters for gradient-style progress bar
BLOCKS = " ▁▂▃▄▅▆▇█"


def make_gradient_bar(percent: float, width: int = 25) -> str:
    """Create a gradient-style progress bar with Unicode blocks."""
    filled_exact = percent / 100 * width
    filled = int(filled_exact)
    partial = filled_exact - filled
    empty = width - filled - (1 if partial > 0 else 0)

    if percent < 50:
        color = "#9ece6a"
    elif percent < 80:
        color = "#e0af68"
    else:
        color = "#f7768e"

    bar = "█" * filled
    if partial > 0:
        partial_index = int(partial * (len(BLOCKS) - 1))
        bar += BLOCKS[partial_index]
    bar += "░" * empty

    return f"[{color}]{bar}[/]"


def _render_partition_row(partition: PartitionGPU) -> str:
    """Render a partition row as a single Rich markup string."""
    percent = partition.usage_percent
    if percent < 50:
        color = "#9ece6a"
    elif percent < 80:
        color = "#e0af68"
    else:
        color = "#f7768e"

    bar = make_gradient_bar(percent)
    return (
        f"[#c0caf5]{partition.partition:<4}[/]"
        f"[#565f89]{partition.allocated:2}/{partition.total:2}[/]  "
        f"{bar}  "
        f"[{color}]{percent:5.1f}%[/]"
    )


class GPUMonitorWidget(Widget):
    """Widget showing GPU allocation per partition with auto-refresh."""

    DEFAULT_CSS = """
    GPUMonitorWidget {
        background: transparent;
        border: none;
        height: auto;
        padding: 0 2;
        margin: 0 0 1 0;
    }

    GPUMonitorWidget > .section-header {
        layout: horizontal;
        height: 1;
        margin-bottom: 0;
    }

    GPUMonitorWidget > .section-header > .section-title {
        width: 1fr;
        color: #565f89;
    }

    GPUMonitorWidget > .section-header > .section-info {
        width: auto;
        color: #414868;
    }

    GPUMonitorWidget > .separator {
        color: #414868;
        margin-bottom: 1;
    }

    GPUMonitorWidget > .partition-content {
        height: auto;
        padding: 0;
    }

    GPUMonitorWidget .no-data {
        color: #565f89;
        text-style: italic;
    }
    """

    def __init__(
        self,
        gpu_monitor: GPUMonitor | None = None,
        refresh_interval: float = 10.0,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.gpu_monitor = gpu_monitor or GPUMonitor()
        self.refresh_interval = refresh_interval
        self._timer = None
        self._detail_index: int = -1
        self.partitions: list[PartitionGPU] = []

    def compose(self) -> ComposeResult:
        with Horizontal(classes="section-header"):
            yield Static("GPU Allocation", classes="section-title")
            yield Static(f"{int(self.refresh_interval)}s", classes="section-info")

        yield Static("─" * 56, classes="separator")
        yield Static("No partition data available", classes="partition-content")

    def on_mount(self) -> None:
        """Start auto-refresh timer on mount (1s offset to let job table load first)."""
        self.set_timer(1.0, self._start_refresh)

    def _start_refresh(self) -> None:
        self.refresh_data()
        self._timer = self.set_interval(self.refresh_interval, self.refresh_data)

    @work(thread=True, exclusive=True)
    def refresh_data(self) -> None:
        """Refresh GPU allocation data in background thread."""
        worker = get_current_worker()
        try:
            partitions = self.gpu_monitor.get_partition_allocation()
            if not worker.is_cancelled:
                self.app.call_from_thread(self._apply_data, partitions)
        except Exception:
            pass

    def _apply_data(self, partitions: list[PartitionGPU]) -> None:
        """Update partition display imperatively — no recompose."""
        self.partitions = partitions
        content = self.query_one(".partition-content", Static)
        if not partitions:
            content.update("No partition data available")
            return
        lines = [_render_partition_row(p) for p in partitions]
        content.update("\n".join(lines))

    def cycle_partition_detail(self) -> PartitionGPU | None:
        """Cycle through partitions for detail view. Returns selected partition or None."""
        if not self.partitions:
            return None
        self._detail_index += 1
        if self._detail_index >= len(self.partitions):
            self._detail_index = -1
            return None
        return self.partitions[self._detail_index]
