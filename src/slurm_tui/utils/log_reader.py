"""Shared log file reader for job details and log viewer."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _process_cr(content: str) -> list[str]:
    """Simulate terminal \\r behaviour: keep only the last \\r-segment per line.

    tqdm writes progress bars using \\r without \\n, so a training log can
    contain megabytes of data on a single "line".  We split on both \\n and
    \\r to handle this correctly.
    """
    result_lines: list[str] = []
    for raw_line in content.split("\n"):
        if "\r" in raw_line:
            final = raw_line.rsplit("\r", 1)[-1]
            if final.strip():
                result_lines.append(final)
        elif raw_line.strip():
            result_lines.append(raw_line)
    return result_lines


def read_log_file(path: str, tail: int = 1000) -> str:
    """Read log file tail efficiently with terminal simulation for carriage returns."""
    try:
        file_size = os.path.getsize(path)

        # For large files, only read the tail portion
        tail_bytes = 2 * 1024 * 1024  # 2MB
        truncated = False

        with open(path, "rb") as f:
            if file_size > tail_bytes:
                f.seek(-tail_bytes, 2)
                truncated = True
            raw = f.read()

        content = raw.decode("utf-8", errors="replace")
        result_lines = _process_cr(content)

        # Limit to last N lines
        if len(result_lines) > tail:
            result_lines = (
                [f"... ({len(result_lines) - tail} lines omitted) ..."]
                + result_lines[-tail:]
            )
        elif truncated:
            result_lines = ["... (showing tail of large file) ..."] + result_lines

        return "\n".join(result_lines)
    except Exception as e:
        return f"Error reading log: {e}"


@dataclass
class LogTail:
    """Track file position for incremental log reads."""

    path: str
    offset: int = 0
    _initialized: bool = field(default=False, repr=False)

    def reset(self) -> None:
        """Reset to uninitialized state (e.g. after file truncation)."""
        self.offset = 0
        self._initialized = False


def read_log_incremental(tail: LogTail, initial_tail: int = 1000) -> str | None:
    """Read new content from a log file incrementally.

    First call: behaves like read_log_file() — reads last 2MB, processes \\r,
    limits to *initial_tail* lines. Records file offset for future calls.

    Subsequent calls: seeks to saved offset, reads only new bytes, returns
    new lines prefixed with "\\n" so an insert at document-end doesn't merge
    with the last existing line.  Returns "" when there is no new data.

    Returns None on error or missing file.
    """
    try:
        if not os.path.exists(tail.path):
            return None

        file_size = os.path.getsize(tail.path)

        # Truncation detection: file shrank since last read
        if tail._initialized and file_size < tail.offset:
            tail.reset()

        if not tail._initialized:
            # --- initial load (same logic as read_log_file) ---
            tail_bytes = 2 * 1024 * 1024  # 2MB
            truncated = False

            with open(tail.path, "rb") as f:
                if file_size > tail_bytes:
                    f.seek(-tail_bytes, 2)
                    truncated = True
                raw = f.read()
                tail.offset = f.tell()

            content = raw.decode("utf-8", errors="replace")
            result_lines = _process_cr(content)

            if len(result_lines) > initial_tail:
                result_lines = (
                    [f"... ({len(result_lines) - initial_tail} lines omitted) ..."]
                    + result_lines[-initial_tail:]
                )
            elif truncated:
                result_lines = [
                    "... (showing tail of large file) ..."
                ] + result_lines

            tail._initialized = True
            return "\n".join(result_lines)

        # --- incremental read ---
        if file_size <= tail.offset:
            return ""  # no new data

        with open(tail.path, "rb") as f:
            f.seek(tail.offset)
            raw = f.read()
            tail.offset = f.tell()

        content = raw.decode("utf-8", errors="replace")
        new_lines = _process_cr(content)

        if not new_lines:
            return ""

        # Leading \n so insert at document end doesn't merge with last line
        return "\n" + "\n".join(new_lines)

    except Exception:
        return None
