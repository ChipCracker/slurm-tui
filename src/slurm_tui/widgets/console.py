"""Console Widget - Embedded terminal with real shell via pyte."""

from __future__ import annotations

import asyncio
import fcntl
import os
import pty
import signal
import struct
import termios

import pyte
from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.events import Resize
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Static

# Map pyte color names to hex values (Tokyo Night palette where possible)
_PYTE_COLORS = {
    "black": "#1a1b26",
    "red": "#f7768e",
    "green": "#9ece6a",
    "yellow": "#e0af68",
    "blue": "#7aa2f7",
    "magenta": "#bb9af7",
    "cyan": "#7dcfff",
    "white": "#c0caf5",
    "default": None,
}

_PYTE_BRIGHT_COLORS = {
    "black": "#414868",
    "red": "#f7768e",
    "green": "#9ece6a",
    "yellow": "#e0af68",
    "blue": "#7aa2f7",
    "magenta": "#bb9af7",
    "cyan": "#7dcfff",
    "white": "#ffffff",
}


def _pyte_color_to_hex(color: str, bright: bool = False) -> str | None:
    """Convert a pyte color to a hex string."""
    if color == "default":
        return None
    # Direct hex codes (256-color or true-color from pyte)
    if len(color) == 6:
        try:
            int(color, 16)
            return f"#{color}"
        except ValueError:
            pass
    lookup = _PYTE_BRIGHT_COLORS if bright else _PYTE_COLORS
    return lookup.get(color)


class TerminalDisplay(Widget):
    """Widget that renders a pyte screen buffer."""

    can_focus = True

    DEFAULT_CSS = """
    TerminalDisplay {
        height: 1fr;
        background: #0d0e14;
        padding: 0 1;
    }

    TerminalDisplay:focus {
        background: #0d0e14;
    }
    """

    def __init__(self, screen: pyte.Screen, **kwargs):
        super().__init__(**kwargs)
        self._screen = screen

    def render_line(self, y: int) -> Strip:
        """Render a single line from the pyte screen buffer."""
        if y >= self._screen.lines:
            return Strip.blank(self.size.width)

        line = self._screen.buffer[y]
        text = Text(no_wrap=True, overflow="crop")

        for x in range(self._screen.columns):
            char_data = line[x]
            char = char_data.data or " "

            fg = _pyte_color_to_hex(char_data.fg, bold=char_data.bold)
            bg = _pyte_color_to_hex(char_data.bg)

            style = Style(
                color=fg or "#c0caf5",
                bgcolor=bg,
                bold=char_data.bold,
                italic=char_data.italics,
                underline=char_data.underscore,
                reverse=char_data.reverse,
            )
            text.append(char, style=style)

        # Show cursor
        if self.has_focus and y == self._screen.cursor.y:
            cx = self._screen.cursor.x
            if cx < len(text):
                cursor_style = Style(color="#1a1b26", bgcolor="#c0caf5")
                text.stylize(cursor_style, cx, cx + 1)

        return Strip([text.render(self.app.console)])


class ConsoleWidget(Widget):
    """Embeddable console panel with real terminal emulation."""

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
    """

    BINDINGS = [
        ("escape", "unfocus", "Back"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._master_fd: int | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        # Terminal emulation - initial size, will be updated on mount
        self._pty_screen = pyte.Screen(80, 10)
        self._pty_stream = pyte.Stream(self._pty_screen)

    def compose(self) -> ComposeResult:
        with Horizontal(classes="console-header"):
            yield Static("Console", classes="console-title")
            yield Static("Esc=back  `=toggle", classes="console-hint")
        yield TerminalDisplay(self._pty_screen, id="terminal-display")

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

            # Resize PTY + pyte screen to match widget
            self._sync_size()

            # Start reading output
            self._reader_task = asyncio.create_task(self._read_output())

        except Exception:
            pass

    async def _read_output(self) -> None:
        """Async loop reading PTY output into pyte screen."""
        loop = asyncio.get_event_loop()
        display = self.query_one("#terminal-display", TerminalDisplay)

        while True:
            if self._process is None or self._process.returncode is not None:
                break

            try:
                data = await loop.run_in_executor(None, self._read_pty)
                if data:
                    self._pty_stream.feed(data)
                    display.refresh()
            except Exception:
                break

            await asyncio.sleep(0.02)

    def _read_pty(self) -> str:
        """Read available data from PTY master fd."""
        if self._master_fd is None:
            return ""
        try:
            data = os.read(self._master_fd, 8192)
            if data:
                return data.decode("utf-8", errors="replace")
        except BlockingIOError:
            pass
        except OSError:
            pass
        return ""

    def on_key(self, event) -> None:
        """Forward all keystrokes to the PTY."""
        if self._master_fd is None:
            return

        # Let escape binding handle unfocus
        if event.key == "escape":
            return

        key = event.key
        char_to_send = None

        if key == "enter":
            char_to_send = "\r"
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
        elif key == "pageup":
            char_to_send = "\x1b[5~"
        elif key == "pagedown":
            char_to_send = "\x1b[6~"
        elif key == "ctrl+a":
            char_to_send = "\x01"
        elif key == "ctrl+b":
            char_to_send = "\x02"
        elif key == "ctrl+c":
            char_to_send = "\x03"
        elif key == "ctrl+d":
            char_to_send = "\x04"
        elif key == "ctrl+e":
            char_to_send = "\x05"
        elif key == "ctrl+k":
            char_to_send = "\x0b"
        elif key == "ctrl+l":
            char_to_send = "\x0c"
        elif key == "ctrl+r":
            char_to_send = "\x12"
        elif key == "ctrl+u":
            char_to_send = "\x15"
        elif key == "ctrl+w":
            char_to_send = "\x17"
        elif key == "ctrl+z":
            char_to_send = "\x1a"
        elif event.character and len(event.character) == 1:
            char_to_send = event.character

        if char_to_send:
            try:
                os.write(self._master_fd, char_to_send.encode())
                event.prevent_default()
                event.stop()
            except OSError:
                pass

    def on_resize(self, event: Resize) -> None:
        """Update PTY and pyte screen size."""
        self._sync_size()

    def _sync_size(self) -> None:
        """Sync PTY and pyte screen to widget dimensions."""
        try:
            display = self.query_one("#terminal-display", TerminalDisplay)
            cols = max(display.size.width - 2, 20)
            rows = max(display.size.height, 2)
        except Exception:
            cols, rows = 80, 10

        # Resize pyte screen
        self._pty_screen.resize(rows, cols)

        # Resize PTY
        if self._master_fd is not None:
            try:
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
