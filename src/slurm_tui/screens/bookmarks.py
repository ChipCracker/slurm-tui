"""Bookmarks Screen - View and manage bookmarked jobs and scripts."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, DataTable, Button, TabbedContent, TabPane

from ..utils.bookmarks import BookmarkManager


class BookmarksScreen(ModalScreen):
    """Modal screen for viewing and managing bookmarks."""

    DEFAULT_CSS = """
    BookmarksScreen {
        align: center middle;
    }

    BookmarksScreen > Vertical {
        width: 80%;
        height: 80%;
        border: thick $secondary;
        background: $surface;
    }

    BookmarksScreen .bookmarks-title {
        text-style: bold;
        text-align: center;
        padding: 1;
        background: $secondary-darken-2;
    }

    BookmarksScreen TabbedContent {
        height: 1fr;
    }

    BookmarksScreen DataTable {
        height: 1fr;
    }

    BookmarksScreen .bookmark-actions {
        height: auto;
        padding: 1;
        align: center middle;
        background: $surface-darken-1;
    }

    BookmarksScreen .bookmark-actions Button {
        margin: 0 1;
    }

    BookmarksScreen .no-bookmarks {
        text-align: center;
        color: $text-muted;
        padding: 2;
    }
    """

    BINDINGS = [
        ("escape", "close", "Close"),
        ("d", "delete", "Delete"),
        ("e", "edit", "Edit Script"),
    ]

    def __init__(self, bookmark_manager: BookmarkManager):
        super().__init__()
        self.bookmark_manager = bookmark_manager

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Bookmarks", classes="bookmarks-title")

            with TabbedContent():
                with TabPane("Jobs", id="jobs-tab"):
                    table = DataTable(id="jobs-table", zebra_stripes=True)
                    table.cursor_type = "row"
                    table.add_columns("JobID", "Name", "Added")
                    yield table

                with TabPane("Scripts", id="scripts-tab"):
                    table = DataTable(id="scripts-table", zebra_stripes=True)
                    table.cursor_type = "row"
                    table.add_columns("Name", "Path", "Added")
                    yield table

            with Horizontal(classes="bookmark-actions"):
                yield Button("Delete", variant="error", id="delete")
                yield Button("Edit Script", variant="primary", id="edit")
                yield Button("Close", variant="default", id="close")

    def on_mount(self) -> None:
        """Load bookmarks on mount."""
        self._refresh_tables()

    def _refresh_tables(self) -> None:
        """Refresh bookmark tables."""
        # Jobs table
        jobs_table = self.query_one("#jobs-table", DataTable)
        jobs_table.clear()

        for job in self.bookmark_manager.get_jobs():
            jobs_table.add_row(job.job_id, job.name, job.added)

        # Scripts table
        scripts_table = self.query_one("#scripts-table", DataTable)
        scripts_table.clear()

        for script in self.bookmark_manager.get_scripts():
            scripts_table.add_row(script.name, script.path, script.added)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "close":
            self.app.pop_screen()
        elif event.button.id == "delete":
            self.action_delete()
        elif event.button.id == "edit":
            self.action_edit()

    def action_close(self) -> None:
        """Close the bookmarks screen."""
        self.app.pop_screen()

    def action_delete(self) -> None:
        """Delete selected bookmark."""
        # Check which tab is active
        tabbed = self.query_one(TabbedContent)
        active_tab = tabbed.active

        if active_tab == "jobs-tab":
            self._delete_selected_job()
        elif active_tab == "scripts-tab":
            self._delete_selected_script()

    def _delete_selected_job(self) -> None:
        """Delete selected job bookmark."""
        table = self.query_one("#jobs-table", DataTable)

        if table.cursor_row is None:
            self.notify("No job selected", severity="warning")
            return

        jobs = self.bookmark_manager.get_jobs()
        if table.cursor_row >= len(jobs):
            return

        job = jobs[table.cursor_row]
        self.bookmark_manager.remove_job(job.job_id)
        self._refresh_tables()
        self.notify(f"Removed bookmark for job {job.job_id}")

    def _delete_selected_script(self) -> None:
        """Delete selected script bookmark."""
        table = self.query_one("#scripts-table", DataTable)

        if table.cursor_row is None:
            self.notify("No script selected", severity="warning")
            return

        scripts = self.bookmark_manager.get_scripts()
        if table.cursor_row >= len(scripts):
            return

        script = scripts[table.cursor_row]
        self.bookmark_manager.remove_script(script.path)
        self._refresh_tables()
        self.notify(f"Removed bookmark for {script.name}")

    def action_edit(self) -> None:
        """Open selected script in editor."""
        # Check which tab is active
        tabbed = self.query_one(TabbedContent)

        if tabbed.active != "scripts-tab":
            self.notify("Select a script to edit", severity="warning")
            return

        table = self.query_one("#scripts-table", DataTable)

        if table.cursor_row is None:
            self.notify("No script selected", severity="warning")
            return

        scripts = self.bookmark_manager.get_scripts()
        if table.cursor_row >= len(scripts):
            return

        script = scripts[table.cursor_row]

        # Open editor with the script
        from .editor import EditorScreen
        self.app.push_screen(EditorScreen(script.path))
