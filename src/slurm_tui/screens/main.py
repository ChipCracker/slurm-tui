"""Main Screen - Dashboard with all widgets.

Two-column layout: left panel (GPU monitor, GPU hours, job table),
right panel (job details / script / logs / GPU stats).

Navigation:
    a      = attach to the selected running job
    s / x  = cycle sort column in the job table
    d      = toggle sort direction (asc/desc)
    y / ←  = focus left panel (DataTable)
    c / →  = focus right panel (logs TextArea)
    C      = cancel the selected job
    ↑ / ↓  = row navigation (DataTable) or cursor (TextArea)

Design decisions:
    - Arrow left/right are intercepted at Screen level via on_key() so they
      work regardless of which widget has focus. When a TextArea is editable
      we skip the intercept so the user can still move their cursor inside
      the script editor.
    - All data fetching happens in @work(thread=True) workers so the event
      loop is never blocked by subprocess calls.
    - Widget updates use Static.update() / update_cell_at() (imperative)
      instead of recompose() to avoid flicker and preserve scroll position.
"""

from __future__ import annotations

import os
import subprocess

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from ..widgets import GPUMonitorWidget, GPUHoursWidget, JobTableWidget, JobDetailsWidget
from ..utils.slurm import SlurmClient
from ..utils.gpu import GPUMonitor
from ..utils.bookmarks import BookmarkManager


class MainScreen(Screen):
    """Main dashboard screen.

    Keybinding philosophy:
        Restore the classic a/s/d workflow (attach, sort, sort direction),
        and move the panel-navigation cluster to y/x/c for QWERTZ keyboards.
        Arrow left/right remain aliases for panel switching.
    """

    DEFAULT_CSS = """
    MainScreen {
        layout: grid;
        grid-size: 1;
        grid-rows: auto 1fr auto;
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

    MainScreen > #main-content {
        layout: horizontal;
        height: 1fr;
    }

    MainScreen > #main-content > #left-panel {
        width: 50%;
        height: 100%;
    }

    MainScreen > #main-content > #left-panel > #top-panel {
        layout: horizontal;
        height: auto;
        min-height: 6;
        max-height: 10;
    }

    MainScreen > #main-content > #left-panel > #top-panel > GPUMonitorWidget {
        width: 1fr;
    }

    MainScreen > #main-content > #left-panel > #gpu-hours-panel {
        height: auto;
        max-height: 24;
    }

    MainScreen > #main-content > #left-panel > #bottom-panel {
        height: 1fr;
        margin-top: 1;
    }

    MainScreen > #main-content > #left-panel > #bottom-panel > JobTableWidget {
        width: 100%;
        height: 100%;
    }

    MainScreen > #main-content > JobDetailsWidget {
        width: 50%;
        height: 100%;
    }

    MainScreen > .keybindings {
        height: 1;
        padding: 0 2;
        color: #565f89;
        background: transparent;
    }
    """

    # ── Keybindings ───────────────────────────────────────────────
    #
    # Letter keys bubble up to the Screen reliably because DataTable doesn't
    # bind them. We keep legacy a/s/d actions and use y/x/c for the newer
    # left / sort / right navigation cluster.
    # Arrow left/right are handled in on_key() since DataTable binds
    # them for cursor_left/cursor_right (which we don't need in row mode).
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("n", "new_job", "New Job"),
        ("i", "interactive", "Interactive"),
        ("a", "attach", "Attach"),
        ("C", "cancel", "Cancel"),
        ("u", "toggle_users", "Toggle Users"),
        ("s,x", "sort", "Sort"),
        ("d", "sort_direction", "Sort ↕"),
        ("y", "focus_left", "← Left"),
        ("c", "focus_right", "→ Right"),
        ("o", "toggle_running", "Overview"),
        ("h", "toggle_hours", "GPU Hours"),
        ("g", "gpu_details", "GPU Details"),
        ("v", "gpu_stats", "GPU Stats"),
        ("w", "toggle_log_stream", "stderr/stdout"),
        ("l", "view_logs", "Logs"),
        ("b", "bookmarks", "Bookmarks"),
        ("B", "add_bookmark", "Add Bookmark"),
        ("ctrl+e", "toggle_edit_script", "Edit Script"),
        ("e", "editor", "Editor"),
        ("t", "toggle_console", "Terminal"),
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

        # Main 2-column layout
        with Horizontal(id="main-content"):
            # Left panel — GPU monitor, GPU hours, job table
            with Vertical(id="left-panel"):
                with Container(id="top-panel"):
                    yield GPUMonitorWidget(
                        gpu_monitor=self.gpu_monitor,
                        refresh_interval=10.0,
                    )
                with Container(id="gpu-hours-panel"):
                    yield GPUHoursWidget(
                        gpu_monitor=self.gpu_monitor,
                        refresh_interval=60.0,
                    )
                with Container(id="bottom-panel"):
                    yield JobTableWidget(
                        slurm_client=self.slurm_client,
                        refresh_interval=10.0,
                    )

            # Right panel — job details / script / logs
            yield JobDetailsWidget(
                slurm_client=self.slurm_client,
                bookmark_manager=self.bookmark_manager,
                id="details-panel",
            )

        # Footer showing available keybindings
        yield Static(
            "[#7aa2f7]y[/]←  [#7aa2f7]x/s[/]ort  [#7aa2f7]c[/]→  "
            "[#7aa2f7]a[/]ttach  [#7aa2f7]d[/]ir  [#7aa2f7]C[/]ancel  "
            "[#7aa2f7]r[/]efresh  "
            "[#7aa2f7]n[/]ew  [#7aa2f7]i[/]nteractive  [#7aa2f7]u[/]sers  "
            "[#7aa2f7]o[/]verview  [#7aa2f7]h[/]ours  "
            "[#7aa2f7]g[/]pu  [#7aa2f7]v[/]GPU  [#7aa2f7]w[/]stderr/out  "
            "[#7aa2f7]l[/]ogs  [#7aa2f7]b[/]ookmarks  "
            "[#7aa2f7]e[/]ditor  [#7aa2f7]t[/]erminal  [#7aa2f7]q[/]uit",
            classes="keybindings",
        )

    # ── Arrow key handling ───────────────────────────────────────
    #
    # DataTable binds left/right for cursor_left/cursor_right, but in
    # row cursor mode we don't need column navigation.  We override
    # on_key() to repurpose them for panel switching.
    # Skip only when an editable TextArea is focused so the user can still
    # move the cursor while editing the script.

    def on_key(self, event) -> None:
        """Repurpose arrow left/right for panel navigation."""
        from textual.widgets import TextArea
        focused = self.app.focused
        if isinstance(focused, TextArea) and not focused.read_only:
            return
        if event.key == "left":
            self.action_focus_left()
            event.prevent_default()
            event.stop()
        elif event.key == "right":
            self.action_focus_right()
            event.prevent_default()
            event.stop()

    # ── Message handlers ──────────────────────────────────────────

    def on_job_table_widget_job_selected(self, message: JobTableWidget.JobSelected) -> None:
        """Update right panel when a job is selected/highlighted in the table."""
        details_panel = self.query_one(JobDetailsWidget)

        # When GPU stats view is active, follow cursor to show new job's stats
        if details_panel._showing_gpu_stats:
            if message.job.state == "R":
                if not details_panel._gpu_stats_job or details_panel._gpu_stats_job.job_id != message.job.job_id:
                    details_panel.show_gpu_stats(message.job, self.gpu_monitor)
            elif message.explicit:
                details_panel.update_job(message.job, force=True)
            return

        if message.explicit:
            gpu_widget = self.query_one(GPUMonitorWidget)
            gpu_widget._detail_index = -1
            details_panel.update_job(message.job, force=True)
        else:
            details_panel.update_job(message.job)

    def on_job_table_widget_jobs_refreshed(self, message: JobTableWidget.JobsRefreshed) -> None:
        """Forward refreshed jobs to GPU hours widget for running jobs summary."""
        gpu_hours = self.query_one(GPUHoursWidget)
        gpu_hours.update_running_jobs(message.jobs)

    # ── Actions ───────────────────────────────────────────────────

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()

    def action_refresh(self) -> None:
        """Trigger an immediate refresh of all widgets."""
        gpu_monitor = self.query_one(GPUMonitorWidget)
        gpu_monitor.refresh_data()

        gpu_hours = self.query_one(GPUHoursWidget)
        gpu_hours.refresh_data()

        job_table = self.query_one(JobTableWidget)
        job_table.refresh_data()

        details_panel = self.query_one(JobDetailsWidget)
        details_panel.refresh_logs()

        self.notify("Data refreshed")

    def action_focus_left(self) -> None:
        """Move focus to the left panel (job table's DataTable)."""
        try:
            from textual.widgets import DataTable
            self.query_one(DataTable).focus()
            self.notify("← focus left")
        except Exception as e:
            self.notify(f"focus_left error: {e}", severity="error")

    def action_focus_right(self) -> None:
        """Move focus to the right panel (logs TextArea).

        Prefers the logs area (2nd TextArea) so the user can scroll logs
        immediately.  Falls back to the script area if no logs are shown.
        """
        try:
            from textual.widgets import TextArea
            details = self.query_one(JobDetailsWidget)
            text_areas = list(details.query(TextArea))
            if len(text_areas) > 1:
                text_areas[1].focus()
            elif text_areas:
                text_areas[0].focus()
            self.notify("→ focus right")
        except Exception as e:
            self.notify(f"focus_right error: {e}", severity="error")

    def action_sort(self) -> None:
        """Cycle sort column in the job table (ID → Name → State → …)."""
        try:
            job_table = self.query_one(JobTableWidget)
            job_table.cycle_sort()
            self.notify("sort cycled")
        except Exception as e:
            self.notify(f"sort error: {e}", severity="error")

    def action_sort_direction(self) -> None:
        """Toggle sort direction for the active sort column."""
        try:
            job_table = self.query_one(JobTableWidget)
            job_table.toggle_sort_direction()
            self.notify("sort direction toggled")
        except Exception as e:
            self.notify(f"sort direction error: {e}", severity="error")

    def action_toggle_log_stream(self) -> None:
        """Toggle between stderr and stdout in the details panel."""
        details_panel = self.query_one(JobDetailsWidget)
        details_panel.toggle_log_stream()

    def action_toggle_edit_script(self) -> None:
        """Toggle script read-only ↔ editable in the details panel."""
        details_panel = self.query_one(JobDetailsWidget)
        details_panel.toggle_edit_script()

    def action_new_job(self) -> None:
        """Show the new batch job submission dialog."""
        from .job_submit import JobSubmitScreen
        self.app.push_screen(JobSubmitScreen())

    def action_interactive(self) -> None:
        """Show the interactive session dialog."""
        from .job_submit import InteractiveSessionScreen
        self.app.push_screen(InteractiveSessionScreen())

    def action_attach(self) -> None:
        """Attach to selected running job — suspends TUI, resumes on exit."""
        job_table = self.query_one(JobTableWidget)
        job = job_table.get_selected_job()

        if job is None:
            self.notify("No job selected", severity="warning")
            return
        if job.state != "R":
            self.notify(f"Job {job.job_id} is not running (state: {job.state})", severity="warning")
            return

        cmd = self.slurm_client.attach_to_job(job.job_id)
        with self.app.suspend():
            subprocess.run(cmd)

    def action_cancel(self) -> None:
        """Cancel selected job (with confirmation dialog)."""
        job_table = self.query_one(JobTableWidget)
        job = job_table.get_selected_job()

        if job is None:
            self.notify("No job selected", severity="warning")
            return

        from .job_submit import ConfirmCancelScreen
        self.app.push_screen(ConfirmCancelScreen(job))

    def action_toggle_users(self) -> None:
        """Toggle between own jobs and all users' jobs."""
        job_table = self.query_one(JobTableWidget)
        job_table.toggle_all_users()

    def action_gpu_stats(self) -> None:
        """Show live per-GPU stats for the selected running job."""
        job_table = self.query_one(JobTableWidget)
        job = job_table.get_selected_job()

        if job is None:
            self.notify("No job selected", severity="warning")
            return
        if job.state != "R":
            self.notify(f"Job {job.job_id} is not running", severity="warning")
            return

        details_panel = self.query_one(JobDetailsWidget)
        details_panel.show_gpu_stats(job, self.gpu_monitor)

    def action_toggle_running(self) -> None:
        """Toggle running jobs overview expanded/compact."""
        gpu_hours = self.query_one(GPUHoursWidget)
        gpu_hours.toggle_expanded()

    def action_toggle_hours(self) -> None:
        """Toggle GPU hours leaderboard collapsed/expanded."""
        gpu_hours = self.query_one(GPUHoursWidget)
        gpu_hours.toggle_hours()

    def action_gpu_details(self) -> None:
        """Cycle through partition details in the right panel."""
        gpu_widget = self.query_one(GPUMonitorWidget)
        partition = gpu_widget.cycle_partition_detail()
        details_panel = self.query_one(JobDetailsWidget)
        if partition is None:
            details_panel.update_job(None, force=True)
            self.notify("GPU details closed")
        else:
            details_panel.update_partition(partition, self.gpu_monitor)

    def action_help(self) -> None:
        """Show keybinding cheatsheet as notification."""
        self.notify(
            "y/c or ←/→=Panel  x/s=Sort  d=Dir  a=Attach  C=Cancel  "
            "n=New  l=Logs  b=Bookmarks  e=Editor  w=stderr/stdout  q=Quit",
            timeout=5,
        )

    def action_view_logs(self) -> None:
        """Open full-screen log viewer for the selected job."""
        job_table = self.query_one(JobTableWidget)
        job = job_table.get_selected_job()

        if job is None:
            self.notify("No job selected", severity="warning")
            return

        from .log_viewer import LogViewerScreen
        self.app.push_screen(LogViewerScreen(job, self.slurm_client))

    def action_bookmarks(self) -> None:
        """Open bookmarks screen."""
        from .bookmarks import BookmarksScreen
        self.app.push_screen(BookmarksScreen(self.bookmark_manager))

    def action_add_bookmark(self) -> None:
        """Bookmark the currently selected job."""
        job_table = self.query_one(JobTableWidget)
        job = job_table.get_selected_job()

        if job is None:
            self.notify("No job selected", severity="warning")
            return

        self.bookmark_manager.add_job(job.job_id, job.name)
        self.notify(f"Bookmarked job {job.job_id}")

    def action_toggle_console(self) -> None:
        """Open a native shell, suspending the TUI until exit."""
        shell = os.environ.get("SHELL", "/bin/bash")
        with self.app.suspend():
            print("\033[1;34m=== SLURM TUI Console ===\033[0m")
            print("Type \033[1mexit\033[0m or press \033[1mCtrl+D\033[0m to return to the TUI.\n")
            subprocess.run(shell)

    def action_editor(self) -> None:
        """Open the built-in script editor screen."""
        from .editor import EditorScreen
        self.app.push_screen(EditorScreen())
