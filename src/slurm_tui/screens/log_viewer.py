"""Log Viewer Screen - View job stdout/stderr logs."""

from __future__ import annotations

import os

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Static, TextArea, Button, TabbedContent, TabPane
from textual.worker import get_current_worker

from ..utils.slurm import SlurmClient, Job


def _read_log_file(path: str, tail: int = 1000) -> str:
    """Read log file tail efficiently with terminal simulation for carriage returns."""
    try:
        file_size = os.path.getsize(path)

        # For large files, only read the tail portion
        tail_bytes = 1024 * 1024  # 1MB for log viewer (more than details panel)
        truncated = False

        with open(path, "rb") as f:
            if file_size > tail_bytes:
                f.seek(-tail_bytes, 2)
                f.readline()  # Skip partial first line
                truncated = True
            content = f.read().decode("utf-8", errors="replace")

        # Process carriage returns: take last \r segment (simulates terminal overwrite)
        result_lines = []
        for raw_line in content.split("\n"):
            if "\r" in raw_line:
                # Take the last non-empty segment after \r
                segments = raw_line.split("\r")
                final = ""
                for seg in reversed(segments):
                    if seg.strip():
                        final = seg
                        break
                if final:
                    result_lines.append(final)
            elif raw_line.strip():
                result_lines.append(raw_line)

        # Limit to last N lines
        if len(result_lines) > tail:
            result_lines = (
                [f"... ({len(result_lines) - tail} lines omitted) ..."]
                + result_lines[-tail:]
            )
        elif truncated:
            result_lines = ["... (showing tail of large file) ..."] + result_lines

        return "\n".join(result_lines)
    except Exception as e:
        return f"Error reading log: {e}"


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
    ]

    following: reactive[bool] = reactive(False)

    def __init__(self, job: Job, slurm_client: SlurmClient):
        super().__init__()
        self.job = job
        self.slurm_client = slurm_client
        self.stdout_path: str | None = None
        self.stderr_path: str | None = None
        self._follow_timer = None

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
        """Load log file contents in background thread."""
        worker = get_current_worker()

        stderr_content = "No stderr log available"
        if self.stderr_path and os.path.exists(self.stderr_path):
            stderr_content = _read_log_file(self.stderr_path)

        if worker.is_cancelled:
            return

        stdout_content = "No stdout log available"
        if self.stdout_path and os.path.exists(self.stdout_path):
            stdout_content = _read_log_file(self.stdout_path)

        if worker.is_cancelled:
            return

        self.app.call_from_thread(self._apply_logs, stderr_content, stdout_content)

    def _apply_logs(self, stderr_content: str, stdout_content: str) -> None:
        """Apply loaded log content on the main thread."""
        try:
            stderr_log = self.query_one("#stderr-log", TextArea)
            stderr_log.load_text(stderr_content)
            stderr_log.scroll_end(animate=False)

            stdout_log = self.query_one("#stdout-log", TextArea)
            stdout_log.load_text(stdout_content)
            stdout_log.scroll_end(animate=False)
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "close":
            self.app.pop_screen()
        elif event.button.id == "refresh":
            self._load_logs()
            self.notify("Logs refreshed")
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
        self._load_logs()

    def action_refresh_logs(self) -> None:
        """Refresh log contents."""
        self._load_logs()
        self.notify("Logs refreshed")
