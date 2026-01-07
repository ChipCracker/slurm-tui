"""SLURM TUI - Main Application."""

from __future__ import annotations

from textual.app import App

from .screens.main import MainScreen


class SlurmTUI(App):
    """A modern TUI for SLURM cluster management."""

    TITLE = "SLURM TUI"
    SUB_TITLE = "GPU Cluster Management"

    CSS = """
    /* Tokyo Night Color Scheme */
    $background: #1a1b26;
    $surface: #24283b;
    $surface-light: #414868;
    $primary: #7aa2f7;
    $secondary: #bb9af7;
    $success: #9ece6a;
    $warning: #e0af68;
    $error: #f7768e;
    $text: #c0caf5;
    $text-muted: #565f89;
    $border: #414868;

    Screen {
        background: $background;
    }

    /* Minimal Footer */
    Footer {
        background: $surface;
        color: $text-muted;
        height: 1;
    }

    Footer > .footer--key {
        background: $surface-light;
        color: $primary;
    }

    /* DataTable - Clean look */
    DataTable {
        background: $surface;
        scrollbar-background: $surface;
        scrollbar-color: $surface-light;
    }

    DataTable > .datatable--cursor {
        background: $surface-light;
        color: $text;
    }

    DataTable > .datatable--header {
        background: $surface;
        color: $primary;
        text-style: bold;
    }

    DataTable > .datatable--even-row {
        background: $surface;
    }

    DataTable > .datatable--odd-row {
        background: #1e2030;
    }

    /* Progress bars */
    ProgressBar {
        padding: 0;
    }

    ProgressBar > .bar--bar {
        color: $success;
        background: $surface-light;
    }

    ProgressBar > .bar--complete {
        color: $success;
    }

    /* Buttons */
    Button {
        background: $surface-light;
        color: $text;
        border: none;
        min-width: 10;
    }

    Button:hover {
        background: $primary;
        color: $background;
    }

    Button.-primary {
        background: $primary;
        color: $background;
    }

    Button.-success {
        background: $success;
        color: $background;
    }

    Button.-error {
        background: $error;
        color: $background;
    }

    /* Input fields */
    Input {
        background: $surface;
        border: tall $border;
        padding: 0 1;
    }

    Input:focus {
        border: tall $primary;
    }

    /* Select */
    Select {
        background: $surface;
        border: tall $border;
    }

    Select:focus {
        border: tall $primary;
    }

    /* TextArea */
    TextArea {
        background: $surface;
        border: round $border;
    }

    /* TabbedContent */
    TabbedContent {
        background: $surface;
    }

    Tabs {
        background: $surface;
    }

    Tab {
        background: $surface;
        color: $text-muted;
        padding: 0 2;
    }

    Tab.-active {
        background: $surface-light;
        color: $primary;
    }

    Tab:hover {
        background: $surface-light;
    }

    TabPane {
        background: $surface;
        padding: 1;
    }

    /* Toast notifications */
    Toast {
        background: $surface;
        border: round $primary;
        color: $text;
    }

    /* Scrollbars */
    Vertical:focus-within > ScrollBar,
    Horizontal:focus-within > ScrollBar {
        background: $surface;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def on_mount(self) -> None:
        """Called when app is mounted."""
        self.push_screen(MainScreen())

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()


def main() -> None:
    """Main entry point."""
    app = SlurmTUI()
    result = app.run()

    # If we exited with a message (e.g., for attach command), print it
    if result:
        print(result)


if __name__ == "__main__":
    main()
