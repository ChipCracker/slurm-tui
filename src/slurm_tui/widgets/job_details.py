"""Job Details Widget - right panel showing script, logs, partition info, or GPU stats.

This widget serves multiple views depending on context:
    1. Job details   — script (read-only by default) + stderr/stdout logs
    2. Partition info — node list with GPU/CPU/memory details
    3. Live GPU stats — per-GPU utilization, VRAM, power, temperature

Performance design:
    - All file I/O and subprocess calls run in @work(thread=True) workers.
    - Log refresh is incremental (append-only via LogTail) to avoid
      re-reading the entire file every cycle.
    - GPU stats and partition details use Static.update() (imperative)
      instead of rebuilding the widget tree.
    - Script is read-only by default to prevent accidental edits;
      Ctrl+E toggles into edit mode.
    - Smart auto-scroll: logs only scroll to bottom if the user was
      already at the bottom, preserving manual scroll position.
"""

from __future__ import annotations

import os
import subprocess

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Static, TextArea
from textual.widget import Widget
from textual.worker import get_current_worker

from ..utils.slurm import SlurmClient, Job
from ..utils.gpu import GPUMonitor, PartitionGPU, NodeGPU, GPUStats
from ..utils.bookmarks import BookmarkManager
from ..utils.log_reader import LogTail, read_log_incremental


def _color_for(percent: float) -> str:
    """Return a Tokyo Night color based on percentage thresholds."""
    if percent < 50:
        return "#9ece6a"   # green
    elif percent < 80:
        return "#e0af68"   # yellow
    else:
        return "#f7768e"   # red


def _make_bar(percent: float, width: int = 20) -> str:
    """Create a color-coded progress bar (█ filled, ░ empty)."""
    color = _color_for(percent)
    filled = int(min(percent, 100) / 100 * width)
    empty = width - filled
    return f"[{color}]{'█' * filled}{'░' * empty}[/]"


class JobDetailsWidget(Widget):
    """Right panel widget with multiple view modes.

    View modes (mutually exclusive):
        - Job details: script + logs (default when a job is selected)
        - Partition details: node table (activated by 'g' key)
        - GPU stats: live nvidia-smi output (activated by 'v' key)
    """

    DEFAULT_CSS = """
    JobDetailsWidget {
        background: transparent;
        border: none;
        height: 1fr;
        padding: 0 2;
        border-left: solid #414868;
    }

    JobDetailsWidget > .details-title {
        color: #7aa2f7;
        text-style: bold;
        height: auto;
    }

    JobDetailsWidget > .separator {
        color: #414868;
        height: auto;
    }

    JobDetailsWidget > #content-container {
        height: 1fr;
        background: transparent;
    }

    JobDetailsWidget .section-label {
        color: #565f89;
        margin-top: 1;
        height: auto;
    }

    JobDetailsWidget .script-path {
        color: #9ece6a;
        height: auto;
    }

    JobDetailsWidget .no-job {
        color: #565f89;
        text-style: italic;
        text-align: center;
        padding: 2;
        height: auto;
    }

    JobDetailsWidget .not-your-job {
        color: #e0af68;
        text-align: center;
        padding: 2;
        height: auto;
    }

    JobDetailsWidget .loading {
        color: #565f89;
        text-style: italic;
        text-align: center;
        padding: 2;
        height: auto;
    }

    JobDetailsWidget TextArea {
        height: 1fr;
        background: #1e2030;
        border: solid #414868;
        min-height: 5;
    }

    JobDetailsWidget TextArea:focus {
        border: solid #7aa2f7;
        background: #24283b;
    }

    JobDetailsWidget .script-area {
        max-height: 40%;
    }

    JobDetailsWidget .script-area:focus {
        border: solid #9ece6a;
    }

    JobDetailsWidget .logs-area {
        height: 1fr;
    }

    JobDetailsWidget .script-modified {
        border: solid #e0af68;
    }

    JobDetailsWidget .script-header {
        color: #565f89;
        margin-top: 1;
        height: auto;
    }

    JobDetailsWidget .script-header-modified {
        color: #e0af68;
    }
    """

    BINDINGS = [
        ("ctrl+s", "save_script", "Save Script"),
        ("b", "bookmark_script", "Bookmark Script"),
        ("Y", "copy_logs", "Copy Logs"),
    ]

    def __init__(
        self,
        slurm_client: SlurmClient | None = None,
        bookmark_manager: BookmarkManager | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.slurm_client = slurm_client or SlurmClient()
        self.bookmark_manager = bookmark_manager or BookmarkManager()

        # Current view state
        self._current_job: Job | None = None
        self._is_own_job: bool = False
        self._showing_partition: bool = False
        self._showing_gpu_stats: bool = False

        # GPU stats state (live refresh via set_interval)
        self._gpu_stats_timer = None
        self._gpu_stats_job: Job | None = None
        self._gpu_monitor_ref: GPUMonitor | None = None
        self._gpu_stats_widget: Static | None = None

        # Script editor state
        self._logs_area: TextArea | None = None
        self._script_area: TextArea | None = None
        self._script_path: str | None = None
        self._original_script: str = ""
        self._script_modified: bool = False

        # Log state — stderr/stdout toggle + incremental tails
        self._stderr_log_tail: LogTail | None = None
        self._stdout_log_tail: LogTail | None = None
        self._showing_stderr: bool = True
        self._stderr_content: str = ""
        self._stdout_content: str = ""
        self._logs_label: Static | None = None

    def compose(self) -> ComposeResult:
        yield Static("Job Details", classes="details-title")
        yield Static("─" * 40, classes="separator")
        yield Vertical(id="content-container")

    def on_mount(self) -> None:
        """Show initial placeholder."""
        self._show_placeholder("Select a job to view details")

    # ── Helpers ────────────────────────────────────────────────────

    def _clear_content(self) -> None:
        """Remove all children from the content container."""
        self.query_one("#content-container", Vertical).remove_children()

    def _show_placeholder(self, message: str, is_warning: bool = False) -> None:
        """Show a centered placeholder message."""
        self._clear_content()
        container = self.query_one("#content-container", Vertical)
        css_class = "not-your-job" if is_warning else "no-job"
        container.mount(Static(message, classes=css_class))

    def _show_loading(self) -> None:
        """Show a 'Loading...' indicator."""
        self._clear_content()
        container = self.query_one("#content-container", Vertical)
        container.mount(Static("Loading...", classes="loading"))

    def _update_title(self, title: str) -> None:
        """Update the panel title."""
        self.query_one(".details-title", Static).update(title)

    # ── Job details view ──────────────────────────────────────────

    def update_job(self, job: Job | None, force: bool = False) -> None:
        """Switch to job details view.

        Skips update if the same job is already displayed (prevents
        unnecessary file I/O on every cursor move).
        """
        # Don't overwrite partition/GPU views from auto-refresh
        if (self._showing_partition or self._showing_gpu_stats) and not force and job is not None:
            return

        self._showing_partition = False
        self._stop_gpu_stats()

        # Skip if same job already loaded
        if self._current_job is not None and job is not None:
            if self._current_job.job_id == job.job_id:
                return

        self._current_job = job

        if job is None:
            self._update_title("Job Details")
            self._show_placeholder("Select a job to view details")
            return

        self._update_title(f"Job {job.job_id} - {job.name}")
        self._show_loading()
        self._load_job_content()

    @work(thread=True, exclusive=True)
    def _load_job_content(self) -> None:
        """Load script + logs in a background thread.

        Uses a single scontrol call to get all job metadata (paths, owner).
        Reads script and log files from the shared filesystem.
        """
        worker = get_current_worker()
        job = self._current_job
        if not job:
            return

        # Single scontrol call for all job details
        details = self.slurm_client.get_job_details(job.job_id)
        if worker.is_cancelled:
            return

        # Check ownership — only show details for the user's own jobs
        job_user = details.get("UserId", "").split("(")[0] if details else None
        username = self.slurm_client.username
        is_own_job = job_user == username if job_user else True

        if not is_own_job:
            self.app.call_from_thread(
                self._show_placeholder,
                f"Not your job (owner: {job_user})\nDetails not available",
                True,
            )
            return

        # Extract file paths
        script_path = details.get("Command") if details else None
        stderr_path = details.get("StdErr") if details else None
        stdout_path = details.get("StdOut") if details else None

        if worker.is_cancelled:
            return

        # Read script content — try file first, fall back to scontrol
        script_content = "Script not available"
        if script_path and os.path.exists(script_path):
            try:
                with open(script_path) as f:
                    script_content = f.read()
            except Exception as e:
                script_content = f"Error reading script: {e}"

        if script_content == "Script not available":
            # Fallback: retrieve script from Slurm controller directly
            # Works for workflow-manager jobs, temp scripts, array jobs
            batch_script = self.slurm_client.get_batch_script(job.job_id)
            if batch_script:
                script_content = batch_script
                if not script_path:
                    script_path = "(retrieved from Slurm controller)"

        if worker.is_cancelled:
            return

        # Read stderr via LogTail (enables incremental refresh later)
        stderr_content = "No stderr log available"
        stderr_tail = None
        if stderr_path:
            log_tail = LogTail(stderr_path)
            result = read_log_incremental(log_tail)
            if result is not None:
                stderr_content = result
                stderr_tail = log_tail

        # Read stdout via LogTail
        stdout_content = "No stdout log available"
        stdout_tail = None
        if stdout_path:
            log_tail = LogTail(stdout_path)
            result = read_log_incremental(log_tail)
            if result is not None:
                stdout_content = result
                stdout_tail = log_tail

        if worker.is_cancelled:
            return

        self.app.call_from_thread(
            self._apply_job_content,
            script_path, script_content,
            stderr_content, stdout_content,
            stderr_tail, stdout_tail,
        )

    def _apply_job_content(
        self,
        script_path: str | None,
        script_content: str,
        stderr_content: str,
        stdout_content: str,
        stderr_tail: LogTail | None,
        stdout_tail: LogTail | None,
    ) -> None:
        """Mount the job details UI (runs on main thread)."""
        self._is_own_job = True
        self._script_path = script_path
        self._original_script = script_content
        self._script_modified = False
        self._stderr_log_tail = stderr_tail
        self._stdout_log_tail = stdout_tail
        self._stderr_content = stderr_content
        self._stdout_content = stdout_content
        self._showing_stderr = True

        self._clear_content()
        container = self.query_one("#content-container", Vertical)

        # Script section — read-only by default, Ctrl+E to enable editing
        container.mount(Static("Script [read-only] [Ctrl+E to edit]", classes="script-header"))
        container.mount(Static(f"{script_path or 'N/A'}", classes="script-path"))
        container.mount(Static("─" * 40, classes="separator"))

        script_area = TextArea(
            script_content,
            language="bash",
            read_only=True,
            show_line_numbers=True,
            classes="script-area",
        )
        container.mount(script_area)
        self._script_area = script_area

        # Logs section — defaults to stderr, 'w' toggles to stdout
        logs_label = Static("Logs (stderr) [w to toggle]", classes="section-label")
        container.mount(logs_label)
        self._logs_label = logs_label
        container.mount(Static("─" * 40, classes="separator"))

        logs_area = TextArea(
            stderr_content,
            read_only=True,
            show_line_numbers=True,
            classes="logs-area",
        )
        container.mount(logs_area)
        self._logs_area = logs_area

        # Auto-scroll logs to the end after the layout settles
        self.call_after_refresh(self._scroll_logs_to_end)

    def _scroll_logs_to_end(self) -> None:
        """Scroll the logs TextArea to the bottom."""
        try:
            if self._logs_area:
                self._logs_area.scroll_end(animate=False)
        except Exception:
            pass

    # ── Log refresh (incremental) ─────────────────────────────────
    #
    # LogTail tracks the file position so we only read new bytes.
    # This avoids re-reading multi-MB log files every 10 seconds.

    def refresh_logs(self) -> None:
        """Refresh log content — incremental if possible, full reload otherwise."""
        if not (self._current_job and self._is_own_job):
            return

        active_tail = self._stderr_log_tail if self._showing_stderr else self._stdout_log_tail
        if active_tail and active_tail._initialized and self._logs_area:
            self._refresh_logs_incremental()
        else:
            self._load_job_content()

    @work(thread=True, exclusive=True, group="refresh_logs")
    def _refresh_logs_incremental(self) -> None:
        """Read only new bytes from the active log file."""
        worker = get_current_worker()
        active_tail = self._stderr_log_tail if self._showing_stderr else self._stdout_log_tail
        if not active_tail:
            return

        result = read_log_incremental(active_tail)
        new_text = result if result else ""

        if worker.is_cancelled or not new_text:
            return

        self.app.call_from_thread(self._apply_incremental_logs, new_text)

    def _apply_incremental_logs(self, new_text: str) -> None:
        """Append new log text.  Only auto-scrolls if user was already at bottom."""
        try:
            if self._logs_area:
                was_at_bottom = self._logs_area.scroll_y >= self._logs_area.max_scroll_y
                self._logs_area.insert(new_text, self._logs_area.document.end)
                if was_at_bottom:
                    self._logs_area.scroll_end(animate=False)
        except Exception:
            pass

    # ── Log stream toggle ─────────────────────────────────────────

    def toggle_log_stream(self) -> None:
        """Switch between stderr and stdout in the logs area."""
        if not self._logs_area or not self._is_own_job:
            return

        # Cache current content before switching
        if self._showing_stderr:
            self._stderr_content = self._logs_area.text
        else:
            self._stdout_content = self._logs_area.text

        self._showing_stderr = not self._showing_stderr

        label = "stderr" if self._showing_stderr else "stdout"
        content = self._stderr_content if self._showing_stderr else self._stdout_content

        if self._logs_label:
            self._logs_label.update(f"Logs ({label}) [w to toggle]")

        self._logs_area.load_text(content)
        self._logs_area.scroll_end(animate=False)

    # ── Script editing ────────────────────────────────────────────

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Track whether the script has been modified."""
        if self._script_area and event.text_area == self._script_area:
            is_modified = self._script_area.text != self._original_script
            if is_modified != self._script_modified:
                self._script_modified = is_modified
                self._update_modified_indicator()

    def _update_modified_indicator(self) -> None:
        """Update the script header to reflect edit/modified state."""
        try:
            header = self.query_one(".script-header", Static)
            if self._script_modified:
                header.update("Script [modified] [Ctrl+S to save]")
                header.add_class("script-header-modified")
                if self._script_area:
                    self._script_area.add_class("script-modified")
            else:
                editing = self._script_area and not self._script_area.read_only
                if editing:
                    header.update("Script [editing] [Ctrl+S to save]")
                else:
                    header.update("Script [read-only] [Ctrl+E to edit]")
                header.remove_class("script-header-modified")
                if self._script_area:
                    self._script_area.remove_class("script-modified")
        except Exception:
            pass

    def toggle_edit_script(self) -> None:
        """Toggle script between read-only and editable (Ctrl+E)."""
        if not self._script_area:
            return
        self._script_area.read_only = not self._script_area.read_only
        self._update_modified_indicator()

    def save_script(self) -> bool:
        """Write the script content back to disk."""
        if not self._script_path or not self._script_area:
            self.notify("No script to save", severity="warning")
            return False

        try:
            with open(self._script_path, "w") as f:
                f.write(self._script_area.text)
            self._original_script = self._script_area.text
            self._script_modified = False
            self._update_modified_indicator()
            self.notify(f"Saved: {os.path.basename(self._script_path)}")
            return True
        except Exception as e:
            self.notify(f"Error saving: {e}", severity="error")
            return False

    def action_save_script(self) -> None:
        """Ctrl+S action handler."""
        self.save_script()

    def action_copy_logs(self) -> None:
        """Copy the current log content to the system clipboard."""
        if not self._logs_area or not self._logs_area.text:
            self.notify("No log content to copy", severity="warning")
            return

        text = self._logs_area.text
        if text.startswith("No "):
            self.notify("No log content to copy", severity="warning")
            return

        try:
            subprocess.run(
                ["pbcopy"] if os.uname().sysname == "Darwin" else ["xclip", "-selection", "clipboard"],
                input=text.encode(),
                check=True,
            )
            self.notify("Copied logs to clipboard")
        except Exception as e:
            self.notify(f"Copy failed: {e}", severity="error")

    def action_bookmark_script(self) -> None:
        """Bookmark the current script path."""
        if not self._script_path:
            self.notify("No script to bookmark", severity="warning")
            return

        if self.bookmark_manager.add_script(self._script_path):
            self.notify(f"Bookmarked: {os.path.basename(self._script_path)}")
        else:
            self.notify("Already bookmarked", severity="warning")

    # ── Partition details view ────────────────────────────────────

    # Known VRAM per GPU type (fallback when partition mapping unavailable)
    GPU_VRAM = {
        "rtx": "11 GB GDDR6",
        "rtx2080ti": "11 GB GDDR6",
        "a100": "40 GB HBM",
        "h200": "143 GB HBM",
        "h100": "80 GB HBM",
        "l40s": "46 GB GDDR6",
        "v100": "32 GB HBM",
        "a40": "48 GB GDDR6",
    }

    # Partition → (GPU model, VRAM) overrides for our cluster
    PARTITION_VRAM = {
        "p0": ("RTX 2080 Ti PCIe", "11 GB GDDR6"),
        "p1": ("A100-SXM4", "40 GB HBM"),
        "p2": ("A100-SXM4", "80 GB HBM"),
        "p4": ("H200-SXM5", "143 GB HBM"),
        "p6": ("L40S PCIe", "46 GB GDDR6"),
    }

    def update_partition(self, partition: PartitionGPU, gpu_monitor: GPUMonitor) -> None:
        """Switch to partition details view."""
        self._stop_gpu_stats()
        self._current_job = None
        self._showing_partition = True
        self._update_title(f"Partition {partition.partition}")
        self._show_loading()
        self._load_partition_details(partition, gpu_monitor)

    @work(thread=True, exclusive=True)
    def _load_partition_details(self, partition: PartitionGPU, gpu_monitor: GPUMonitor) -> None:
        """Fetch node details for a partition in background thread."""
        worker = get_current_worker()
        nodes = gpu_monitor.get_partition_details(partition.partition)
        if not worker.is_cancelled:
            self.app.call_from_thread(self._apply_partition_details, partition, nodes)

    def _apply_partition_details(self, partition: PartitionGPU, nodes: list[NodeGPU]) -> None:
        """Render partition summary + node table."""
        self._clear_content()
        container = self.query_one("#content-container", Vertical)

        percent = partition.usage_percent
        color = _color_for(percent)

        # Aggregate stats
        total_mem = sum(n.memory_mb for n in nodes)
        total_cpus = sum(n.cpus for n in nodes)

        # GPU model info
        if partition.partition in self.PARTITION_VRAM:
            gpu_name, vram = self.PARTITION_VRAM[partition.partition]
        else:
            gpu_name = nodes[0].gpu_type if nodes else "unknown"
            vram = self.GPU_VRAM.get(gpu_name.lower(), "unknown")

        summary_lines = [
            f"  GPUs: [{color}]{partition.allocated}[/] / {partition.total} allocated  ([{color}]{percent:.1f}%[/])",
            f"  GPU: [#bb9af7]{gpu_name}[/]   VRAM: [#bb9af7]{vram}[/]",
            f"  Nodes: [#c0caf5]{len(nodes)}[/]   CPUs: [#c0caf5]{total_cpus}[/]   RAM: [#c0caf5]{total_mem // 1024} GB[/]",
        ]
        container.mount(Static("\n".join(summary_lines)))
        container.mount(Static("─" * 40, classes="separator"))

        # Node table header
        header = (
            f"  [#565f89]{'Node':<16} {'GPUs':>4}  {'State':<14} "
            f"{'CPUs':>4}  {'Mem':>7}  {'Free':>7}[/]"
        )
        container.mount(Static(header))
        container.mount(Static("  [#414868]" + "─" * 62 + "[/]"))

        # Node rows
        for node in nodes:
            state = node.state
            if "idle" in state.lower():
                sc = "#9ece6a"
            elif "mix" in state.lower():
                sc = "#e0af68"
            elif "alloc" in state.lower() or "drain" in state.lower() or "down" in state.lower():
                sc = "#f7768e"
            else:
                sc = "#565f89"

            row = (
                f"  [#c0caf5]{node.node:<16}[/] "
                f"[#bb9af7]{node.gpu_count:>4}[/]  "
                f"[{sc}]{state:<14}[/] "
                f"[#c0caf5]{node.cpus:>4}[/]  "
                f"[#565f89]{node.memory_mb // 1024}G{' ' * (5 - len(str(node.memory_mb // 1024)))}[/]  "
                f"[#9ece6a]{node.free_memory_mb // 1024}G{' ' * (5 - len(str(node.free_memory_mb // 1024)))}[/]"
            )
            container.mount(Static(row))

    # ── Live GPU stats view ───────────────────────────────────────
    #
    # Mounts a single Static widget once, then updates its content
    # every 5 seconds via set_interval + background worker.
    # This avoids widget tree churn and keeps the UI responsive.

    def _stop_gpu_stats(self) -> None:
        """Stop the GPU stats timer and release references."""
        self._showing_gpu_stats = False
        self._gpu_stats_job = None
        self._gpu_monitor_ref = None
        self._gpu_stats_widget = None
        if self._gpu_stats_timer:
            self._gpu_stats_timer.stop()
            self._gpu_stats_timer = None

    def show_gpu_stats(self, job: Job, gpu_monitor: GPUMonitor) -> None:
        """Show live GPU stats for a running job (toggle off if same job)."""
        # Toggle off if already showing stats for this job
        if self._showing_gpu_stats and self._gpu_stats_job and self._gpu_stats_job.job_id == job.job_id:
            self._stop_gpu_stats()
            self._current_job = None
            self.update_job(job, force=True)
            return

        self._stop_gpu_stats()
        self._current_job = job
        self._showing_partition = False
        self._showing_gpu_stats = True
        self._gpu_stats_job = job
        self._gpu_monitor_ref = gpu_monitor
        self._update_title(f"GPU Stats — Job {job.job_id}")

        # Mount a single Static — content updated imperatively every 5s
        self._clear_content()
        container = self.query_one("#content-container", Vertical)
        self._gpu_stats_widget = Static("[#565f89]Loading GPU stats...[/]")
        container.mount(self._gpu_stats_widget)

        self._refresh_gpu_stats()
        self._gpu_stats_timer = self.set_interval(5.0, self._refresh_gpu_stats)

    @work(thread=True, exclusive=True, group="gpu_stats")
    def _refresh_gpu_stats(self) -> None:
        """Fetch GPU stats via srun --overlap nvidia-smi in background."""
        worker = get_current_worker()
        job = self._gpu_stats_job
        monitor = self._gpu_monitor_ref
        if not job or not monitor or not self._showing_gpu_stats:
            return

        stats = monitor.get_job_gpu_stats(job.job_id)
        if not worker.is_cancelled:
            self.app.call_from_thread(self._apply_gpu_stats, stats)

    def _apply_gpu_stats(self, stats: list[GPUStats]) -> None:
        """Render GPU stats into the existing Static widget (no rebuild)."""
        if not self._showing_gpu_stats or not self._gpu_stats_widget:
            return

        content = self._gpu_stats_widget

        if not stats:
            content.update(
                "[#f7768e]Could not fetch GPU stats[/]\n"
                "[#565f89]Job may have ended or nvidia-smi unavailable[/]"
            )
            self._stop_gpu_stats()
            return

        lines = []
        for s in stats:
            lines.append(f"  [#c0caf5]GPU {s.index}[/]: [#bb9af7]{s.name}[/]")

            util_bar = _make_bar(s.utilization)
            lines.append(f"    Util   {util_bar}  [{_color_for(s.utilization)}]{s.utilization:5.1f}%[/]")

            mem_pct = s.memory_percent
            lines.append(
                f"    VRAM   {_make_bar(mem_pct)}  [{_color_for(mem_pct)}]"
                f"{s.memory_used / 1024:.1f} / {s.memory_total / 1024:.1f} GB[/]"
            )

            pwr_pct = s.power_percent
            lines.append(
                f"    Power  {_make_bar(pwr_pct)}  [{_color_for(pwr_pct)}]"
                f"{s.power_draw:.0f} / {s.power_limit:.0f} W[/]"
            )

            temp_pct = min(s.temperature / 90 * 100, 100)
            lines.append(f"    Temp   [{_color_for(temp_pct)}]{s.temperature:.0f}°C[/]")
            lines.append("")

        lines.append("[#414868]Auto-refresh: 5s[/]")
        content.update("\n".join(lines))
