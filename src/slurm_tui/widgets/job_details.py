"""Job Details Widget - shows script and logs for selected job."""

from __future__ import annotations

import os

from textual.app import ComposeResult
from textual.containers import Vertical, ScrollableContainer
from textual.reactive import reactive
from textual.widgets import Static, TextArea
from textual.widget import Widget

from ..utils.slurm import SlurmClient, Job


class JobDetailsWidget(Widget):
    """Widget showing job details: script content and stderr logs."""

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
    ]

    def __init__(
        self,
        slurm_client: SlurmClient | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.slurm_client = slurm_client or SlurmClient()
        self._current_job: Job | None = None
        self._is_own_job: bool = False
        self._logs_area: TextArea | None = None
        self._script_area: TextArea | None = None
        self._script_path: str | None = None
        self._original_script: str = ""
        self._script_modified: bool = False

    def compose(self) -> ComposeResult:
        yield Static("Job Details", classes="details-title")
        yield Static("─" * 40, classes="separator")
        yield Vertical(id="content-container")

    def on_mount(self) -> None:
        """Show initial placeholder."""
        self._show_placeholder("Select a job to view details")

    def _clear_content(self) -> None:
        """Clear the content container."""
        container = self.query_one("#content-container", Vertical)
        container.remove_children()

    def _show_placeholder(self, message: str, is_warning: bool = False) -> None:
        """Show a placeholder message."""
        self._clear_content()
        container = self.query_one("#content-container", Vertical)
        css_class = "not-your-job" if is_warning else "no-job"
        container.mount(Static(message, classes=css_class))

    def _show_job_details(self) -> None:
        """Show full job details with script and logs."""
        self._clear_content()
        container = self.query_one("#content-container", Vertical)

        # Get script path and content
        self._script_path = self._get_script_path()
        script_content = self._get_script_content()
        stderr_content = self._get_stderr_content()
        self._original_script = script_content
        self._script_modified = False

        # Mount content - script header with edit hint
        container.mount(Static("Script [Ctrl+S to save]", classes="script-header"))
        container.mount(Static(f"{self._script_path or 'N/A'}", classes="script-path"))
        container.mount(Static("─" * 40, classes="separator"))

        # Editable script area
        script_area = TextArea(
            script_content,
            language="bash",
            read_only=False,  # Editable!
            show_line_numbers=True,
            classes="script-area",
        )
        container.mount(script_area)
        self._script_area = script_area  # Keep reference for saving

        container.mount(Static("Logs (stderr)", classes="section-label"))
        container.mount(Static("─" * 40, classes="separator"))

        logs_area = TextArea(
            stderr_content,
            read_only=True,
            show_line_numbers=True,
            classes="logs-area",
        )
        container.mount(logs_area)
        self._logs_area = logs_area  # Keep reference for scrolling

        # Scroll logs to end after mount
        self.call_after_refresh(self._scroll_logs_to_end)

    def _scroll_logs_to_end(self) -> None:
        """Scroll the logs area to the end."""
        try:
            if hasattr(self, '_logs_area') and self._logs_area:
                self._logs_area.scroll_end(animate=False)
        except Exception:
            pass

    def update_job(self, job: Job | None) -> None:
        """Update the displayed job (only if job changed)."""
        # Only update if job actually changed
        if self._current_job is not None and job is not None:
            if self._current_job.job_id == job.job_id:
                return  # Same job, don't reload

        self._current_job = job
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Refresh the display based on current job."""
        if self._current_job is None:
            self._update_title("Job Details")
            self._show_placeholder("Select a job to view details")
            return

        # Update title
        self._update_title(f"Job {self._current_job.job_id} - {self._current_job.name}")

        # Check if it's our job
        username = self.slurm_client.username
        job_user = self._get_job_user()
        self._is_own_job = job_user == username if job_user else True

        if not self._is_own_job:
            self._show_placeholder(
                f"Not your job (owner: {job_user})\nDetails not available",
                is_warning=True
            )
            return

        self._show_job_details()

    def _update_title(self, title: str) -> None:
        """Update the title."""
        header = self.query_one(".details-title", Static)
        header.update(title)

    def _get_job_user(self) -> str | None:
        """Get the user who owns the job."""
        if not self._current_job:
            return None
        details = self.slurm_client.get_job_details(self._current_job.job_id)
        if details:
            return details.get("UserId", "").split("(")[0]  # "user(1000)" -> "user"
        return None

    def _get_script_path(self) -> str | None:
        """Get the script path for the current job."""
        if not self._current_job:
            return None
        details = self.slurm_client.get_job_details(self._current_job.job_id)
        if details:
            return details.get("Command")
        return None

    def _get_script_content(self) -> str:
        """Get the script content for the current job."""
        path = self._get_script_path()
        if path and os.path.exists(path):
            try:
                with open(path) as f:
                    return f.read()
            except Exception as e:
                return f"Error reading script: {e}"
        return "Script not available"

    def _get_stderr_content(self) -> str:
        """Get the stderr log content for the current job."""
        if not self._current_job:
            return "No job selected"

        _, stderr_path = self.slurm_client.get_job_log_paths(self._current_job.job_id)

        if stderr_path and os.path.exists(stderr_path):
            try:
                return self._read_log_file(stderr_path)
            except Exception as e:
                return f"Error reading log: {e}"
        return "No stderr log available"

    def _read_log_file(self, path: str, tail: int = 500) -> str:
        """Read log file with terminal simulation for carriage returns."""
        with open(path) as f:
            content = f.read()

        # Simulate terminal behavior for carriage returns
        lines = []
        current_line = ""

        for char in content:
            if char == '\r':
                current_line = ""
            elif char == '\n':
                lines.append(current_line)
                current_line = ""
            else:
                current_line += char

        if current_line:
            lines.append(current_line)

        # Filter empty lines from progress bar overwrites
        lines = [line for line in lines if line.strip()]

        # Show last N lines
        if len(lines) > tail:
            lines = [f"... ({len(lines) - tail} lines omitted) ..."] + lines[-tail:]

        return '\n'.join(lines)

    def refresh_logs(self) -> None:
        """Refresh the log content."""
        if self._current_job and self._is_own_job:
            self._refresh_display()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Track script modifications."""
        if self._script_area and event.text_area == self._script_area:
            is_modified = self._script_area.text != self._original_script
            if is_modified != self._script_modified:
                self._script_modified = is_modified
                self._update_modified_indicator()

    def _update_modified_indicator(self) -> None:
        """Update visual indicator for modified script."""
        try:
            header = self.query_one(".script-header", Static)
            if self._script_modified:
                header.update("Script [modified] [Ctrl+S to save]")
                header.add_class("script-header-modified")
                if self._script_area:
                    self._script_area.add_class("script-modified")
            else:
                header.update("Script [Ctrl+S to save]")
                header.remove_class("script-header-modified")
                if self._script_area:
                    self._script_area.remove_class("script-modified")
        except Exception:
            pass

    def save_script(self) -> bool:
        """Save the script to disk."""
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
        """Action to save script (Ctrl+S)."""
        self.save_script()
