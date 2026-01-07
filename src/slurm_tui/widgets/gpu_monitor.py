"""GPU Monitor Widget - shows GPU allocation per partition."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Static
from textual.widget import Widget

from ..utils.gpu import GPUMonitor, PartitionGPU


# Unicode block characters for gradient-style progress bar
BLOCKS = " ▁▂▃▄▅▆▇█"


def make_gradient_bar(percent: float, width: int = 25) -> str:
    """Create a gradient-style progress bar with Unicode blocks."""
    # Calculate filled and empty portions
    filled_exact = percent / 100 * width
    filled = int(filled_exact)
    partial = filled_exact - filled
    empty = width - filled - (1 if partial > 0 else 0)

    # Color based on usage
    if percent < 50:
        color = "#9ece6a"  # green
    elif percent < 80:
        color = "#e0af68"  # yellow
    else:
        color = "#f7768e"  # red

    # Build the bar with gradient effect
    bar = "█" * filled
    if partial > 0:
        partial_index = int(partial * (len(BLOCKS) - 1))
        bar += BLOCKS[partial_index]
    bar += "░" * empty

    return f"[{color}]{bar}[/]"


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

    GPUMonitorWidget > .partition-row {
        layout: horizontal;
        height: 1;
        padding: 0;
    }

    GPUMonitorWidget > .partition-row > .p-name {
        width: 4;
        color: #c0caf5;
    }

    GPUMonitorWidget > .partition-row > .p-count {
        width: 7;
        text-align: right;
        color: #565f89;
        padding-right: 2;
    }

    GPUMonitorWidget > .partition-row > .p-bar {
        width: 27;
    }

    GPUMonitorWidget > .partition-row > .p-percent {
        width: 6;
        text-align: right;
    }

    GPUMonitorWidget .no-data {
        color: #565f89;
        text-style: italic;
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
        # Section header
        with Horizontal(classes="section-header"):
            yield Static("GPU Allocation", classes="section-title")
            yield Static(f"{int(self.refresh_interval)}s", classes="section-info")

        # Separator line
        yield Static("─" * 56, classes="separator")

        if not self.partitions:
            yield Static("No partition data available", classes="no-data")
        else:
            for partition in self.partitions:
                percent = partition.usage_percent
                # Color for percentage
                if percent < 50:
                    color = "#9ece6a"
                elif percent < 80:
                    color = "#e0af68"
                else:
                    color = "#f7768e"

                with Horizontal(classes="partition-row"):
                    yield Static(f"{partition.partition}", classes="p-name")
                    yield Static(
                        f"{partition.allocated:2}/{partition.total:2}",
                        classes="p-count",
                    )
                    yield Static(make_gradient_bar(percent), classes="p-bar")
                    yield Static(f"[{color}]{percent:5.1f}%[/]", classes="p-percent")

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
