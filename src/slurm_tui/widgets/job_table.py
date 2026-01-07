"""Job Table Widget - shows SLURM jobs."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Static, DataTable
from textual.widget import Widget

from ..utils.slurm import SlurmClient, Job


class JobTableWidget(Widget):
    """Widget showing SLURM jobs in a table."""

    DEFAULT_CSS = """
    JobTableWidget {
        background: #24283b;
        border: round #414868;
        height: 1fr;
        padding: 1 2;
    }

    JobTableWidget > .jobs-header {
        layout: horizontal;
        height: 1;
        padding: 0 0 1 0;
    }

    JobTableWidget > .jobs-header > .jobs-title {
        width: 1fr;
        color: #7aa2f7;
        text-style: bold;
    }

    JobTableWidget > .jobs-header > .jobs-count {
        width: auto;
        color: #565f89;
    }

    JobTableWidget > .jobs-actions {
        height: 1;
        color: #565f89;
        padding: 1 0 0 0;
    }

    JobTableWidget > DataTable {
        height: 1fr;
        background: transparent;
    }

    JobTableWidget .no-jobs {
        color: #565f89;
        text-style: italic;
        padding: 1;
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
        from textual.containers import Horizontal

        with Horizontal(classes="jobs-header"):
            yield Static("Jobs", classes="jobs-title")
            yield Static("", id="jobs-count", classes="jobs-count")

        table = DataTable(zebra_stripes=True)
        table.cursor_type = "row"
        table.add_columns("ID", "Name", "State", "Part", "GPU", "CPU", "Time", "Node")
        yield table

        yield Static(
            "[a]ttach [c]ancel [l]ogs [u]sers [b]ookmark",
            classes="jobs-actions",
        )

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
            # Modern status badges with colors
            state = job.state
            if state == "R":
                state_display = "[#9ece6a bold]RUN[/]"
            elif state == "PD":
                state_display = "[#e0af68]PND[/]"
            elif state in ("CG", "CD"):
                state_display = "[#7aa2f7]" + state + "[/]"
            elif state == "F":
                state_display = "[#f7768e]FAIL[/]"
            else:
                state_display = f"[#565f89]{state}[/]"

            # GPU count with color
            gpu_display = f"[#bb9af7]{job.gpus}[/]" if job.gpus > 0 else "[#565f89]0[/]"

            table.add_row(
                f"[#7aa2f7]{job.job_id}[/]",
                job.name[:18],
                state_display,
                job.partition,
                gpu_display,
                str(job.cpus),
                f"[#565f89]{job.runtime}[/]",
                job.node[:8] if job.node else "-",
            )

        # Update count
        count_label = self.query_one("#jobs-count", Static)
        if self.show_all_users:
            count_label.update(f"all users ({len(self.jobs)})")
        else:
            count_label.update(f"my jobs ({len(self.jobs)})")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection."""
        if (
            event.row_key is not None
            and event.row_key.value is not None
            and event.row_key.value < len(self.jobs)
        ):
            self._selected_job = self.jobs[event.row_key.value]
            self.post_message(self.JobSelected(self._selected_job))

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
