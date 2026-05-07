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


def make_gradient_bar(percent: float, non_preempt_percent: float = 0.0, width: int = 25) -> str:
    """Create a two-tone progress bar: red for non-preemptible, yellow for preemptible."""
    non_preempt_chars = int(non_preempt_percent / 100 * width + 0.5)
    total_filled = int(percent / 100 * width + 0.5)
    preempt_chars = total_filled - non_preempt_chars
    empty = width - total_filled

    bar = (
        f"[#f7768e]" + "█" * non_preempt_chars + "[/]"
        + f"[#e0af68]" + "▒" * preempt_chars + "[/]"
        + "░" * empty
    )
    return bar


def _render_partition_row(partition: PartitionGPU) -> str:
    """Render a partition row as a single Rich markup string."""
    percent = partition.usage_percent
    bar = make_gradient_bar(percent, partition.non_preemptible_percent)
    preempt = partition.preemptible
    return (
        f"[#c0caf5]{partition.partition:<4}[/]"
        f"[#f7768e]{partition.non_preemptible:1}[/]"
        f"[#565f89]+[/]"
        f"[#e0af68]{preempt:1}[/]"
        f"[#565f89]/{partition.total:2}[/]  "
        f"{bar}  "
        f"[#c0caf5]{percent:5.1f}%[/]"
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
