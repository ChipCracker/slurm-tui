"""Job Details Widget - shows script and logs for selected job."""

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
from ..utils.bookmarks import BookmarkManager
from ..utils.log_reader import LogTail, read_log_incremental


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
        ("y", "copy_logs", "Copy Logs"),
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
        self._current_job: Job | None = None
        self._is_own_job: bool = False
        self._logs_area: TextArea | None = None
        self._script_area: TextArea | None = None
        self._script_path: str | None = None
        self._original_script: str = ""
        self._script_modified: bool = False
        self._stderr_log_tail: LogTail | None = None

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

    def _show_loading(self) -> None:
        """Show a loading indicator."""
        self._clear_content()
        container = self.query_one("#content-container", Vertical)
        container.mount(Static("Loading...", classes="loading"))

    def update_job(self, job: Job | None) -> None:
        """Update the displayed job (only if job changed)."""
        if self._current_job is not None and job is not None:
            if self._current_job.job_id == job.job_id:
                return  # Same job, don't reload

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
        """Load job script and logs in background thread (single scontrol call)."""
        worker = get_current_worker()
        job = self._current_job
        if not job:
            return

        # Single scontrol call for all job details
        details = self.slurm_client.get_job_details(job.job_id)
        if worker.is_cancelled:
            return

        # Check ownership from cached details
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

        # Extract paths from cached details
        script_path = details.get("Command") if details else None
        stderr_path = details.get("StdErr") if details else None

        if worker.is_cancelled:
            return

        # Read script content
        script_content = "Script not available"
        if script_path and os.path.exists(script_path):
            try:
                with open(script_path) as f:
                    script_content = f.read()
            except Exception as e:
                script_content = f"Error reading script: {e}"

        if worker.is_cancelled:
            return

        # Read stderr content efficiently via LogTail (enables incremental refresh)
        stderr_content = "No stderr log available"
        self._stderr_log_tail = None
        if stderr_path:
            log_tail = LogTail(stderr_path)
            result = read_log_incremental(log_tail)
            if result is not None:
                stderr_content = result
                self._stderr_log_tail = log_tail

        if worker.is_cancelled:
            return

        # Update UI on main thread
        self.app.call_from_thread(
            self._apply_job_content,
            script_path,
            script_content,
            stderr_content,
        )

    def _apply_job_content(
        self,
        script_path: str | None,
        script_content: str,
        stderr_content: str,
    ) -> None:
        """Apply loaded content to the UI (runs on main thread)."""
        self._is_own_job = True
        self._script_path = script_path
        self._original_script = script_content
        self._script_modified = False

        self._clear_content()
        container = self.query_one("#content-container", Vertical)

        # Mount content - script header with edit hint
        container.mount(Static("Script [Ctrl+S to save]", classes="script-header"))
        container.mount(Static(f"{script_path or 'N/A'}", classes="script-path"))
        container.mount(Static("─" * 40, classes="separator"))

        # Editable script area
        script_area = TextArea(
            script_content,
            language="bash",
            read_only=False,
            show_line_numbers=True,
            classes="script-area",
        )
        container.mount(script_area)
        self._script_area = script_area

        container.mount(Static("Logs (stderr)", classes="section-label"))
        container.mount(Static("─" * 40, classes="separator"))

        logs_area = TextArea(
            stderr_content,
            read_only=True,
            show_line_numbers=True,
            classes="logs-area",
        )
        container.mount(logs_area)
        self._logs_area = logs_area

        # Scroll logs to end after mount
        self.call_after_refresh(self._scroll_logs_to_end)

    def _scroll_logs_to_end(self) -> None:
        """Scroll the logs area to the end."""
        try:
            if hasattr(self, "_logs_area") and self._logs_area:
                self._logs_area.scroll_end(animate=False)
        except Exception:
            pass

    def _update_title(self, title: str) -> None:
        """Update the title."""
        header = self.query_one(".details-title", Static)
        header.update(title)

    def refresh_logs(self) -> None:
        """Refresh the log content (incremental when possible)."""
        if not (self._current_job and self._is_own_job):
            return

        if self._stderr_log_tail and self._stderr_log_tail._initialized and self._logs_area:
            self._refresh_logs_incremental()
        else:
            self._load_job_content()

    @work(thread=True, exclusive=True, group="refresh_logs")
    def _refresh_logs_incremental(self) -> None:
        """Incrementally append new log content."""
        worker = get_current_worker()
        if not self._stderr_log_tail:
            return

        result = read_log_incremental(self._stderr_log_tail)
        new_text = result if result else ""

        if worker.is_cancelled or not new_text:
            return

        self.app.call_from_thread(self._apply_incremental_logs, new_text)

    def _apply_incremental_logs(self, new_text: str) -> None:
        """Append new text to logs area; auto-scroll only if already at bottom."""
        try:
            if self._logs_area:
                was_at_bottom = self._logs_area.scroll_y >= self._logs_area.max_scroll_y
                self._logs_area.insert(new_text, self._logs_area.document.end)
                if was_at_bottom:
                    self._logs_area.scroll_end(animate=False)
        except Exception:
            pass

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

    def action_copy_logs(self) -> None:
        """Copy stderr logs to clipboard."""
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
        """Bookmark the current script (B key)."""
        if not self._script_path:
            self.notify("No script to bookmark", severity="warning")
            return

        if self.bookmark_manager.add_script(self._script_path):
            self.notify(f"Bookmarked: {os.path.basename(self._script_path)}")
        else:
            self.notify("Already bookmarked", severity="warning")
