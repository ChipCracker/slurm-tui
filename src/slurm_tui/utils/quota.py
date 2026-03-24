"""Disk quota monitoring via quota -s."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


@dataclass
class DiskQuota:
    """Represents a disk quota entry for one filesystem."""

    filesystem: str
    used: str       # human-readable, e.g. "150M"
    quota: str      # human-readable, e.g. "500M"
    limit: str      # human-readable, e.g. "600M"
    used_bytes: int
    quota_bytes: int

    @property
    def usage_percent(self) -> float:
        if self.quota_bytes == 0:
            return 0.0
        return min((self.used_bytes / self.quota_bytes) * 100, 100.0)


def _parse_size(s: str) -> int:
    """Parse human-readable size string to bytes (e.g. '150M' -> 157286400)."""
    s = s.strip().rstrip("*")
    if not s or s == "none" or s == "0":
        return 0
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([KMGTP]?)$", s, re.IGNORECASE)
    if not match:
        try:
            return int(s) * 1024  # plain number = KB in quota output
        except ValueError:
            return 0
    value = float(match.group(1))
    suffix = match.group(2).upper()
    multipliers = {"": 1024, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}
    return int(value * multipliers.get(suffix, 1024))


class QuotaMonitor:
    """Monitor disk quotas via quota -s."""

    def get_quotas(self) -> list[DiskQuota]:
        """Get disk quotas for the current user."""
        try:
            result = subprocess.run(
                ["quota", "-s"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return []
            return self._parse_output(result.stdout)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

    def _parse_output(self, output: str) -> list[DiskQuota]:
        """Parse quota -s output.

        Expected format:
        Disk quotas for user foo (uid 1234):
             Filesystem   space   quota   limit   grace   files   quota   limit   grace
             /dev/sda1    150M    500M    600M              1234   5000    6000
        """
        quotas = []
        lines = output.strip().split("\n")
        # Skip header lines (first 2)
        for line in lines[2:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 4:
                continue

            filesystem = parts[0]
            used_str = parts[1]
            quota_str = parts[2]
            limit_str = parts[3]

            used_bytes = _parse_size(used_str)
            quota_bytes = _parse_size(quota_str)

            quotas.append(
                DiskQuota(
                    filesystem=filesystem,
                    used=used_str.rstrip("*"),
                    quota=quota_str,
                    limit=limit_str,
                    used_bytes=used_bytes,
                    quota_bytes=quota_bytes,
                )
            )
        return quotas
