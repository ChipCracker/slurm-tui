"""SLURM TUI - Main Application."""

from __future__ import annotations

from textual.app import App

from .screens.main import MainScreen


class SlurmTUI(App):
    """A modern TUI for SLURM cluster management."""

    TITLE = "SLURM TUI"
    SUB_TITLE = "GPU Cluster Management"

    CSS = """
    Screen {
        background: $surface;
    }

    Header {
        background: $primary-darken-2;
    }

    Footer {
        background: $primary-darken-3;
    }

    /* Progress bar styling */
    ProgressBar > .bar--bar {
        color: $success;
    }

    ProgressBar > .bar--complete {
        color: $success;
    }

    /* DataTable styling */
    DataTable {
        background: $surface;
    }

    DataTable > .datatable--cursor {
        background: $primary-darken-1;
    }

    DataTable > .datatable--header {
        background: $primary-darken-2;
        text-style: bold;
    }

    /* Widget titles */
    .gpu-title, .hours-title, .jobs-title {
        background: $primary-darken-2;
        padding: 0 1;
    }

    /* Notification styling */
    Toast {
        background: $surface;
        border: solid $primary;
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
