"""Job Details Widget - shows script and logs for selected job."""

from __future__ import annotations

import os

from textual.app import ComposeResult
from textual.containers import Vertical
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

    JobDetailsWidget > .details-header {
        height: auto;
        margin-bottom: 0;
    }

    JobDetailsWidget > .details-header > .details-title {
        color: #7aa2f7;
        text-style: bold;
    }

    JobDetailsWidget > .details-header > .details-subtitle {
        color: #565f89;
    }

    JobDetailsWidget > .separator {
        color: #414868;
        margin-bottom: 0;
    }

    JobDetailsWidget > .section-label {
        color: #565f89;
        margin-top: 1;
    }

    JobDetailsWidget > .script-path {
        color: #9ece6a;
        margin-bottom: 0;
    }

    JobDetailsWidget > TextArea {
        height: 1fr;
        background: transparent;
        border: none;
        min-height: 5;
    }

    JobDetailsWidget > .no-job {
        color: #565f89;
        text-style: italic;
        text-align: center;
        padding: 2;
    }

    JobDetailsWidget > .not-your-job {
        color: #e0af68;
        text-align: center;
        padding: 2;
    }

    JobDetailsWidget > #script-area {
        max-height: 40%;
    }

    JobDetailsWidget > #logs-area {
        height: 1fr;
    }
    """

    job: reactive[Job | None] = reactive(None)

    def __init__(
        self,
        slurm_client: SlurmClient | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.slurm_client = slurm_client or SlurmClient()
        self._current_job: Job | None = None
        self._is_own_job: bool = False

    def compose(self) -> ComposeResult:
        yield Static("Job Details", classes="details-title details-header")
        yield Static("─" * 40, classes="separator")
        yield Static("Select a job to view details", id="placeholder", classes="no-job")

    def watch_job(self, job: Job | None) -> None:
        """React to job changes."""
        self._current_job = job
        self._update_display()

    def _update_display(self) -> None:
        """Update the display based on current job."""
        # Remove old content except header
        for widget in list(self.query("*")):
            if widget.id not in (None,) and widget.id not in ("placeholder",):
                if isinstance(widget, (TextArea, Static)) and widget.has_class("details-title", "separator") is False:
                    pass

        # Clear everything and rebuild
        self._rebuild_content()

    def _rebuild_content(self) -> None:
        """Rebuild the widget content."""
        # Remove dynamic content
        for widget in list(self.query(TextArea)):
            widget.remove()
        for widget in list(self.query(".section-label")):
            widget.remove()
        for widget in list(self.query(".script-path")):
            widget.remove()
        for widget in list(self.query(".not-your-job")):
            widget.remove()

        placeholder = self.query_one("#placeholder", Static)

        if self._current_job is None:
            placeholder.update("Select a job to view details")
            placeholder.display = True
            return

        # Check if it's our job
        username = self.slurm_client.username
        job_user = self._get_job_user()
        self._is_own_job = job_user == username if job_user else True  # Assume own job if can't determine

        # Update header
        header = self.query_one(".details-title", Static)
        header.update(f"Job {self._current_job.job_id} - {self._current_job.name}")

        if not self._is_own_job:
            placeholder.update(f"Not your job (owner: {job_user})\nDetails not available")
            placeholder.remove_class("no-job")
            placeholder.add_class("not-your-job")
            placeholder.display = True
            return

        placeholder.display = False

        # Get script path and content
        script_path = self._get_script_path()
        script_content = self._get_script_content()
        stderr_content = self._get_stderr_content()

        # Mount new content
        self.mount(Static("Script", classes="section-label"))
        self.mount(Static(f"{script_path or 'N/A'}", classes="script-path"))
        self.mount(Static("─" * 40, classes="separator"))

        script_area = TextArea(
            script_content,
            language="bash",
            read_only=True,
            show_line_numbers=True,
            id="script-area",
        )
        self.mount(script_area)

        self.mount(Static("Logs (stderr)", classes="section-label"))
        self.mount(Static("─" * 40, classes="separator"))

        logs_area = TextArea(
            stderr_content,
            read_only=True,
            show_line_numbers=True,
            id="logs-area",
        )
        self.mount(logs_area)

        # Scroll logs to end
        logs_area.scroll_end(animate=False)

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

    def update_job(self, job: Job | None) -> None:
        """Update the displayed job."""
        self.job = job

    def refresh_logs(self) -> None:
        """Refresh the log content."""
        if self._current_job and self._is_own_job:
            self._rebuild_content()
