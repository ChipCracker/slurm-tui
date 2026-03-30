"""Log Viewer Screen - View job stdout/stderr logs."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Static, TextArea, Button, TabbedContent, TabPane
from textual.worker import get_current_worker

from ..utils.slurm import SlurmClient, Job
from ..utils.log_reader import LogTail, read_log_incremental


class LogViewerScreen(ModalScreen):
    """Modal screen for viewing job logs."""

    DEFAULT_CSS = """
    LogViewerScreen {
        align: center middle;
        background: rgba(26, 27, 38, 0.9);
    }

    LogViewerScreen > Vertical {
        width: 90%;
        height: 90%;
        background: #1a1b26;
    }

    LogViewerScreen .log-title {
        text-style: bold;
        text-align: center;
        padding: 1 0 0 0;
        color: #7aa2f7;
    }

    LogViewerScreen .separator {
        color: #414868;
        padding: 0 2;
    }

    LogViewerScreen .log-container {
        height: 1fr;
    }

    LogViewerScreen TextArea {
        height: 1fr;
        background: #1a1b26;
        border: none;
    }

    LogViewerScreen .log-actions {
        height: auto;
        padding: 1;
        align: center middle;
    }

    LogViewerScreen .log-actions Button {
        margin: 0 1;
    }

    LogViewerScreen .no-log {
        text-align: center;
        color: #565f89;
        padding: 2;
    }

    LogViewerScreen TabbedContent {
        height: 1fr;
        background: #1a1b26;
    }

    LogViewerScreen Tabs {
        background: #1a1b26;
        border-bottom: solid #414868;
    }

    LogViewerScreen Tab {
        background: #1a1b26;
        color: #565f89;
        border: none;
    }

    LogViewerScreen Tab.-active {
        background: #1a1b26;
        color: #7aa2f7;
        text-style: bold;
    }

    LogViewerScreen TabPane {
        background: #1a1b26;
        padding: 0;
    }
    """

    BINDINGS = [
        ("escape", "close", "Close"),
        ("f", "toggle_follow", "Follow"),
        ("r", "refresh_logs", "Refresh"),
        ("y", "copy_logs", "Copy"),
    ]

    following: reactive[bool] = reactive(False)

    def __init__(self, job: Job, slurm_client: SlurmClient):
        super().__init__()
        self.job = job
        self.slurm_client = slurm_client
        self.stdout_path: str | None = None
        self.stderr_path: str | None = None
        self._follow_timer = None
        self._stderr_tail: LogTail | None = None
        self._stdout_tail: LogTail | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(
                f"Job Logs: {self.job.job_id} - {self.job.name}",
                classes="log-title",
            )

            # stderr tab first (default)
            with TabbedContent(initial="stderr-tab"):
                with TabPane("stderr", id="stderr-tab"):
                    yield TextArea(id="stderr-log", read_only=True, show_line_numbers=True)

                with TabPane("stdout", id="stdout-tab"):
                    yield TextArea(id="stdout-log", read_only=True, show_line_numbers=True)

            with Horizontal(classes="log-actions"):
                yield Button("Refresh", variant="primary", id="refresh")
                yield Button("Copy", variant="default", id="copy")
                yield Button("Follow", variant="default", id="follow")
                yield Button("Close", variant="default", id="close")

    def on_mount(self) -> None:
        """Load logs on mount."""
        self._load_log_paths()
        self._load_logs()

    def _load_log_paths(self) -> None:
        """Get log file paths from SLURM."""
        self.stdout_path, self.stderr_path = self.slurm_client.get_job_log_paths(
            self.job.job_id
        )

    @work(thread=True, exclusive=True)
    def _load_logs(self) -> None:
        """Full load of log files (initial mount + manual refresh)."""
        worker = get_current_worker()

        # Create fresh LogTail objects for full reload
        self._stderr_tail = LogTail(self.stderr_path) if self.stderr_path else None
        self._stdout_tail = LogTail(self.stdout_path) if self.stdout_path else None

        stderr_content = "No stderr log available"
        if self._stderr_tail:
            result = read_log_incremental(self._stderr_tail)
            if result is not None:
                stderr_content = result

        if worker.is_cancelled:
            return

        stdout_content = "No stdout log available"
        if self._stdout_tail:
            result = read_log_incremental(self._stdout_tail)
            if result is not None:
                stdout_content = result

        if worker.is_cancelled:
            return

        self.app.call_from_thread(self._apply_logs, stderr_content, stdout_content)

    def _apply_logs(self, stderr_content: str, stdout_content: str) -> None:
        """Apply full log content on the main thread (load_text + scroll to end)."""
        try:
            stderr_log = self.query_one("#stderr-log", TextArea)
            stderr_log.load_text(stderr_content)
            stderr_log.scroll_end(animate=False)

            stdout_log = self.query_one("#stdout-log", TextArea)
            stdout_log.load_text(stdout_content)
            stdout_log.scroll_end(animate=False)
        except Exception:
            pass

    @work(thread=True, exclusive=True)
    def _follow_tick(self) -> None:
        """Incremental follow-mode update — only reads new bytes."""
        worker = get_current_worker()

        stderr_new = ""
        if self._stderr_tail and self._stderr_tail._initialized:
            result = read_log_incremental(self._stderr_tail)
            stderr_new = result if result else ""

        if worker.is_cancelled:
            return

        stdout_new = ""
        if self._stdout_tail and self._stdout_tail._initialized:
            result = read_log_incremental(self._stdout_tail)
            stdout_new = result if result else ""

        if worker.is_cancelled:
            return

        if stderr_new or stdout_new:
            self.app.call_from_thread(
                self._apply_incremental, stderr_new, stdout_new
            )

    def _apply_incremental(self, stderr_new: str, stdout_new: str) -> None:
        """Append new text to TextAreas; auto-scroll only if already at bottom."""
        try:
            if stderr_new:
                ta = self.query_one("#stderr-log", TextArea)
                was_at_bottom = ta.scroll_y >= ta.max_scroll_y
                ta.insert(stderr_new, ta.document.end)
                if was_at_bottom:
                    ta.scroll_end(animate=False)

            if stdout_new:
                ta = self.query_one("#stdout-log", TextArea)
                was_at_bottom = ta.scroll_y >= ta.max_scroll_y
                ta.insert(stdout_new, ta.document.end)
                if was_at_bottom:
                    ta.scroll_end(animate=False)
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "close":
            self.app.pop_screen()
        elif event.button.id == "refresh":
            self._load_logs()
            self.notify("Logs refreshed")
        elif event.button.id == "copy":
            self.action_copy_logs()
        elif event.button.id == "follow":
            self.action_toggle_follow()

    def action_close(self) -> None:
        """Close the log viewer."""
        self.app.pop_screen()

    def action_toggle_follow(self) -> None:
        """Toggle log following."""
        self.following = not self.following

        follow_btn = self.query_one("#follow", Button)

        if self.following:
            follow_btn.variant = "success"
            follow_btn.label = "Following"
            self._follow_timer = self.set_interval(2.0, self._follow_update)
            self.notify("Following logs...")
        else:
            follow_btn.variant = "default"
            follow_btn.label = "Follow"
            if self._follow_timer:
                self._follow_timer.stop()
                self._follow_timer = None
            self.notify("Stopped following")

    def _follow_update(self) -> None:
        """Update logs when following."""
        self._follow_tick()

    def action_copy_logs(self) -> None:
        """Copy the complete log file content to clipboard."""
        try:
            tabbed = self.query_one(TabbedContent)
            active_tab = tabbed.active
            if active_tab == "stderr-tab":
                path = self.stderr_path
                label = "stderr"
            else:
                path = self.stdout_path
                label = "stdout"

            if not path:
                self.notify("No log file available", severity="warning")
                return

            with open(path, "r", errors="replace") as f:
                text = f.read()

            if not text.strip():
                self.notify("Log file is empty", severity="warning")
                return

            self.app.copy_to_clipboard(text)
            self.notify(f"Copied complete {label} log to clipboard")
        except Exception as e:
            self.notify(f"Copy failed: {e}", severity="error")

    def action_refresh_logs(self) -> None:
        """Refresh log contents."""
        self._load_logs()
        self.notify("Logs refreshed")
