"""Log Viewer Screen - View job stdout/stderr logs."""

from __future__ import annotations

import os
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Static, TextArea, Button, TabbedContent, TabPane

from ..utils.slurm import SlurmClient, Job


class LogViewerScreen(ModalScreen):
    """Modal screen for viewing job logs."""

    DEFAULT_CSS = """
    LogViewerScreen {
        align: center middle;
    }

    LogViewerScreen > Vertical {
        width: 90%;
        height: 90%;
        border: thick $primary;
        background: $surface;
    }

    LogViewerScreen .log-title {
        text-style: bold;
        text-align: center;
        padding: 1;
        background: $primary-darken-2;
    }

    LogViewerScreen .log-container {
        height: 1fr;
    }

    LogViewerScreen TextArea {
        height: 1fr;
        border: solid $primary-darken-2;
    }

    LogViewerScreen .log-actions {
        height: auto;
        padding: 1;
        align: center middle;
        background: $surface-darken-1;
    }

    LogViewerScreen .log-actions Button {
        margin: 0 1;
    }

    LogViewerScreen .no-log {
        text-align: center;
        color: $text-muted;
        padding: 2;
    }

    LogViewerScreen TabbedContent {
        height: 1fr;
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

    def _load_logs(self) -> None:
        """Load log file contents."""
        stdout_log = self.query_one("#stdout-log", TextArea)
        stderr_log = self.query_one("#stderr-log", TextArea)

        # Load stderr
        if self.stderr_path and os.path.exists(self.stderr_path):
            content = self._read_log_file(self.stderr_path)
            stderr_log.load_text(content)
            # Scroll to end
            stderr_log.scroll_end(animate=False)
        else:
            stderr_log.load_text("No stderr log available")

        # Load stdout
        if self.stdout_path and os.path.exists(self.stdout_path):
            content = self._read_log_file(self.stdout_path)
            stdout_log.load_text(content)
            # Scroll to end
            stdout_log.scroll_end(animate=False)
        else:
            stdout_log.load_text("No stdout log available")

    def _read_log_file(self, path: str, tail: int = 1000) -> str:
        """Read log file and return content as string."""
        try:
            with open(path) as f:
                content = f.read()

            # Simulate terminal behavior for carriage returns
            # Process the content to handle \r (overwrites current line)
            lines = []
            current_line = ""

            for char in content:
                if char == '\r':
                    # Carriage return: reset to beginning of current line
                    current_line = ""
                elif char == '\n':
                    # Newline: finish current line and start new one
                    lines.append(current_line)
                    current_line = ""
                else:
                    current_line += char

            # Don't forget the last line if it doesn't end with \n
            if current_line:
                lines.append(current_line)

            # Filter out empty lines that come from progress bar overwrites
            lines = [line for line in lines if line.strip()]

            # Show last N lines
            if len(lines) > tail:
                lines = [f"... ({len(lines) - tail} lines omitted) ..."] + lines[-tail:]

            return '\n'.join(lines)
        except Exception as e:
            return f"Error reading log: {e}"

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
