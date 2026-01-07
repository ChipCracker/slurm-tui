"""SLURM TUI - Main Application."""

from __future__ import annotations

from textual.app import App

from .screens.main import MainScreen


class SlurmTUI(App):
    """A modern TUI for SLURM cluster management."""

    TITLE = "SLURM TUI"
    SUB_TITLE = "GPU Cluster Management"

    CSS = """
    /* Tokyo Night Color Scheme - Borderless Modern */
    $background: #1a1b26;
    $surface: #1a1b26;
    $surface-alt: #1e2030;
    $primary: #7aa2f7;
    $secondary: #bb9af7;
    $success: #9ece6a;
    $warning: #e0af68;
    $error: #f7768e;
    $text: #c0caf5;
    $text-muted: #565f89;
    $separator: #414868;

    Screen {
        background: $background;
    }

    /* Borderless Footer - just keybindings */
    Footer {
        background: $background;
        color: $text-muted;
        height: 1;
        border: none;
    }

    Footer > .footer--key {
        background: transparent;
        color: $primary;
    }

    Footer > .footer--description {
        color: $text-muted;
    }

    /* DataTable - Borderless with subtle selection */
    DataTable {
        background: $background;
        border: none;
        scrollbar-background: $background;
        scrollbar-color: $separator;
    }

    DataTable > .datatable--cursor {
        background: $surface-alt;
        color: $text;
    }

    DataTable > .datatable--header {
        background: $background;
        color: $text-muted;
        text-style: none;
        border-bottom: none;
    }

    DataTable > .datatable--even-row {
        background: $background;
    }

    DataTable > .datatable--odd-row {
        background: $background;
    }

    /* Buttons - Minimal */
    Button {
        background: $surface-alt;
        color: $text;
        border: none;
        min-width: 8;
        padding: 0 2;
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

    /* Input fields - Borderless */
    Input {
        background: $surface-alt;
        border: none;
        padding: 0 1;
    }

    Input:focus {
        background: #24283b;
    }

    /* Select - Borderless */
    Select {
        background: $surface-alt;
        border: none;
    }

    Select:focus {
        background: #24283b;
    }

    /* TextArea - Borderless */
    TextArea {
        background: $background;
        border: none;
    }

    /* TabbedContent - Minimal */
    TabbedContent {
        background: $background;
    }

    Tabs {
        background: $background;
        border-bottom: solid $separator;
    }

    Tab {
        background: $background;
        color: $text-muted;
        padding: 0 2;
        border: none;
    }

    Tab.-active {
        background: $background;
        color: $primary;
        text-style: bold;
    }

    Tab:hover {
        color: $text;
    }

    TabPane {
        background: $background;
        padding: 1 0;
    }

    /* Toast notifications - Minimal */
    Toast {
        background: $surface-alt;
        border: none;
        color: $text;
    }

    /* Scrollbars - Subtle */
    Vertical:focus-within > ScrollBar,
    Horizontal:focus-within > ScrollBar {
        background: $background;
    }

    /* Separator line style */
    .separator {
        color: $separator;
        height: 1;
    }

    /* Section title style */
    .section-title {
        color: $text-muted;
        text-style: none;
        padding: 0;
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
