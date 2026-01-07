"""Log Viewer Screen - View job stdout/stderr logs."""

from __future__ import annotations

import os
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Static, RichLog, Button, TabbedContent, TabPane

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

    LogViewerScreen RichLog {
        height: 1fr;
        border: solid $primary-darken-2;
        scrollbar-gutter: stable;
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

            with TabbedContent():
                with TabPane("stdout", id="stdout-tab"):
                    yield RichLog(id="stdout-log", highlight=True, markup=True)

                with TabPane("stderr", id="stderr-tab"):
                    yield RichLog(id="stderr-log", highlight=True, markup=True)

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
        stdout_log = self.query_one("#stdout-log", RichLog)
        stderr_log = self.query_one("#stderr-log", RichLog)

        stdout_log.clear()
        stderr_log.clear()

        # Load stdout
        if self.stdout_path and os.path.exists(self.stdout_path):
            self._load_file_to_log(self.stdout_path, stdout_log)
        else:
            stdout_log.write("[dim]No stdout log available[/dim]")

        # Load stderr
        if self.stderr_path and os.path.exists(self.stderr_path):
            self._load_file_to_log(self.stderr_path, stderr_log)
        else:
            stderr_log.write("[dim]No stderr log available[/dim]")

    def _load_file_to_log(self, path: str, log_widget: RichLog, tail: int = 500) -> None:
        """Load file contents into a RichLog widget."""
        try:
            with open(path) as f:
                lines = f.readlines()

            # Show last N lines
            if len(lines) > tail:
                log_widget.write(f"[dim]... ({len(lines) - tail} lines omitted) ...[/dim]\n")
                lines = lines[-tail:]

            for line in lines:
                log_widget.write(line.rstrip())
        except Exception as e:
            log_widget.write(f"[red]Error reading log: {e}[/red]")

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
