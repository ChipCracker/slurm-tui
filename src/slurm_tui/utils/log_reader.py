"""Shared log file reader for job details and log viewer."""

from __future__ import annotations

import os


def read_log_file(path: str, tail: int = 1000) -> str:
    """Read log file tail efficiently with terminal simulation for carriage returns.

    tqdm writes progress bars using \\r without \\n, so a training log can
    contain megabytes of data on a single "line".  We split on both \\n and
    \\r to handle this correctly.
    """
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

        # Simulate terminal \r behaviour: keep only the last \r-segment per line
        result_lines = []
        for raw_line in content.split("\n"):
            if "\r" in raw_line:
                final = raw_line.rsplit("\r", 1)[-1]
                if final.strip():
                    result_lines.append(final)
            elif raw_line.strip():
                result_lines.append(raw_line)

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
