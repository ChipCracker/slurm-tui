"""Job Submit Screens - dialogs for job creation and management."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import (
    Static,
    Input,
    Button,
    Select,
    Label,
)

from ..utils.slurm import SlurmClient, Job


class JobSubmitScreen(ModalScreen):
    """Modal screen for submitting a new job."""

    DEFAULT_CSS = """
    JobSubmitScreen {
        align: center middle;
        background: rgba(26, 27, 38, 0.9);
    }

    JobSubmitScreen > Vertical {
        width: 60;
        height: auto;
        background: #1a1b26;
        padding: 1 2;
    }

    JobSubmitScreen .title {
        text-style: bold;
        text-align: center;
        color: #7aa2f7;
        padding: 0 0 1 0;
    }

    JobSubmitScreen .separator {
        color: #414868;
        margin-bottom: 1;
    }

    JobSubmitScreen .field-label {
        margin-top: 1;
        color: #565f89;
    }

    JobSubmitScreen Input {
        margin-bottom: 1;
        background: #1e2030;
        border: none;
    }

    JobSubmitScreen Input:focus {
        background: #24283b;
    }

    JobSubmitScreen Select {
        margin-bottom: 1;
        background: #1e2030;
        border: none;
    }

    JobSubmitScreen .buttons {
        layout: horizontal;
        align: center middle;
        height: auto;
        margin-top: 1;
        padding-top: 1;
    }

    JobSubmitScreen .buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self):
        super().__init__()
        self.slurm_client = SlurmClient()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Submit SLURM Job", classes="title")
            yield Static("─" * 56, classes="separator")

            yield Label("Script Path:", classes="field-label")
            yield Input(placeholder="/path/to/script.slurm", id="script-path")

            yield Label("Partition:", classes="field-label")
            yield Select(
                [
                    ("p0", "p0"),
                    ("p1", "p1"),
                    ("p2", "p2"),
                    ("p4", "p4"),
                ],
                value="p2",
                id="partition",
            )

            yield Label("GPUs:", classes="field-label")
            yield Input(value="1", id="gpus")

            yield Label("CPUs per Task:", classes="field-label")
            yield Input(value="12", id="cpus")

            yield Label("Memory per CPU:", classes="field-label")
            yield Input(value="10G", id="memory")

            yield Static("─" * 56, classes="separator")

            with Horizontal(classes="buttons"):
                yield Button("Cancel", variant="default", id="cancel")
                yield Button("Submit", variant="primary", id="submit")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.app.pop_screen()
        elif event.button.id == "submit":
            self._submit_job()

    def _submit_job(self) -> None:
        script_path = self.query_one("#script-path", Input).value

        if not script_path:
            self.notify("Please enter a script path", severity="error")
            return

        if not Path(script_path).exists():
            self.notify(f"Script not found: {script_path}", severity="error")
            return

        success, message = self.slurm_client.submit_job(script_path)

        if success:
            self.notify(message, severity="information")
            self.app.pop_screen()
        else:
            self.notify(f"Failed: {message}", severity="error")

    def action_cancel(self) -> None:
        self.app.pop_screen()


class InteractiveSessionScreen(ModalScreen):
    """Modal screen for starting an interactive session."""

    DEFAULT_CSS = """
    InteractiveSessionScreen {
        align: center middle;
        background: rgba(26, 27, 38, 0.9);
    }

    InteractiveSessionScreen > Vertical {
        width: 60;
        height: auto;
        background: #1a1b26;
        padding: 1 2;
    }

    InteractiveSessionScreen .title {
        text-style: bold;
        text-align: center;
        color: #bb9af7;
        padding: 0 0 1 0;
    }

    InteractiveSessionScreen .separator {
        color: #414868;
        margin-bottom: 1;
    }

    InteractiveSessionScreen .field-label {
        margin-top: 1;
        color: #565f89;
    }

    InteractiveSessionScreen Input {
        margin-bottom: 1;
        background: #1e2030;
        border: none;
    }

    InteractiveSessionScreen Input:focus {
        background: #24283b;
    }

    InteractiveSessionScreen Select {
        margin-bottom: 1;
        background: #1e2030;
        border: none;
    }

    InteractiveSessionScreen .buttons {
        layout: horizontal;
        align: center middle;
        height: auto;
        margin-top: 1;
        padding-top: 1;
    }

    InteractiveSessionScreen .buttons Button {
        margin: 0 1;
    }

    InteractiveSessionScreen .command-preview {
        background: #1e2030;
        padding: 1;
        margin-top: 1;
        color: #9ece6a;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self):
        super().__init__()
        self.slurm_client = SlurmClient()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Interactive SLURM Session", classes="title")
            yield Static("─" * 56, classes="separator")

            yield Label("Partition:", classes="field-label")
            yield Select(
                [
                    ("p0", "p0"),
                    ("p1", "p1"),
                    ("p2", "p2"),
                    ("p4", "p4"),
                ],
                value="p2",
                id="partition",
            )

            yield Label("GPUs:", classes="field-label")
            yield Input(value="1", id="gpus")

            yield Label("CPUs per Task:", classes="field-label")
            yield Input(value="4", id="cpus")

            yield Label("Memory per CPU:", classes="field-label")
            yield Input(value="4G", id="memory")

            yield Static("", id="command-preview", classes="command-preview")

            yield Static("─" * 56, classes="separator")

            with Horizontal(classes="buttons"):
                yield Button("Cancel", variant="default", id="cancel")
                yield Button("Start", variant="primary", id="start")

    def on_mount(self) -> None:
        self._update_preview()

    def on_input_changed(self, event: Input.Changed) -> None:
        self._update_preview()

    def on_select_changed(self, event: Select.Changed) -> None:
        self._update_preview()

    def _update_preview(self) -> None:
        partition = self.query_one("#partition", Select).value or "p2"
        gpus = self.query_one("#gpus", Input).value or "1"
        cpus = self.query_one("#cpus", Input).value or "4"
        memory = self.query_one("#memory", Input).value or "4G"

        cmd = self.slurm_client.start_interactive_session(
            partition=str(partition),
            gpus=int(gpus) if gpus.isdigit() else 1,
            cpus=int(cpus) if cpus.isdigit() else 4,
            memory=memory,
        )

        preview = self.query_one("#command-preview", Static)
        preview.update(f"$ {' '.join(cmd)}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.app.pop_screen()
        elif event.button.id == "start":
            self._start_session()

    def _start_session(self) -> None:
        partition = self.query_one("#partition", Select).value or "p2"
        gpus = self.query_one("#gpus", Input).value or "1"
        cpus = self.query_one("#cpus", Input).value or "4"
        memory = self.query_one("#memory", Input).value or "4G"

        cmd = self.slurm_client.start_interactive_session(
            partition=str(partition),
            gpus=int(gpus) if gpus.isdigit() else 1,
            cpus=int(cpus) if cpus.isdigit() else 4,
            memory=memory,
        )

        # Exit the TUI and show the command to run
        self.app.exit(message=f"Run the following command:\n{' '.join(cmd)}")

    def action_cancel(self) -> None:
        self.app.pop_screen()


class ConfirmCancelScreen(ModalScreen):
    """Modal screen to confirm job cancellation."""

    DEFAULT_CSS = """
    ConfirmCancelScreen {
        align: center middle;
        background: rgba(26, 27, 38, 0.9);
    }

    ConfirmCancelScreen > Vertical {
        width: 50;
        height: auto;
        background: #1a1b26;
        padding: 1 2;
    }

    ConfirmCancelScreen .title {
        text-style: bold;
        text-align: center;
        color: #f7768e;
        padding: 0 0 1 0;
    }

    ConfirmCancelScreen .separator {
        color: #414868;
        margin-bottom: 1;
    }

    ConfirmCancelScreen .message {
        text-align: center;
        padding: 1;
        color: #c0caf5;
    }

    ConfirmCancelScreen .job-info {
        text-align: center;
        padding: 1;
        background: #1e2030;
        margin: 1 0;
        color: #565f89;
    }

    ConfirmCancelScreen .buttons {
        layout: horizontal;
        align: center middle;
        height: auto;
        margin-top: 1;
        padding-top: 1;
    }

    ConfirmCancelScreen .buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("y", "confirm", "Confirm"),
        ("n", "cancel", "Cancel"),
    ]

    def __init__(self, job: Job):
        super().__init__()
        self.job = job
        self.slurm_client = SlurmClient()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("✗ Cancel Job?", classes="title")
            yield Static("─" * 46, classes="separator")

            yield Static("Are you sure you want to cancel this job?", classes="message")
            yield Static(
                f"JobID: {self.job.job_id}\n"
                f"Name: {self.job.name}\n"
                f"State: {self.job.state}",
                classes="job-info",
            )

            yield Static("─" * 46, classes="separator")

            with Horizontal(classes="buttons"):
                yield Button("No", variant="default", id="no")
                yield Button("Yes, Cancel", variant="error", id="yes")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "no":
            self.app.pop_screen()
        elif event.button.id == "yes":
            self._cancel_job()

    def _cancel_job(self) -> None:
        success, message = self.slurm_client.cancel_job(self.job.job_id)

        if success:
            self.notify(message, severity="information")
        else:
            self.notify(f"Failed: {message}", severity="error")

        self.app.pop_screen()

    def action_cancel(self) -> None:
        self.app.pop_screen()

    def action_confirm(self) -> None:
        self._cancel_job()
