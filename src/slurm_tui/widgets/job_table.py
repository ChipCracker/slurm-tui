"""Job Table Widget - shows SLURM jobs in a DataTable.

Performance design:
    - Refreshes every 10s via a background thread worker (@work(thread=True))
      so subprocess calls never block the event loop.
    - Uses differential updates (update_cell_at) instead of clear+rebuild
      to preserve scroll position and avoid flicker.
    - Only adds/removes rows when the job count actually changes.
    - The worker is exclusive=True so a slow squeue can't pile up.
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Static, DataTable
from textual.widgets._data_table import Coordinate
from textual.widget import Widget
from textual.worker import get_current_worker

from ..utils.slurm import SlurmClient, Job


# Tokyo Night themed status symbols
STATUS_SYMBOLS = {
    "R": ("●", "#9ece6a"),    # Running  — green
    "PD": ("◐", "#e0af68"),   # Pending  — yellow
    "CD": ("✓", "#7aa2f7"),   # Completed — blue
    "CG": ("✓", "#7aa2f7"),   # Completing — blue
    "F": ("✗", "#f7768e"),    # Failed   — red
    "CA": ("⏹", "#565f89"),   # Cancelled — gray
    "TO": ("⏱", "#f7768e"),   # Timeout  — red
    "NF": ("✗", "#f7768e"),   # Node Fail — red
}

# Fixed-width column header; positions used for sort indicator overlay
BASE_HEADER = "    ID       Name                   State    Part      GPU     Time"

# (start, end) character positions of each column label in BASE_HEADER
COL_POSITIONS = [
    (4, 6),    # ID
    (13, 17),  # Name
    (36, 41),  # State
    (45, 49),  # Part
    (55, 58),  # GPU
    (63, 67),  # Time
]

SORT_COLUMN_NAMES = ["ID", "Name", "State", "Partition", "GPU", "Time"]

# DataTable column identifiers — used by add_columns() and update_cell_at()
COL_KEYS = ("id", "name", "state", "partition", "gpu", "time")


def _parse_runtime(runtime: str) -> int:
    """Parse SLURM runtime string (e.g. '1-02:30:00') to total seconds."""
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
    """SLURM job list with auto-refresh and in-place sorting.

    Posts JobSelected when the cursor moves and JobsRefreshed after each
    data refresh so other widgets (e.g. GPUHoursWidget) can react.
    """

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

    # ── Messages ──────────────────────────────────────────────────

    class JobSelected(Message):
        """Emitted when a job row is highlighted or selected."""

        def __init__(self, job: Job, explicit: bool = False) -> None:
            self.job = job
            self.explicit = explicit  # True = Enter/click, False = cursor move
            super().__init__()

    class JobsRefreshed(Message):
        """Emitted after a successful data refresh."""

        def __init__(self, jobs: list[Job]) -> None:
            self.jobs = jobs
            super().__init__()

    class ActionRequested(Message):
        """Emitted when a keybinding action targets a specific job."""

        def __init__(self, job: Job, action: str) -> None:
            self.job = job
            self.action = action
            super().__init__()

    # ── Init ──────────────────────────────────────────────────────

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
        self._sort_col_index: int | None = None  # None = natural order
        self._sort_reverse: bool = False
        self._display_jobs: list[Job] = []  # jobs in current display order

    def compose(self) -> ComposeResult:
        with Horizontal(classes="section-header"):
            yield Static("Jobs", classes="section-title")
            yield Static("", id="jobs-count", classes="section-info")

        yield Static("─" * 66, classes="separator")

        # Custom column header (DataTable's built-in header is hidden)
        yield Static(BASE_HEADER, id="column-header", classes="column-header")
        yield Static("─" * 66, classes="header-separator")

        # show_header=False: we render our own header with sort indicators
        table = DataTable(zebra_stripes=False, show_header=False)
        table.cursor_type = "row"
        table.add_columns(*COL_KEYS)
        yield table

    def on_mount(self) -> None:
        """Start the auto-refresh timer (first fetch is immediate)."""
        self.refresh_data()
        self._timer = self.set_interval(self.refresh_interval, self.refresh_data)

    # ── Data fetching ─────────────────────────────────────────────
    #
    # exclusive=True cancels any in-flight worker before starting a new
    # one, preventing stale data from overwriting fresh data.

    @work(thread=True, exclusive=True)
    def refresh_data(self) -> None:
        """Fetch jobs from squeue in a background thread."""
        worker = get_current_worker()
        try:
            jobs = self.slurm_client.get_jobs(all_users=self.show_all_users)
            if not worker.is_cancelled:
                self.app.call_from_thread(self._apply_refresh, jobs)
        except Exception:
            pass  # network/slurm errors are silently ignored to keep TUI alive

    def _apply_refresh(self, jobs: list[Job]) -> None:
        """Apply fetched data on the main thread (safe for UI updates)."""
        try:
            table = self.query_one(DataTable)
            # Remember which job was selected so we can restore cursor after update
            old_cursor_row = table.cursor_row
            old_job_id = None
            if old_cursor_row is not None and old_cursor_row < len(self._display_jobs):
                old_job_id = self._display_jobs[old_cursor_row].job_id
            self.jobs = jobs
            self._update_table(old_job_id)
        except Exception:
            pass

    # ── Table rendering ───────────────────────────────────────────
    #
    # Instead of clear() + add_row() (which resets scroll position),
    # we use update_cell_at() for existing rows and only add/remove
    # rows when the total count changes.  This is O(n*m) per refresh
    # but with typically <100 jobs and 6 columns it's negligible.

    @staticmethod
    def _render_job_row(job: Job) -> tuple:
        """Convert a Job into a tuple of Rich-markup cell strings."""
        symbol, color = STATUS_SYMBOLS.get(job.state, ("?", "#565f89"))
        state_display = f"[{color}]{symbol}[/] [{color}]{job.state:3}[/]"
        gpu_display = f"[#bb9af7]{job.gpus:2}[/]" if job.gpus > 0 else "[#414868] -[/]"
        time_display = (
            f"[#565f89]{job.runtime:>8}[/]"
            if job.runtime and job.runtime != "0:00"
            else "[#414868]      —[/]"
        )
        return (
            f"[#c0caf5]{job.job_id:>7}[/]",
            f"{job.name[:20]:<20}",
            state_display,
            f"[#7dcfff]{job.partition:<8}[/]",
            gpu_display,
            time_display,
        )

    def _update_table(self, old_job_id: str | None = None) -> None:
        """Differentially update the DataTable — no clear/rebuild.

        1. Sort the job list if a sort column is active.
        2. Update existing rows in-place via update_cell_at().
        3. Add new rows or remove excess rows as needed.
        4. Restore the cursor to the previously selected job.
        """
        table = self.query_one(DataTable)

        # Apply sort
        if self._sort_col_index is not None:
            self._display_jobs = sorted(
                self.jobs,
                key=self._get_sort_key,
                reverse=self._sort_reverse,
            )
        else:
            self._display_jobs = list(self.jobs)

        # Update the custom column header (shows sort indicator)
        self.query_one("#column-header", Static).update(self._build_column_header())

        # Render all rows
        new_rows = [self._render_job_row(job) for job in self._display_jobs]
        current_row_count = table.row_count

        # Try differential update first (preserves scroll position).
        # Fall back to clear+rebuild if anything goes wrong.
        try:
            for i, cells in enumerate(new_rows):
                if i < current_row_count:
                    for col_idx, value in enumerate(cells):
                        table.update_cell_at(
                            Coordinate(i, col_idx), value, update_width=False
                        )
                else:
                    table.add_row(*cells)

            # Remove excess rows
            while table.row_count > len(new_rows):
                last_key = list(table.rows.keys())[-1]
                table.remove_row(last_key)
        except Exception:
            # Fallback: clear and rebuild (resets scroll but always works)
            table.clear()
            for cells in new_rows:
                table.add_row(*cells)

        # Update job count label
        mode = "all" if self.show_all_users else "my jobs"
        self.query_one("#jobs-count", Static).update(f"{mode} ({len(self.jobs)})")

        # Notify other widgets
        self.post_message(self.JobsRefreshed(self.jobs))

        # Restore cursor to the same job (it may have moved due to sorting)
        if old_job_id is not None:
            for i, job in enumerate(self._display_jobs):
                if job.job_id == old_job_id:
                    table.move_cursor(row=i)
                    break

    # ── Sort ──────────────────────────────────────────────────────

    def _build_column_header(self) -> str:
        """Build the column header string, inserting a ▲/▼ sort indicator."""
        if self._sort_col_index is None:
            return BASE_HEADER
        indicator = "▲" if not self._sort_reverse else "▼"
        start, end = COL_POSITIONS[self._sort_col_index]
        col_text = BASE_HEADER[start:end]
        before = BASE_HEADER[:start]
        after = BASE_HEADER[end + 1:] if end < len(BASE_HEADER) else ""
        return f"{before}[#7aa2f7]{col_text}{indicator}[/]{after}"

    def _get_sort_key(self, job: Job):
        """Return a comparable sort key for the active sort column."""
        if self._sort_col_index == 0:    # ID — numeric sort
            try:
                return (0, int(job.job_id))
            except ValueError:
                return (1, job.job_id)   # non-numeric IDs sort after numeric
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
        """Cycle to the next sort column.  Wraps back to 'no sort' after Time.

        Sort direction toggles when pressing sort on the already-active column.
        """
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
        """Toggle ascending ↔ descending for the current sort column."""
        if self._sort_col_index is not None:
            self._sort_reverse = not self._sort_reverse
            self._update_table()

    # ── Row selection ─────────────────────────────────────────────

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter/click on a row — explicit selection."""
        job = self.get_selected_job()
        if job:
            self._selected_job = job
            self.post_message(self.JobSelected(job, explicit=True))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Cursor moved to a new row — passive highlight."""
        job = self.get_selected_job()
        if job:
            self.post_message(self.JobSelected(job))

    def get_selected_job(self) -> Job | None:
        """Return the Job under the cursor, or None."""
        table = self.query_one(DataTable)
        if table.cursor_row is not None and 0 <= table.cursor_row < len(self._display_jobs):
            return self._display_jobs[table.cursor_row]
        return None

    def toggle_all_users(self) -> None:
        """Toggle between own jobs and all users' jobs."""
        self.show_all_users = not self.show_all_users
        self.refresh_data()
