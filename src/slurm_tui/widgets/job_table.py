"""Job Table Widget - shows SLURM jobs."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Static, DataTable
from textual.widget import Widget

from ..utils.slurm import SlurmClient, Job


# Status symbols with colors
STATUS_SYMBOLS = {
    "R": ("●", "#9ece6a"),    # Running - green
    "PD": ("◐", "#e0af68"),   # Pending - yellow
    "CD": ("✓", "#7aa2f7"),   # Completed - blue
    "CG": ("✓", "#7aa2f7"),   # Completing - blue
    "F": ("✗", "#f7768e"),    # Failed - red
    "CA": ("⏹", "#565f89"),   # Cancelled - gray
    "TO": ("⏱", "#f7768e"),   # Timeout - red
    "NF": ("✗", "#f7768e"),   # Node Fail - red
}


class JobTableWidget(Widget):
    """Widget showing SLURM jobs in a table."""

    DEFAULT_CSS = """
    JobTableWidget {
        background: transparent;
        border: none;
        height: 1fr;
        padding: 0 2;
    }

    JobTableWidget > .section-header {
        layout: horizontal;
        height: 1;
        margin-bottom: 0;
    }

    JobTableWidget > .section-header > .section-title {
        width: 1fr;
        color: #565f89;
    }

    JobTableWidget > .section-header > .section-info {
        width: auto;
        color: #414868;
    }

    JobTableWidget > .separator {
        color: #414868;
        margin-bottom: 0;
    }

    JobTableWidget > .column-header {
        color: #565f89;
        height: 1;
        padding: 0;
    }

    JobTableWidget > .header-separator {
        color: #414868;
        margin-bottom: 0;
    }

    JobTableWidget > DataTable {
        height: 1fr;
        background: transparent;
        border: none;
    }

    JobTableWidget .no-jobs {
        color: #565f89;
        text-style: italic;
    }
    """

    jobs: reactive[list[Job]] = reactive(list)
    show_all_users: reactive[bool] = reactive(False)

    class JobSelected(Message):
        """Message sent when a job is selected."""

        def __init__(self, job: Job) -> None:
            self.job = job
            super().__init__()

    class ActionRequested(Message):
        """Message sent when an action is requested on a job."""

        def __init__(self, job: Job, action: str) -> None:
            self.job = job
            self.action = action
            super().__init__()

    def __init__(
        self,
        slurm_client: SlurmClient | None = None,
        refresh_interval: float = 10.0,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.slurm_client = slurm_client or SlurmClient()
        self.refresh_interval = refresh_interval
        self._timer = None
        self._selected_job: Job | None = None

    def compose(self) -> ComposeResult:
        # Section header
        with Horizontal(classes="section-header"):
            yield Static("Jobs", classes="section-title")
            yield Static("", id="jobs-count", classes="section-info")

        # Separator line
        yield Static("─" * 56, classes="separator")

        # Column header
        yield Static(
            "    ID       Name                   State    GPU     Time",
            classes="column-header",
        )
        yield Static("─" * 56, classes="header-separator")

        # Data table without header (we made our own)
        table = DataTable(zebra_stripes=False, show_header=False)
        table.cursor_type = "row"
        table.add_columns("id", "name", "state", "gpu", "time")
        yield table

    def on_mount(self) -> None:
        """Start timer and load initial data."""
        self.refresh_data()
        self._timer = self.set_interval(self.refresh_interval, self.refresh_data)

    def refresh_data(self) -> None:
        """Refresh job data."""
        try:
            self.jobs = self.slurm_client.get_jobs(all_users=self.show_all_users)
            self._update_table()
        except Exception:
            pass

    def _update_table(self) -> None:
        """Update the data table with current jobs."""
        table = self.query_one(DataTable)
        table.clear()

        for job in self.jobs:
            # Status symbol with color
            state = job.state
            symbol, color = STATUS_SYMBOLS.get(state, ("?", "#565f89"))
            state_display = f"[{color}]{symbol}[/] [{color}]{state:3}[/]"

            # GPU with color
            if job.gpus > 0:
                gpu_display = f"[#bb9af7]{job.gpus:2}[/]"
            else:
                gpu_display = "[#414868] -[/]"

            # Time format
            if job.runtime and job.runtime != "0:00":
                time_display = f"[#565f89]{job.runtime:>8}[/]"
            else:
                time_display = "[#414868]      —[/]"

            table.add_row(
                f"[#c0caf5]{job.job_id:>7}[/]",
                f"{job.name[:20]:<20}",
                state_display,
                gpu_display,
                time_display,
            )

        # Update count
        count_label = self.query_one("#jobs-count", Static)
        mode = "all" if self.show_all_users else "my jobs"
        count_label.update(f"{mode} ({len(self.jobs)})")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection."""
        if (
            event.row_key is not None
            and event.row_key.value is not None
            and event.row_key.value < len(self.jobs)
        ):
            self._selected_job = self.jobs[event.row_key.value]
            self.post_message(self.JobSelected(self._selected_job))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Notify of selection when cursor moves."""
        # Post message for job details panel (don't rebuild table - causes cursor reset)
        job = self.get_selected_job()
        if job:
            self.post_message(self.JobSelected(job))

    def get_selected_job(self) -> Job | None:
        """Get the currently selected job."""
        table = self.query_one(DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.jobs):
            return self.jobs[table.cursor_row]
        return None

    def toggle_all_users(self) -> None:
        """Toggle between showing own jobs and all jobs."""
        self.show_all_users = not self.show_all_users
        self.refresh_data()
