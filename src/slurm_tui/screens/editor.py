"""Editor Screen - Edit SLURM scripts with syntax highlighting."""

from __future__ import annotations

import os
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Static, TextArea, Button, Input, Header, Footer

from ..utils.bookmarks import BookmarkManager


class EditorScreen(Screen):
    """Screen for editing SLURM scripts."""

    DEFAULT_CSS = """
    EditorScreen {
        layout: grid;
        grid-size: 1;
        grid-rows: auto 1fr auto;
    }

    EditorScreen .editor-header {
        layout: horizontal;
        height: auto;
        padding: 1;
        background: $primary-darken-2;
    }

    EditorScreen .editor-header .filename {
        width: 1fr;
        text-style: bold;
    }

    EditorScreen .editor-header .modified {
        width: auto;
        color: $warning;
    }

    EditorScreen TextArea {
        height: 1fr;
    }

    EditorScreen .editor-footer {
        layout: horizontal;
        height: auto;
        padding: 1;
        background: $surface-darken-1;
        align: center middle;
    }

    EditorScreen .editor-footer Button {
        margin: 0 1;
    }

    EditorScreen .file-picker {
        layout: horizontal;
        height: auto;
        padding: 1;
        background: $surface-darken-1;
    }

    EditorScreen .file-picker Input {
        width: 1fr;
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
    ]

    modified: reactive[bool] = reactive(False)
    current_file: reactive[str | None] = reactive(None)

    def __init__(self, file_path: str | None = None):
        super().__init__()
        self._initial_file = file_path
        self._original_content = ""
        self.bookmark_manager = BookmarkManager()

    def compose(self) -> ComposeResult:
        yield Header()

        with Horizontal(classes="editor-header"):
            yield Static("No file open", id="filename", classes="filename")
            yield Static("", id="modified-indicator", classes="modified")

        with Horizontal(classes="file-picker"):
            yield Input(placeholder="Enter file path...", id="file-input")
            yield Button("Open", variant="primary", id="open-btn")
            yield Button("Bookmark", variant="default", id="bookmark-btn")

        yield TextArea(language="bash", theme="monokai", id="editor")

        with Horizontal(classes="editor-footer"):
            yield Button("Save", variant="success", id="save")
            yield Button("Save As...", variant="primary", id="save-as")
            yield Button("Close", variant="default", id="close")

        yield Footer()

    def on_mount(self) -> None:
        """Load initial file if provided."""
        if self._initial_file:
            self._load_file(self._initial_file)
            # Set the input field to the file path
            self.query_one("#file-input", Input).value = self._initial_file

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
            filename_label.update(f"Editing: {path}")

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
            filename_label.update(f"Editing: {path}")

            self.notify(f"Saved: {os.path.basename(path)}")
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
        editor = self.query_one("#editor", TextArea)
        self.modified = editor.text != self._original_content

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "close":
            self.action_quit_editor()
        elif event.button.id == "save":
            self.action_save()
        elif event.button.id == "save-as":
            self._save_as()
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

    def _save_as(self) -> None:
        """Save to the path in the input field."""
        file_input = self.query_one("#file-input", Input)
        path = file_input.value.strip()

        if path:
            self._save_file(path)
        else:
            self.notify("Enter a file path first", severity="warning")

    def _add_bookmark(self) -> None:
        """Bookmark the current file."""
        if self.current_file:
            if self.bookmark_manager.add_script(self.current_file):
                self.notify(f"Bookmarked: {os.path.basename(self.current_file)}")
            else:
                self.notify("Already bookmarked", severity="warning")
        else:
            self.notify("No file open", severity="warning")

    def action_save(self) -> None:
        """Save the current file."""
        if self.current_file:
            self._save_file()
        else:
            self._save_as()

    def action_quit_editor(self) -> None:
        """Quit the editor."""
        if self.modified:
            self.notify("Unsaved changes! Press Ctrl+S to save or Escape again to discard")
            # Could implement confirmation dialog here
        self.app.pop_screen()

    def action_open_file(self) -> None:
        """Focus the file input."""
        file_input = self.query_one("#file-input", Input)
        file_input.focus()
