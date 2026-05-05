"""Terminal Screen - Embedded terminal for job attachment."""

from __future__ import annotations

import asyncio
import os
import pty
import re
import signal
import struct
import fcntl
import termios

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, TextArea

from ..utils.slurm import Job


# Pre-compiled escape-sequence patterns. Keeping them at module level avoids
# re-parsing them on every PTY read (and the read path is hot under load).
_ESC_CSI = re.compile(r"\x1b\[[0-9;]*[HJKm]")
_ESC_CTRL = re.compile(r"\x1b\[[0-9;]*[ABCDEFGHJKSTfnsu]")
_ESC_OSC = re.compile(r"\x1b\][^\x07]*\x07")
_ESC_MODE = re.compile(r"\x1b[=>]")

# Tunable PTY read size — matches typical pipe buffer sizes.
_PTY_READ_BYTES = 4096

# How often to check whether the child process has exited. Cheap because it
# just inspects an attribute; we don't need millisecond precision here.
_PROCESS_EXIT_POLL_S = 0.5


class TerminalScreen(ModalScreen):
    """Modal screen with embedded terminal for job attachment."""

    DEFAULT_CSS = """
    TerminalScreen {
        align: center middle;
        background: rgba(26, 27, 38, 0.95);
    }

    TerminalScreen > Vertical {
        width: 90%;
        height: 90%;
        background: #1a1b26;
        border: solid #7aa2f7;
    }

    TerminalScreen .terminal-header {
        layout: horizontal;
        height: 1;
        padding: 0 1;
        background: #24283b;
    }

    TerminalScreen .terminal-title {
        width: 1fr;
        color: #7aa2f7;
        text-style: bold;
    }

    TerminalScreen .terminal-hint {
        width: auto;
        color: #565f89;
    }

    TerminalScreen .separator {
        color: #414868;
    }

    TerminalScreen #terminal-output {
        height: 1fr;
        background: #0d0e14;
        color: #c0caf5;
        border: none;
        padding: 0 1;
    }

    TerminalScreen #terminal-output:focus {
        border: none;
    }

    TerminalScreen .terminal-footer {
        height: 1;
        padding: 0 1;
        color: #565f89;
        background: #24283b;
    }
    """

    BINDINGS = [
        ("ctrl+d", "close_terminal", "Close"),
        ("escape", "close_terminal", "Close"),
    ]

    def __init__(self, job: Job, command: list[str]):
        super().__init__()
        self.job = job
        self.command = command
        self.process = None
        self.master_fd = None
        self._reader_registered = False
        self._exit_timer = None

    def compose(self) -> ComposeResult:
        with Vertical():
            with Vertical(classes="terminal-header"):
                yield Static(
                    f"Terminal - Job {self.job.job_id} - {self.job.name}",
                    classes="terminal-title",
                )
            yield Static("─" * 100, classes="separator")
            yield TextArea(
                "",
                id="terminal-output",
                read_only=False,
                show_line_numbers=False,
            )
            yield Static(
                "[Ctrl+D or Escape to close] [Type to interact]",
                classes="terminal-footer",
            )

    async def on_mount(self) -> None:
        """Start PTY process and register an async reader on the master FD."""
        try:
            # Create pseudo-terminal
            self.master_fd, slave_fd = pty.openpty()

            # Non-blocking master so add_reader callbacks return immediately
            # when the child has nothing more to write.
            flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            # Start the process
            self.process = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                preexec_fn=os.setsid,
            )

            # Close slave in parent
            os.close(slave_fd)

            # Set terminal size
            self._set_terminal_size()

            # Register an event-driven reader on the PTY master. This wakes
            # only when there's actual data — no 50ms polling loop, no
            # thread-pool round-trip per tick.
            loop = asyncio.get_event_loop()
            loop.add_reader(self.master_fd, self._on_pty_readable)
            self._reader_registered = True

            # Lightweight watchdog for child-process exit. Cheaper than
            # checking inside the hot read path.
            self._exit_timer = self.set_interval(
                _PROCESS_EXIT_POLL_S, self._check_process_exit
            )

            # Show initial command line and focus
            terminal = self.query_one("#terminal-output", TextArea)
            terminal.load_text(f"$ {' '.join(self.command)}\n")
            terminal.focus()

        except Exception as e:
            self._append_output(f"\nError starting terminal: {e}\n")

    def _set_terminal_size(self) -> None:
        """Set the PTY terminal size."""
        if self.master_fd is None:
            return

        try:
            terminal = self.query_one("#terminal-output", TextArea)
            rows = max(24, terminal.size.height)
            cols = max(80, terminal.size.width - 2)

            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
        except Exception:
            pass

    def _on_pty_readable(self) -> None:
        """Called by the event loop when the PTY master has data."""
        if self.master_fd is None:
            return

        try:
            data = os.read(self.master_fd, _PTY_READ_BYTES)
        except BlockingIOError:
            return
        except OSError:
            # PTY closed — child likely gone. Stop watching it.
            self._unregister_reader()
            return

        if not data:
            return

        text = self._process_terminal_output(
            data.decode("utf-8", errors="replace")
        )
        if text:
            self._append_output(text)

    def _check_process_exit(self) -> None:
        """Detect child exit and surface it once."""
        if self.process is None:
            return
        if self.process.returncode is None:
            return

        # Stop the watchdog and reader; surface a one-time exit notice.
        if self._exit_timer is not None:
            self._exit_timer.stop()
            self._exit_timer = None
        self._unregister_reader()
        self._append_output("\n[Process exited]\n")

    def _process_terminal_output(self, text: str) -> str:
        """Process terminal output, handling escape sequences."""
        # Strip the most common ANSI escape sequences. We use pre-compiled
        # patterns so this stays cheap on bursts of output.
        text = _ESC_CSI.sub("", text)
        text = _ESC_CTRL.sub("", text)
        text = _ESC_OSC.sub("", text)
        text = _ESC_MODE.sub("", text)

        # Handle carriage returns (simulate terminal behavior)
        lines = []
        current_line = ""

        for char in text:
            if char == '\r':
                current_line = ""
            elif char == '\n':
                lines.append(current_line)
                current_line = ""
            elif char == '\x08':  # Backspace
                current_line = current_line[:-1] if current_line else ""
            elif ord(char) >= 32 or char == '\t':  # Printable or tab
                current_line += char

        if current_line:
            lines.append(current_line)

        return '\n'.join(lines) if lines else ""

    def _append_output(self, text: str) -> None:
        """Append text to the terminal output without copying the buffer."""
        if not text:
            return

        try:
            terminal = self.query_one("#terminal-output", TextArea)
            # insert() is O(len(text)); load_text(current+text) was O(N) per
            # tick which became the dominant cost on long-running sessions.
            terminal.insert(text, terminal.document.end)
            self.call_after_refresh(lambda: terminal.scroll_end(animate=False))
        except Exception:
            pass

    def _unregister_reader(self) -> None:
        """Remove the PTY reader from the event loop (idempotent)."""
        if not self._reader_registered or self.master_fd is None:
            return
        try:
            asyncio.get_event_loop().remove_reader(self.master_fd)
        except Exception:
            pass
        self._reader_registered = False

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Handle text input - send to PTY."""
        # We handle input via on_key instead for better control
        pass

    def on_key(self, event) -> None:
        """Send keystrokes to PTY."""
        if self.master_fd is None:
            return

        # Handle special keys
        key = event.key
        char_to_send = None

        if key == "enter":
            char_to_send = "\n"
        elif key == "tab":
            char_to_send = "\t"
        elif key == "backspace":
            char_to_send = "\x7f"
        elif key == "delete":
            char_to_send = "\x1b[3~"
        elif key == "up":
            char_to_send = "\x1b[A"
        elif key == "down":
            char_to_send = "\x1b[B"
        elif key == "right":
            char_to_send = "\x1b[C"
        elif key == "left":
            char_to_send = "\x1b[D"
        elif key == "home":
            char_to_send = "\x1b[H"
        elif key == "end":
            char_to_send = "\x1b[F"
        elif key == "ctrl+c":
            char_to_send = "\x03"
        elif key == "ctrl+z":
            char_to_send = "\x1a"
        elif key == "ctrl+l":
            char_to_send = "\x0c"
        elif event.character and len(event.character) == 1:
            char_to_send = event.character

        if char_to_send:
            try:
                os.write(self.master_fd, char_to_send.encode())
                event.prevent_default()
            except Exception:
                pass

    def action_close_terminal(self) -> None:
        """Close the terminal and return to main screen."""
        self._cleanup()
        self.app.pop_screen()

    def _cleanup(self) -> None:
        """Clean up resources."""
        # Stop watchdog
        if self._exit_timer is not None:
            self._exit_timer.stop()
            self._exit_timer = None

        # Unhook reader before closing the FD (otherwise the loop may try
        # to call back into a closed descriptor on the next tick).
        self._unregister_reader()

        # Kill process
        if self.process and self.process.returncode is None:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except Exception:
                pass

        # Close master fd
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except Exception:
                pass
            self.master_fd = None

    def on_unmount(self) -> None:
        """Clean up when screen is unmounted."""
        self._cleanup()
