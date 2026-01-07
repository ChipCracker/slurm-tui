"""Main Screen - Dashboard with all widgets."""

from __future__ import annotations

import subprocess

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Static

from ..widgets import GPUMonitorWidget, GPUHoursWidget, JobTableWidget
from ..utils.slurm import SlurmClient
from ..utils.gpu import GPUMonitor
from ..utils.bookmarks import BookmarkManager


class MainScreen(Screen):
    """Main dashboard screen."""

    DEFAULT_CSS = """
    MainScreen {
        layout: grid;
        grid-size: 1;
        grid-rows: auto auto auto 1fr auto;
        padding: 0;
        background: #1a1b26;
    }

    MainScreen > .app-header {
        layout: horizontal;
        height: 1;
        padding: 0 2;
        margin-bottom: 1;
    }

    MainScreen > .app-header > .app-title {
        width: 1fr;
        color: #7aa2f7;
        text-style: bold;
    }

    MainScreen > .app-header > .app-info {
        width: auto;
        color: #414868;
    }

    MainScreen > #top-panel {
        layout: horizontal;
        height: auto;
        min-height: 6;
        max-height: 10;
    }

    MainScreen > #top-panel > GPUMonitorWidget {
        width: 1fr;
    }

    MainScreen > #gpu-hours-panel {
        height: auto;
        min-height: 6;
        max-height: 14;
    }

    MainScreen > #bottom-panel {
        height: 1fr;
        margin-top: 1;
    }

    MainScreen > #bottom-panel > JobTableWidget {
        width: 100%;
        height: 100%;
    }

    MainScreen > .keybindings {
        height: 1;
        padding: 0 2;
        color: #565f89;
        background: transparent;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("n", "new_job", "New Job"),
        ("i", "interactive", "Interactive"),
        ("a", "attach", "Attach"),
        ("c", "cancel", "Cancel"),
        ("u", "toggle_users", "Toggle Users"),
        ("l", "view_logs", "Logs"),
        ("b", "bookmarks", "Bookmarks"),
        ("B", "add_bookmark", "Add Bookmark"),
        ("e", "editor", "Editor"),
        ("?", "help", "Help"),
    ]

    def __init__(self):
        super().__init__()
        self.slurm_client = SlurmClient()
        self.gpu_monitor = GPUMonitor()
        self.bookmark_manager = BookmarkManager()

    def compose(self) -> ComposeResult:
        # App header
        with Horizontal(classes="app-header"):
            yield Static("SLURM TUI", classes="app-title")
            yield Static("10s refresh", classes="app-info")

        # GPU Monitor (full width)
        with Container(id="top-panel"):
            yield GPUMonitorWidget(
                gpu_monitor=self.gpu_monitor,
                refresh_interval=10.0,
            )

        # GPU Hours
        with Container(id="gpu-hours-panel"):
            yield GPUHoursWidget(
                gpu_monitor=self.gpu_monitor,
                refresh_interval=60.0,
            )

        # Jobs table
        with Container(id="bottom-panel"):
            yield JobTableWidget(
                slurm_client=self.slurm_client,
                refresh_interval=10.0,
            )

        # Custom keybindings footer
        yield Static(
            "[#7aa2f7]a[/]ttach  [#7aa2f7]c[/]ancel  [#7aa2f7]l[/]ogs  "
            "[#7aa2f7]n[/]ew  [#7aa2f7]i[/]nteractive  [#7aa2f7]u[/]sers  "
            "[#7aa2f7]b[/]ookmarks  [#7aa2f7]e[/]ditor  [#7aa2f7]q[/]uit",
            classes="keybindings",
        )

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()

    def action_refresh(self) -> None:
        """Refresh all data."""
        gpu_monitor = self.query_one(GPUMonitorWidget)
        gpu_monitor.refresh_data()

        gpu_hours = self.query_one(GPUHoursWidget)
        gpu_hours.refresh_data()

        job_table = self.query_one(JobTableWidget)
        job_table.refresh_data()

        self.notify("Data refreshed")

    def action_new_job(self) -> None:
        """Show new job dialog."""
        from .job_submit import JobSubmitScreen
        self.app.push_screen(JobSubmitScreen())

    def action_interactive(self) -> None:
        """Start interactive session."""
        from .job_submit import InteractiveSessionScreen
        self.app.push_screen(InteractiveSessionScreen())

    def action_attach(self) -> None:
        """Attach to selected job using suspend/resume."""
        job_table = self.query_one(JobTableWidget)
        job = job_table.get_selected_job()

        if job is None:
            self.notify("No job selected", severity="warning")
            return

        if job.state != "R":
            self.notify(f"Job {job.job_id} is not running (state: {job.state})", severity="warning")
            return

        cmd = self.slurm_client.attach_to_job(job.job_id)
        self.notify(f"Attaching to job {job.job_id}...")

        # Suspend TUI, run srun, then resume
        with self.app.suspend():
            subprocess.run(cmd)

    def action_cancel(self) -> None:
        """Cancel selected job."""
        job_table = self.query_one(JobTableWidget)
        job = job_table.get_selected_job()

        if job is None:
            self.notify("No job selected", severity="warning")
            return

        from .job_submit import ConfirmCancelScreen
        self.app.push_screen(ConfirmCancelScreen(job))

    def action_toggle_users(self) -> None:
        """Toggle between own jobs and all users."""
        job_table = self.query_one(JobTableWidget)
        job_table.toggle_all_users()

    def action_help(self) -> None:
        """Show help."""
        self.notify(
            "q=Quit r=Refresh n=New i=Interactive a=Attach c=Cancel l=Logs b=Bookmarks e=Editor",
            timeout=5,
        )

    def action_view_logs(self) -> None:
        """View logs for selected job."""
        job_table = self.query_one(JobTableWidget)
        job = job_table.get_selected_job()

        if job is None:
            self.notify("No job selected", severity="warning")
            return

        from .log_viewer import LogViewerScreen
        self.app.push_screen(LogViewerScreen(job, self.slurm_client))

    def action_bookmarks(self) -> None:
        """Show bookmarks."""
        from .bookmarks import BookmarksScreen
        self.app.push_screen(BookmarksScreen(self.bookmark_manager))

    def action_add_bookmark(self) -> None:
        """Add current job to bookmarks."""
        job_table = self.query_one(JobTableWidget)
        job = job_table.get_selected_job()

        if job is None:
            self.notify("No job selected", severity="warning")
            return

        self.bookmark_manager.add_job(job.job_id, job.name)
        self.notify(f"Bookmarked job {job.job_id}")

    def action_editor(self) -> None:
        """Open script editor."""
        from .editor import EditorScreen
        self.app.push_screen(EditorScreen())
