"""Job Table Widget - shows SLURM jobs."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Static, DataTable
from textual.widget import Widget
from textual.worker import get_current_worker

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

BASE_HEADER = "    ID       Name                   State    Part      GPU     Time"

# (start, end) positions of each column label in BASE_HEADER
COL_POSITIONS = [
    (4, 6),    # ID
    (13, 17),  # Name
    (36, 41),  # State
    (45, 49),  # Part
    (55, 58),  # GPU
    (63, 67),  # Time
]

SORT_COLUMN_NAMES = ["ID", "Name", "State", "Partition", "GPU", "Time"]


def _parse_runtime(runtime: str) -> int:
    """Parse SLURM runtime string to total seconds for sorting."""
    if not runtime or runtime == "0:00":
        return 0
    try:
        days = 0
        time_str = runtime
        if "-" in runtime:
            day_part, time_str = runtime.split("-", 1)
            days = int(day_part)
        parts = time_str.split(":")
        if len(parts) == 3:
            return days * 86400 + int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return days * 86400 + int(parts[0]) * 60 + int(parts[1])
        return 0
    except (ValueError, IndexError):
        return 0


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

    class JobsRefreshed(Message):
        """Message sent when the job list has been refreshed."""

        def __init__(self, jobs: list[Job]) -> None:
            self.jobs = jobs
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
        self._sort_col_index: int | None = None
        self._sort_reverse: bool = False
        self._display_jobs: list[Job] = []

    def compose(self) -> ComposeResult:
        # Section header
        with Horizontal(classes="section-header"):
            yield Static("Jobs", classes="section-title")
            yield Static("", id="jobs-count", classes="section-info")

        # Separator line
        yield Static("─" * 66, classes="separator")

        # Column header
        yield Static(
            BASE_HEADER,
            id="column-header",
            classes="column-header",
        )
        yield Static("─" * 66, classes="header-separator")

        # Data table without header (we made our own)
        table = DataTable(zebra_stripes=False, show_header=False)
        table.cursor_type = "row"
        table.add_columns("id", "name", "state", "partition", "gpu", "time")
        yield table

    def on_mount(self) -> None:
        """Start timer and load initial data."""
        self.refresh_data()
        self._timer = self.set_interval(self.refresh_interval, self.refresh_data)

    @work(thread=True, exclusive=True)
    def refresh_data(self) -> None:
        """Refresh job data in background thread."""
        worker = get_current_worker()
        try:
            jobs = self.slurm_client.get_jobs(all_users=self.show_all_users)
            if not worker.is_cancelled:
                self.app.call_from_thread(self._apply_refresh, jobs)
        except Exception:
            pass

    def _apply_refresh(self, jobs: list[Job]) -> None:
        """Apply refreshed job data on the main thread."""
        try:
            table = self.query_one(DataTable)
            old_cursor_row = table.cursor_row
            old_job_id = None
            if old_cursor_row is not None and old_cursor_row < len(self._display_jobs):
                old_job_id = self._display_jobs[old_cursor_row].job_id
            self.jobs = jobs
            self._update_table(old_job_id)
        except Exception:
            pass

    def _update_table(self, old_job_id: str | None = None) -> None:
        """Update the data table with current jobs."""
        table = self.query_one(DataTable)
        table.clear()

        # Sort jobs if sort is active
        if self._sort_col_index is not None:
            self._display_jobs = sorted(
                self.jobs,
                key=self._get_sort_key,
                reverse=self._sort_reverse,
            )
        else:
            self._display_jobs = list(self.jobs)

        # Update column header with sort indicator
        header = self.query_one("#column-header", Static)
        header.update(self._build_column_header())

        for job in self._display_jobs:
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

            # Partition
            partition_display = f"[#7dcfff]{job.partition:<8}[/]"

            table.add_row(
                f"[#c0caf5]{job.job_id:>7}[/]",
                f"{job.name[:20]:<20}",
                state_display,
                partition_display,
                gpu_display,
                time_display,
            )

        # Update count
        count_label = self.query_one("#jobs-count", Static)
        mode = "all" if self.show_all_users else "my jobs"
        count_label.update(f"{mode} ({len(self.jobs)})")

        # Notify other widgets about the refreshed job list
        self.post_message(self.JobsRefreshed(self.jobs))

        # Restore cursor position
        if old_job_id is not None:
            for i, job in enumerate(self._display_jobs):
                if job.job_id == old_job_id:
                    table.move_cursor(row=i)
                    break

    def _build_column_header(self) -> str:
        """Build column header string with sort indicator."""
        if self._sort_col_index is None:
            return BASE_HEADER

        indicator = "▲" if not self._sort_reverse else "▼"
        start, end = COL_POSITIONS[self._sort_col_index]
        col_text = BASE_HEADER[start:end]
        before = BASE_HEADER[:start]
        # Steal one trailing space for the indicator to keep alignment
        after = BASE_HEADER[end + 1:] if end < len(BASE_HEADER) else ""
        return f"{before}[#7aa2f7]{col_text}{indicator}[/]{after}"

    def _get_sort_key(self, job: Job):
        """Return sort key for the current sort column."""
        if self._sort_col_index == 0:  # ID
            try:
                return int(job.job_id)
            except ValueError:
                return job.job_id
        elif self._sort_col_index == 1:  # Name
            return job.name.lower()
        elif self._sort_col_index == 2:  # State
            return job.state
        elif self._sort_col_index == 3:  # Partition
            return job.partition
        elif self._sort_col_index == 4:  # GPU
            return job.gpus
        elif self._sort_col_index == 5:  # Time
            return _parse_runtime(job.runtime)
        return 0

    def cycle_sort(self) -> None:
        """Cycle to the next sort column."""
        if self._sort_col_index is None:
            self._sort_col_index = 0
            self._sort_reverse = False
        else:
            self._sort_col_index += 1
            if self._sort_col_index >= len(COL_POSITIONS):
                self._sort_col_index = None
                self._sort_reverse = False
        self._update_table()

    def toggle_sort_direction(self) -> None:
        """Toggle sort direction (asc/desc)."""
        if self._sort_col_index is not None:
            self._sort_reverse = not self._sort_reverse
            self._update_table()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection."""
        job = self.get_selected_job()
        if job:
            self._selected_job = job
            self.post_message(self.JobSelected(job))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Notify of selection when cursor moves."""
        job = self.get_selected_job()
        if job:
            self.post_message(self.JobSelected(job))

    def get_selected_job(self) -> Job | None:
        """Get the currently selected job."""
        table = self.query_one(DataTable)
        if table.cursor_row is not None and 0 <= table.cursor_row < len(self._display_jobs):
            return self._display_jobs[table.cursor_row]
        return None

    def toggle_all_users(self) -> None:
        """Toggle between showing own jobs and all jobs."""
        self.show_all_users = not self.show_all_users
        self.refresh_data()
