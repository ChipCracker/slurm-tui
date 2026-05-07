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

# Warm, muted "earth tones" palette — sage, cream, coral, mauve.
# Mine = green family, Other = red/coral family. Preempt variants are
# softer/lighter than their non-preempt counterparts.
COLOR_NEUTRAL           = "#d8b48a"  # warm tan — plain "allocated"
COLOR_NON_PREEMPT       = "#c97a6e"  # muted coral — protected
COLOR_PREEMPT           = "#a89c8a"  # warm taupe — preemptible
COLOR_OWN               = "#a3be8c"  # sage green — own GPUs
COLOR_OTHER             = "#c97a6e"  # muted coral — other users' GPUs
COLOR_OWN_NON_PREEMPT   = "#a3be8c"  # sage green — own protected
COLOR_OWN_PREEMPT       = "#d8c89c"  # warm cream — own killable
COLOR_OTHER_NON_PREEMPT = "#c97a6e"  # muted coral — other protected
COLOR_OTHER_PREEMPT     = "#9c8aa3"  # dusty mauve — other killable


def _bar_segments(
    partition: PartitionGPU,
    show_preempt: bool,
    show_own: bool,
    width: int = 25,
) -> list[tuple[int, str]]:
    """Return a list of (gpu_count, color) segments for the bar.

    Order matters — segments are rendered left-to-right in this order.
    """
    if show_preempt and show_own:
        return [
            (partition.own_non_preemptible, COLOR_OWN_NON_PREEMPT),
            (partition.own_preemptible, COLOR_OWN_PREEMPT),
            (partition.other_non_preemptible, COLOR_OTHER_NON_PREEMPT),
            (partition.other_preemptible, COLOR_OTHER_PREEMPT),
        ]
    if show_preempt:
        return [
            (partition.non_preemptible, COLOR_NON_PREEMPT),
            (partition.preemptible, COLOR_PREEMPT),
        ]
    if show_own:
        return [
            (partition.own_allocated, COLOR_OWN),
            (partition.other_allocated, COLOR_OTHER),
        ]
    return [(partition.allocated, COLOR_NEUTRAL)]


def make_gradient_bar(
    partition: PartitionGPU,
    show_preempt: bool = True,
    show_own: bool = False,
    width: int = 25,
) -> str:
    """Create a multi-segment progress bar for a partition.

    Segment widths are computed in proportion to the partition's total GPU
    count so empty space at the end is always correct, even when the
    overlays slice the same allocation differently.
    """
    if partition.total <= 0:
        return "░" * width

    segments = _bar_segments(partition, show_preempt, show_own, width)

    # Convert each segment from gpu-count → character count.
    # Use cumulative rounding so the total never exceeds `width`.
    bar_parts: list[str] = []
    used = 0
    cumulative_gpus = 0
    for count, color in segments:
        cumulative_gpus += count
        target = int(cumulative_gpus / partition.total * width + 0.5)
        seg_chars = max(0, target - used)
        if seg_chars > 0:
            bar_parts.append(f"[{color}]" + "█" * seg_chars + "[/]")
            used += seg_chars

    empty = max(0, width - used)
    if empty > 0:
        bar_parts.append(f"[#565f89]" + "░" * empty + "[/]")

    return "".join(bar_parts)


def _render_legend(show_preempt: bool, show_own: bool) -> str:
    """Build a single-line colour legend matching the active overlay mode."""
    if show_preempt and show_own:
        items = [
            (COLOR_OWN_NON_PREEMPT, "mine"),
            (COLOR_OWN_PREEMPT, "mine·preempt"),
            (COLOR_OTHER_NON_PREEMPT, "other"),
            (COLOR_OTHER_PREEMPT, "other·preempt"),
        ]
    elif show_preempt:
        items = [
            (COLOR_NON_PREEMPT, "non-preempt"),
            (COLOR_PREEMPT, "preempt"),
        ]
    elif show_own:
        items = [
            (COLOR_OWN, "mine"),
            (COLOR_OTHER, "other"),
        ]
    else:
        items = [(COLOR_NEUTRAL, "allocated")]

    parts = [f"[{color}]██[/] [#565f89]{label}[/]" for color, label in items]
    return "  ".join(parts)


def _render_partition_row(
    partition: PartitionGPU,
    show_preempt: bool,
    show_own: bool,
) -> str:
    """Render a partition row as a single Rich markup string."""
    percent = partition.usage_percent
    bar = make_gradient_bar(partition, show_preempt, show_own)

    # Count summary adapts to which overlays are active
    if show_preempt and show_own:
        count_summary = (
            f"[{COLOR_OWN_NON_PREEMPT}]{partition.own_non_preemptible}[/]"
            f"[#565f89]+[/]"
            f"[{COLOR_OWN_PREEMPT}]{partition.own_preemptible}[/]"
            f"[#565f89]/[/]"
            f"[{COLOR_OTHER_NON_PREEMPT}]{partition.other_non_preemptible}[/]"
            f"[#565f89]+[/]"
            f"[{COLOR_OTHER_PREEMPT}]{partition.other_preemptible}[/]"
        )
    elif show_preempt:
        count_summary = (
            f"[{COLOR_NON_PREEMPT}]{partition.non_preemptible}[/]"
            f"[#565f89]+[/]"
            f"[{COLOR_PREEMPT}]{partition.preemptible}[/]"
        )
    elif show_own:
        count_summary = (
            f"[{COLOR_OWN}]{partition.own_allocated}[/]"
            f"[#565f89]+[/]"
            f"[{COLOR_OTHER}]{partition.other_allocated}[/]"
        )
    else:
        count_summary = f"[{COLOR_NEUTRAL}]{partition.allocated:2}[/]"

    return (
        f"[#c0caf5]{partition.partition:<4}[/]"
        f"{count_summary}"
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
        """Initialise GPU monitor with optional monitor instance and refresh interval."""
        super().__init__(**kwargs)
        self.gpu_monitor = gpu_monitor or GPUMonitor()
        self.refresh_interval = refresh_interval
        self._timer = None
        self._detail_index: int = -1
        self.partitions: list[PartitionGPU] = []
        # Default-on: zeige direkt die 4-Bucket-Aufteilung
        # (mine / mine-preempt / other / other-preempt).
        self.show_preempt_overlay: bool = True
        self.show_own_overlay: bool = True

    def compose(self) -> ComposeResult:
        """Compose the header, separator, and content area."""
        with Horizontal(classes="section-header"):
            yield Static("GPU Allocation", classes="section-title")
            yield Static(f"{int(self.refresh_interval)}s", classes="section-info")

        yield Static("─" * 56, classes="separator")
        yield Static("No partition data available", classes="partition-content")

    def on_mount(self) -> None:
        """Start auto-refresh timer on mount (1s offset to let job table load first)."""
        self.set_timer(1.0, self._start_refresh)

    def _start_refresh(self) -> None:
        """Kick off the first data fetch and schedule the periodic refresh timer."""
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
        self._render_partitions()

    def _render_partitions(self) -> None:
        """Re-render the partition rows from cached data (no fetch)."""
        content = self.query_one(".partition-content", Static)
        if not self.partitions:
            content.update("No partition data available")
            return
        lines = [
            _render_partition_row(p, self.show_preempt_overlay, self.show_own_overlay)
            for p in self.partitions
        ]
        # Append a colour legend so the meaning of the bar segments is
        # always visible (and updates when toggles change).
        lines.append(_render_legend(self.show_preempt_overlay, self.show_own_overlay))
        content.update("\n".join(lines))

    def toggle_preempt_overlay(self) -> bool:
        """Toggle the preemptible/non-preemptible colour overlay. Returns new state."""
        self.show_preempt_overlay = not self.show_preempt_overlay
        self._render_partitions()
        return self.show_preempt_overlay

    def toggle_own_overlay(self) -> bool:
        """Toggle the own/other colour overlay. Returns new state."""
        self.show_own_overlay = not self.show_own_overlay
        self._render_partitions()
        return self.show_own_overlay

    def cycle_partition_detail(self) -> PartitionGPU | None:
        """Cycle through partitions for detail view. Returns selected partition or None."""
        if not self.partitions:
            return None
        self._detail_index += 1
        if self._detail_index >= len(self.partitions):
            self._detail_index = -1
            return None
        return self.partitions[self._detail_index]
