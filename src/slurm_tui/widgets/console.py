"""Console Widget - Embedded shell panel for running commands."""

from __future__ import annotations

import asyncio
import fcntl
import os
import pty
import signal
import struct
import termios

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.events import Resize
from textual.widget import Widget
from textual.widgets import Input, RichLog, Static


class ConsoleWidget(Widget):
    """Embeddable console panel with a persistent PTY shell session."""

    DEFAULT_CSS = """
    ConsoleWidget {
        height: 14;
        display: none;
        background: #0d0e14;
        border-top: solid #414868;
    }

    ConsoleWidget.visible {
        display: block;
    }

    ConsoleWidget > .console-header {
        layout: horizontal;
        height: 1;
        padding: 0 2;
        background: #24283b;
    }

    ConsoleWidget > .console-header > .console-title {
        width: 1fr;
        color: #7aa2f7;
        text-style: bold;
    }

    ConsoleWidget > .console-header > .console-hint {
        width: auto;
        color: #565f89;
    }

    ConsoleWidget > RichLog {
        height: 1fr;
        background: #0d0e14;
        padding: 0 2;
        scrollbar-background: #0d0e14;
        scrollbar-color: #414868;
    }

    ConsoleWidget > .console-input-row {
        height: 1;
        padding: 0 1;
        background: #0d0e14;
    }

    ConsoleWidget > .console-input-row > .console-prompt {
        width: 3;
        color: #9ece6a;
        padding: 0 0;
    }

    ConsoleWidget > .console-input-row > Input {
        width: 1fr;
        background: #0d0e14;
        border: none;
        padding: 0;
    }

    ConsoleWidget > .console-input-row > Input:focus {
        background: #0d0e14;
        border: none;
    }
    """

    BINDINGS = [
        ("escape", "unfocus", "Back"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._master_fd: int | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(classes="console-header"):
            yield Static("Console", classes="console-title")
            yield Static("Esc=back  `=toggle", classes="console-hint")
        yield RichLog(max_lines=1000, auto_scroll=True, markup=False)
        with Horizontal(classes="console-input-row"):
            yield Static(" > ", classes="console-prompt")
            yield Input(placeholder="enter command...", id="console-input")

    async def on_mount(self) -> None:
        """Start persistent shell session."""
        await self._start_shell()

    async def _start_shell(self) -> None:
        """Spawn a persistent PTY shell."""
        try:
            master_fd, slave_fd = pty.openpty()

            # Non-blocking reads on master
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            shell = os.environ.get("SHELL", "/bin/bash")
            self._process = await asyncio.create_subprocess_exec(
                shell,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                preexec_fn=os.setsid,
                env={**os.environ, "TERM": "xterm-256color"},
            )
            os.close(slave_fd)
            self._master_fd = master_fd

            # Set initial PTY size
            self._update_pty_size()

            # Start reading output
            self._reader_task = asyncio.create_task(self._read_output())

        except Exception as e:
            log = self.query_one(RichLog)
            log.write(Text(f"Error starting shell: {e}", style="bold red"))

    async def _read_output(self) -> None:
        """Async loop reading PTY output into RichLog."""
        loop = asyncio.get_event_loop()
        log = self.query_one(RichLog)

        while True:
            if self._process is None:
                break
            if self._process.returncode is not None:
                log.write(Text("[Shell exited. Press Enter to restart.]", style="#565f89"))
                break

            try:
                data = await loop.run_in_executor(None, self._read_pty)
                if data:
                    text = Text.from_ansi(data)
                    log.write(text)
            except Exception:
                break

            await asyncio.sleep(0.02)

    def _read_pty(self) -> str:
        """Read available data from PTY master fd (called in executor)."""
        if self._master_fd is None:
            return ""
        try:
            data = os.read(self._master_fd, 4096)
            if data:
                return data.decode("utf-8", errors="replace")
        except BlockingIOError:
            pass
        except OSError:
            pass
        return ""

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Send submitted command to the shell."""
        command = event.value
        event.input.value = ""

        if self._master_fd is None or (self._process and self._process.returncode is not None):
            # Shell died, restart it
            asyncio.create_task(self._start_shell())
            return

        try:
            os.write(self._master_fd, (command + "\n").encode())
        except OSError:
            log = self.query_one(RichLog)
            log.write(Text("[Error writing to shell]", style="bold red"))

    def on_resize(self, event: Resize) -> None:
        """Update PTY size when widget resizes."""
        self._update_pty_size()

    def _update_pty_size(self) -> None:
        """Set PTY window size to match widget dimensions."""
        if self._master_fd is None:
            return
        try:
            cols = max(self.size.width - 4, 80)
            rows = max(self.size.height - 3, 1)
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)
        except Exception:
            pass

    def action_unfocus(self) -> None:
        """Move focus back to the main content."""
        self.screen.query_one("DataTable").focus()

    def _cleanup(self) -> None:
        """Clean up shell process and file descriptors."""
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None

        if self._process and self._process.returncode is None:
            try:
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
            except Exception:
                pass
            self._process = None

        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except Exception:
                pass
            self._master_fd = None

    def on_unmount(self) -> None:
        """Clean up when widget is removed."""
        self._cleanup()
