"""GPU Monitor Widget - shows GPU allocation per partition."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Static, ProgressBar, Label
from textual.widget import Widget

from ..utils.gpu import GPUMonitor, PartitionGPU


class PartitionRow(Static):
    """A single partition row with progress bar."""

    DEFAULT_CSS = """
    PartitionRow {
        layout: horizontal;
        height: 1;
        margin: 0 1;
    }

    PartitionRow .partition-name {
        width: 6;
        text-style: bold;
    }

    PartitionRow .partition-count {
        width: 10;
        text-align: right;
    }

    PartitionRow .partition-bar {
        width: 1fr;
        margin: 0 1;
    }

    PartitionRow .partition-percent {
        width: 7;
        text-align: right;
    }
    """

    def __init__(self, partition: PartitionGPU):
        super().__init__()
        self.partition = partition

    def compose(self) -> ComposeResult:
        yield Label(self.partition.partition, classes="partition-name")
        yield Label(
            f"{self.partition.allocated}/{self.partition.total}",
            classes="partition-count",
        )
        bar = ProgressBar(total=100, show_eta=False, show_percentage=False)
        bar.add_class("partition-bar")
        bar.progress = self.partition.usage_percent
        yield bar
        yield Label(f"{self.partition.usage_percent:5.1f}%", classes="partition-percent")

    def update_partition(self, partition: PartitionGPU) -> None:
        """Update the partition data."""
        self.partition = partition
        self.query_one(".partition-count", Label).update(
            f"{partition.allocated}/{partition.total}"
        )
        self.query_one(".partition-bar", ProgressBar).progress = partition.usage_percent
        self.query_one(".partition-percent", Label).update(
            f"{partition.usage_percent:5.1f}%"
        )


class GPUMonitorWidget(Widget):
    """Widget showing GPU allocation per partition with auto-refresh."""

    DEFAULT_CSS = """
    GPUMonitorWidget {
        border: solid $primary;
        height: auto;
        padding: 0 1;
    }

    GPUMonitorWidget > .gpu-title {
        text-style: bold;
        color: $text;
        padding: 0 0 1 0;
    }

    GPUMonitorWidget > .gpu-header {
        layout: horizontal;
        height: 1;
        margin: 0 1;
        color: $text-muted;
    }

    GPUMonitorWidget > .gpu-header .header-name {
        width: 6;
    }

    GPUMonitorWidget > .gpu-header .header-alloc {
        width: 10;
        text-align: right;
    }

    GPUMonitorWidget > .gpu-header .header-usage {
        width: 1fr;
        text-align: center;
    }

    GPUMonitorWidget > .gpu-header .header-percent {
        width: 7;
        text-align: right;
    }

    GPUMonitorWidget .no-data {
        color: $text-muted;
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
        yield Static("GPU Allocation (auto-refresh 10s)", classes="gpu-title")
        yield Static(
            "[Part  ] [Alloc   ] [Usage                ] [   %  ]",
            classes="gpu-header",
        )

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
