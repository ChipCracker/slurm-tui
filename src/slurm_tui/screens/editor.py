"""Editor Screen - Edit SLURM scripts with syntax highlighting."""

from __future__ import annotations

import os
from pathlib import Path
from glob import glob

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, ScrollableContainer
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Static, TextArea, Button, Input, ListView, ListItem, Label

from ..utils.bookmarks import BookmarkManager


class EditorScreen(Screen):
    """Screen for editing SLURM scripts."""

    DEFAULT_CSS = """
    EditorScreen {
        layout: horizontal;
        background: #1a1b26;
    }

    /* Sidebar */
    EditorScreen #sidebar {
        width: 30;
        height: 100%;
        background: #1a1b26;
        border-right: solid #414868;
    }

    EditorScreen #sidebar .sidebar-title {
        text-style: bold;
        color: #bb9af7;
        padding: 1 1 0 1;
    }

    EditorScreen #sidebar .section-title {
        color: #7aa2f7;
        padding: 1 1 0 1;
        text-style: bold;
    }

    EditorScreen #sidebar .separator {
        color: #414868;
        padding: 0 1;
    }

    EditorScreen #sidebar ListView {
        height: auto;
        max-height: 50%;
        background: transparent;
        padding: 0 1;
    }

    EditorScreen #sidebar ListItem {
        background: transparent;
        padding: 0 1;
    }

    EditorScreen #sidebar ListItem:hover {
        background: #24283b;
    }

    EditorScreen #sidebar ListItem.-active {
        background: #24283b;
    }

    EditorScreen #sidebar .file-item {
        color: #c0caf5;
    }

    EditorScreen #sidebar .bookmark-item {
        color: #e0af68;
    }

    EditorScreen #sidebar .no-items {
        color: #565f89;
        text-style: italic;
        padding: 0 2;
    }

    /* Main editor area */
    EditorScreen #main-editor {
        width: 1fr;
        height: 100%;
    }

    EditorScreen .editor-header {
        layout: horizontal;
        height: auto;
        padding: 1 2 0 2;
    }

    EditorScreen .editor-header .filename {
        width: 1fr;
        color: #7aa2f7;
        text-style: bold;
    }

    EditorScreen .editor-header .modified {
        width: auto;
        color: #e0af68;
    }

    EditorScreen .separator {
        color: #414868;
        padding: 0 2;
    }

    EditorScreen TextArea {
        height: 1fr;
        background: #1e2030;
        border: solid #414868;
        margin: 0 2 1 2;
    }

    EditorScreen TextArea:focus {
        border: solid #7aa2f7;
        background: #24283b;
    }

    EditorScreen .editor-footer {
        layout: horizontal;
        height: auto;
        padding: 0 2 1 2;
        align: left middle;
    }

    EditorScreen .editor-footer Button {
        margin-right: 1;
    }

    EditorScreen .file-picker {
        layout: horizontal;
        height: auto;
        padding: 0 2;
    }

    EditorScreen .file-picker Input {
        width: 1fr;
        background: #1e2030;
        border: solid #414868;
    }

    EditorScreen .file-picker Input:focus {
        background: #24283b;
        border: solid #7aa2f7;
    }

    EditorScreen .file-picker Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        ("ctrl+s", "save", "Save"),
        ("ctrl+q", "quit_editor", "Quit"),
        ("ctrl+o", "open_file", "Open"),
        ("escape", "quit_editor", "Quit"),
        ("ctrl+r", "refresh_sidebar", "Refresh"),
    ]

    modified: reactive[bool] = reactive(False)
    current_file: reactive[str | None] = reactive(None)

    def __init__(self, file_path: str | None = None):
        super().__init__()
        self._initial_file = file_path
        self._original_content = ""
        self.bookmark_manager = BookmarkManager()
        self._browse_dir = os.getcwd()

    def compose(self) -> ComposeResult:
        # Sidebar
        with Vertical(id="sidebar"):
            yield Static("Files", classes="sidebar-title")
            yield Static("─" * 28, classes="separator")

            yield Static("★ Bookmarks", classes="section-title")
            yield ListView(id="bookmarks-list")

            yield Static("─" * 28, classes="separator")
            yield Static("📁 Current Dir", classes="section-title")
            yield ListView(id="files-list")

        # Main editor area
        with Vertical(id="main-editor"):
            with Horizontal(classes="editor-header"):
                yield Static("No file open", id="filename", classes="filename")
                yield Static("", id="modified-indicator", classes="modified")

            yield Static("─" * 60, classes="separator")

            with Horizontal(classes="file-picker"):
                yield Input(placeholder="Enter file path...", id="file-input")
                yield Button("Open", variant="primary", id="open-btn")

            yield TextArea(language="bash", theme="monokai", id="editor")

            with Horizontal(classes="editor-footer"):
                yield Button("Save", variant="success", id="save")
                yield Button("Bookmark", variant="default", id="bookmark-btn")
                yield Button("Close", variant="default", id="close")

    def on_mount(self) -> None:
        """Load initial file if provided."""
        self._refresh_sidebar()

        if self._initial_file:
            self._load_file(self._initial_file)
            self.query_one("#file-input", Input).value = self._initial_file

    def _refresh_sidebar(self) -> None:
        """Refresh sidebar lists."""
        self._refresh_bookmarks()
        self._refresh_files()

    def _refresh_bookmarks(self) -> None:
        """Refresh bookmarks list."""
        bookmarks_list = self.query_one("#bookmarks-list", ListView)
        bookmarks_list.clear()

        scripts = self.bookmark_manager.get_scripts()
        if scripts:
            for script in scripts:
                item = ListItem(
                    Static(f"★ {script.name}", classes="bookmark-item"),
                    id=f"bm-{script.name}",
                )
                item._script_path = script.path  # Store path for later
                bookmarks_list.append(item)
        else:
            bookmarks_list.append(ListItem(Static("No bookmarks", classes="no-items")))

    def _refresh_files(self) -> None:
        """Refresh files list from current directory."""
        files_list = self.query_one("#files-list", ListView)
        files_list.clear()

        # Find SLURM scripts in current directory
        patterns = ["*.slurm", "*.sh", "*.sbatch"]
        files = []
        for pattern in patterns:
            files.extend(glob(os.path.join(self._browse_dir, pattern)))

        files = sorted(set(files))  # Remove duplicates and sort

        if files:
            for file_path in files[:20]:  # Limit to 20 files
                name = os.path.basename(file_path)
                item = ListItem(
                    Static(f"  {name}", classes="file-item"),
                    id=f"file-{name}",
                )
                item._script_path = file_path
                files_list.append(item)
        else:
            files_list.append(ListItem(Static("No scripts found", classes="no-items")))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle file selection from sidebar."""
        item = event.item
        if hasattr(item, "_script_path"):
            self._load_file(item._script_path)
            self.query_one("#file-input", Input).value = item._script_path

    def _load_file(self, path: str) -> bool:
        """Load a file into the editor."""
        try:
            path = os.path.abspath(path)

            if not os.path.exists(path):
                self.notify(f"File not found: {path}", severity="error")
                return False

            with open(path) as f:
                content = f.read()

            editor = self.query_one("#editor", TextArea)
            editor.load_text(content)

            self.current_file = path
            self._original_content = content
            self.modified = False

            # Update UI
            filename_label = self.query_one("#filename", Static)
            filename_label.update(f"{os.path.basename(path)}")

            self.notify(f"Loaded: {os.path.basename(path)}")
            return True

        except Exception as e:
            self.notify(f"Error loading file: {e}", severity="error")
            return False

    def _save_file(self, path: str | None = None) -> bool:
        """Save the editor content to a file."""
        if path is None:
            path = self.current_file

        if path is None:
            self.notify("No file specified", severity="error")
            return False

        try:
            path = os.path.abspath(path)
            editor = self.query_one("#editor", TextArea)
            content = editor.text

            with open(path, "w") as f:
                f.write(content)

            self.current_file = path
            self._original_content = content
            self.modified = False

            # Update UI
            filename_label = self.query_one("#filename", Static)
            filename_label.update(f"{os.path.basename(path)}")

            self.notify(f"Saved: {os.path.basename(path)}")
            self._refresh_files()  # Refresh in case new file was created
            return True

        except Exception as e:
            self.notify(f"Error saving file: {e}", severity="error")
            return False

    def watch_modified(self, modified: bool) -> None:
        """Update modified indicator."""
        indicator = self.query_one("#modified-indicator", Static)
        if modified:
            indicator.update("[modified]")
        else:
            indicator.update("")

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Track modifications."""
        if event.text_area.id == "editor":
            editor = self.query_one("#editor", TextArea)
            self.modified = editor.text != self._original_content

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "close":
            self.action_quit_editor()
        elif event.button.id == "save":
            self.action_save()
        elif event.button.id == "open-btn":
            self._open_from_input()
        elif event.button.id == "bookmark-btn":
            self._add_bookmark()

    def _open_from_input(self) -> None:
        """Open file from input field."""
        file_input = self.query_one("#file-input", Input)
        path = file_input.value.strip()

        if path:
            self._load_file(path)

    def _add_bookmark(self) -> None:
        """Bookmark the current file."""
        if self.current_file:
            if self.bookmark_manager.add_script(self.current_file):
                self.notify(f"Bookmarked: {os.path.basename(self.current_file)}")
                self._refresh_bookmarks()
            else:
                self.notify("Already bookmarked", severity="warning")
        else:
            self.notify("No file open", severity="warning")

    def action_save(self) -> None:
        """Save the current file."""
        if self.current_file:
            self._save_file()
        else:
            # Save to input path
            file_input = self.query_one("#file-input", Input)
            path = file_input.value.strip()
            if path:
                self._save_file(path)
            else:
                self.notify("Enter a file path first", severity="warning")

    def action_quit_editor(self) -> None:
        """Quit the editor."""
        if self.modified:
            self.notify("Unsaved changes! Press Ctrl+S to save or Escape again to discard")
        self.app.pop_screen()

    def action_open_file(self) -> None:
        """Focus the file input."""
        file_input = self.query_one("#file-input", Input)
        file_input.focus()

    def action_refresh_sidebar(self) -> None:
        """Refresh the sidebar."""
        self._refresh_sidebar()
        self.notify("Sidebar refreshed")
