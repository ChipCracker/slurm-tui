"""GPU Monitor Widget - shows GPU allocation per partition."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Static, Label
from textual.widget import Widget

from ..utils.gpu import GPUMonitor, PartitionGPU


def make_progress_bar(percent: float, width: int = 20) -> str:
    """Create a text-based progress bar with modern characters."""
    filled = int(percent / 100 * width)
    empty = width - filled

    # Color based on usage
    if percent < 50:
        color = "#9ece6a"  # green
    elif percent < 80:
        color = "#e0af68"  # yellow
    else:
        color = "#f7768e"  # red

    bar = "▰" * filled + "▱" * empty
    return f"[{color}]{bar}[/]"


class PartitionRow(Static):
    """A single partition row with progress bar."""

    DEFAULT_CSS = """
    PartitionRow {
        layout: horizontal;
        height: 1;
        padding: 0 1;
    }

    PartitionRow .partition-name {
        width: 5;
        color: #7aa2f7;
        text-style: bold;
    }

    PartitionRow .partition-count {
        width: 8;
        text-align: right;
        color: #565f89;
    }

    PartitionRow .partition-bar {
        width: 24;
        padding: 0 2;
    }

    PartitionRow .partition-percent {
        width: 6;
        text-align: right;
    }
    """

    def __init__(self, partition: PartitionGPU):
        super().__init__()
        self.partition = partition

    def compose(self) -> ComposeResult:
        yield Label(self.partition.partition, classes="partition-name")
        yield Label(
            f"{self.partition.allocated:2}/{self.partition.total}",
            classes="partition-count",
        )
        yield Static(
            make_progress_bar(self.partition.usage_percent),
            classes="partition-bar",
        )
        # Color the percentage based on usage
        percent = self.partition.usage_percent
        if percent < 50:
            color = "#9ece6a"
        elif percent < 80:
            color = "#e0af68"
        else:
            color = "#f7768e"
        yield Static(f"[{color}]{percent:5.1f}%[/]", classes="partition-percent")

    def update_partition(self, partition: PartitionGPU) -> None:
        """Update the partition data."""
        self.partition = partition
        self.query_one(".partition-count", Label).update(
            f"{partition.allocated:2}/{partition.total}"
        )
        self.query_one(".partition-bar", Static).update(
            make_progress_bar(partition.usage_percent)
        )
        percent = partition.usage_percent
        if percent < 50:
            color = "#9ece6a"
        elif percent < 80:
            color = "#e0af68"
        else:
            color = "#f7768e"
        self.query_one(".partition-percent", Static).update(f"[{color}]{percent:5.1f}%[/]")


class GPUMonitorWidget(Widget):
    """Widget showing GPU allocation per partition with auto-refresh."""

    DEFAULT_CSS = """
    GPUMonitorWidget {
        background: #24283b;
        border: round #414868;
        height: auto;
        padding: 1 2;
        margin: 0 0 1 0;
    }

    GPUMonitorWidget > .gpu-title {
        color: #7aa2f7;
        text-style: bold;
        padding: 0 0 1 0;
    }

    GPUMonitorWidget > .gpu-subtitle {
        color: #565f89;
        padding: 0 0 1 0;
    }

    GPUMonitorWidget .no-data {
        color: #565f89;
        text-style: italic;
        padding: 1;
    }
    """

    partitions: reactive[list[PartitionGPU]] = reactive(list, recompose=True)

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

    def compose(self) -> ComposeResult:
        yield Static("GPU Allocation", classes="gpu-title")

        if not self.partitions:
            yield Static("No partition data available", classes="no-data")
        else:
            for partition in self.partitions:
                yield PartitionRow(partition)

    def on_mount(self) -> None:
        """Start auto-refresh timer on mount."""
        self.refresh_data()
        self._timer = self.set_interval(self.refresh_interval, self.refresh_data)

    def refresh_data(self) -> None:
        """Refresh GPU allocation data."""
        try:
            self.partitions = self.gpu_monitor.get_partition_allocation()
        except Exception:
            pass
