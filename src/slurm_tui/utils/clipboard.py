"""Cross-platform clipboard utility with SSH-friendly fallbacks."""

from __future__ import annotations

import base64
import shutil
import subprocess
import sys


def copy_to_clipboard(text: str) -> None:
    """Copy text to the system clipboard.

    Tries platform-native tools first, then falls back to the OSC 52
    escape sequence which works over SSH in modern terminals.

    Raises RuntimeError if all methods fail.
    """
    if sys.platform == "darwin":
        if _try_subprocess(["pbcopy"], text):
            return

    if sys.platform == "linux":
        for cmd in [
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
            ["wl-copy"],
        ]:
            if shutil.which(cmd[0]) and _try_subprocess(cmd, text):
                return

    # Universal fallback: OSC 52 escape sequence
    if _try_osc52(text):
        return

    raise RuntimeError(
        "No clipboard method available. "
        "Install xclip/xsel or use a terminal that supports OSC 52."
    )


def _try_subprocess(cmd: list[str], text: str) -> bool:
    """Try to copy text via a subprocess command."""
    try:
        subprocess.run(cmd, input=text.encode(), check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _try_osc52(text: str) -> bool:
    """Copy text via OSC 52 escape sequence written to the terminal."""
    try:
        encoded = base64.b64encode(text.encode()).decode()
        osc = f"\033]52;c;{encoded}\a"
        with open("/dev/tty", "w") as tty:
            tty.write(osc)
            tty.flush()
        return True
    except OSError:
        return False
