"""Main Screen - Dashboard with all widgets."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Header, Footer, Static

from ..widgets import GPUMonitorWidget, GPUHoursWidget, JobTableWidget
from ..utils.slurm import SlurmClient
from ..utils.gpu import GPUMonitor


class MainScreen(Screen):
    """Main dashboard screen."""

    DEFAULT_CSS = """
    MainScreen {
        layout: grid;
        grid-size: 1;
        grid-rows: auto 1fr;
    }

    MainScreen > #top-panel {
        layout: horizontal;
        height: auto;
        min-height: 10;
        max-height: 15;
    }

    MainScreen > #top-panel > GPUMonitorWidget {
        width: 2fr;
    }

    MainScreen > #top-panel > GPUHoursWidget {
        width: 1fr;
    }

    MainScreen > #bottom-panel {
        height: 1fr;
    }

    MainScreen > #bottom-panel > JobTableWidget {
        width: 100%;
        height: 100%;
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
        ("?", "help", "Help"),
    ]

    def __init__(self):
        super().__init__()
        self.slurm_client = SlurmClient()
        self.gpu_monitor = GPUMonitor()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Horizontal(id="top-panel"):
            yield GPUMonitorWidget(
                gpu_monitor=self.gpu_monitor,
                refresh_interval=10.0,
            )
            yield GPUHoursWidget(
                gpu_monitor=self.gpu_monitor,
                refresh_interval=60.0,
            )

        with Container(id="bottom-panel"):
            yield JobTableWidget(
                slurm_client=self.slurm_client,
                refresh_interval=10.0,
            )

        yield Footer()

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
        """Attach to selected job."""
        job_table = self.query_one(JobTableWidget)
        job = job_table.get_selected_job()

        if job is None:
            self.notify("No job selected", severity="warning")
            return

        if job.state != "R":
            self.notify(f"Job {job.job_id} is not running (state: {job.state})", severity="warning")
            return

        # Show the attach command
        cmd = self.slurm_client.attach_to_job(job.job_id)
        self.notify(f"Run: {' '.join(cmd)}")

        # We can't actually attach from TUI, but we can show the command
        self.app.exit(message=f"To attach, run:\n{' '.join(cmd)}")

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
            "q=Quit r=Refresh n=New i=Interactive a=Attach c=Cancel u=Users",
            timeout=5,
        )
