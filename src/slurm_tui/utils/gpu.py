"""GPU monitoring utilities."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime


@dataclass
class PartitionGPU:
    """GPU allocation for a partition."""

    partition: str
    allocated: int
    total: int

    @property
    def usage_percent(self) -> float:
        """Calculate usage percentage."""
        if self.total == 0:
            return 0.0
        return (self.allocated / self.total) * 100


@dataclass
class GPUHoursEntry:
    """GPU hours for a user."""

    hours: float
    user: str
    account: str
    cluster: str


class GPUMonitor:
    """Monitor GPU allocation and usage."""

    # Known partitions with GPU counts (can be overridden)
    DEFAULT_PARTITION_GPUS = {
        "p0": 8,
        "p1": 16,
        "p2": 32,
        "p4": 8,
    }

    def __init__(self, partition_gpus: dict[str, int] | None = None):
        self.partition_gpus = partition_gpus or self.DEFAULT_PARTITION_GPUS

    def _run_command(self, cmd: list[str], timeout: int = 30) -> tuple[str, str, int]:
        """Run a shell command and return stdout, stderr, returncode."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "", "Command timed out", 1
        except FileNotFoundError:
            return "", f"Command not found: {cmd[0]}", 1

    def get_partition_allocation(self) -> list[PartitionGPU]:
        """Get GPU allocation per partition.

        Adapted from show_alloc_gpus.sh
        """
        allocations = []

        for partition in self.partition_gpus:
            allocated = self._get_partition_gpu_count(partition)
            total = self.partition_gpus.get(partition, 0)

            # Try to get actual total from sinfo if possible
            actual_total = self._get_partition_total_gpus(partition)
            if actual_total > 0:
                total = actual_total

            allocations.append(
                PartitionGPU(
                    partition=partition,
                    allocated=allocated,
                    total=total,
                )
            )

        return allocations

    def _get_partition_gpu_count(self, partition: str) -> int:
        """Get allocated GPU count for a partition from squeue."""
        cmd = ["squeue", "-h", "-p", partition, "-t", "R", "-O", "gres:200"]
        stdout, stderr, rc = self._run_command(cmd)

        if rc != 0:
            return 0

        total = 0
        for line in stdout.strip().split("\n"):
            if not line:
                continue
            # Match gpu:type:N or gpu:N patterns
            for match in re.finditer(r"gpu(?::[^:,\s]+)?:(\d+)", line):
                total += int(match.group(1))

        return total

    def _get_partition_total_gpus(self, partition: str) -> int:
        """Get total GPU count for a partition from sinfo."""
        cmd = ["sinfo", "-h", "-p", partition, "-o", "%G"]
        stdout, stderr, rc = self._run_command(cmd)

        if rc != 0:
            return 0

        total = 0
        for line in stdout.strip().split("\n"):
            if not line or line == "(null)":
                continue
            # Match gpu:type:N or gpu:N patterns
            for match in re.finditer(r"gpu(?::[^:,\s]+)?:(\d+)", line):
                total += int(match.group(1))

        return total

    def get_gpu_hours(
        self,
        start: str | None = None,
        end: str | None = None,
        limit: int = 20,
    ) -> list[GPUHoursEntry]:
        """Get GPU hours per user.

        Adapted from check_slurm_gpu_hours.sh
        """
        entries = []

        # Default to current year
        if start is None:
            start = f"{datetime.now().year}-01-01"
        if end is None:
            end = f"{datetime.now().year}-12-31"

        cmd = [
            "sreport",
            "-n",
            "-P",
            "-t",
            "Hours",
            "-T",
            "gres/gpu",
            "cluster",
            "AccountUtilizationByUser",
            f"start={start}",
            f"end={end}",
        ]

        stdout, stderr, rc = self._run_command(cmd, timeout=60)

        if rc != 0:
            return entries

        # Parse output: fields are pipe-separated
        # Format varies but typically: Cluster|Account|User|Used|...
        for line in stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split("|")
            if len(parts) < 6:
                continue

            # Skip header-like lines and root/system accounts
            user = parts[2] if len(parts) > 2 else ""
            if not user or user in ("root", "thn", "cs", ""):
                continue

            try:
                hours = float(parts[5]) if parts[5] else 0.0
            except ValueError:
                continue

            if hours <= 0:
                continue

            entries.append(
                GPUHoursEntry(
                    hours=hours,
                    user=user,
                    account=parts[1] if len(parts) > 1 else "",
                    cluster=parts[0] if len(parts) > 0 else "",
                )
            )

        # Sort by hours descending and limit
        entries.sort(key=lambda x: x.hours, reverse=True)
        return entries[:limit]

    def discover_partitions(self) -> dict[str, int]:
        """Discover partitions with GPUs from sinfo."""
        partitions = {}

        cmd = ["sinfo", "-h", "-o", "%P|%G"]
        stdout, stderr, rc = self._run_command(cmd)

        if rc != 0:
            return self.partition_gpus

        for line in stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split("|")
            if len(parts) < 2:
                continue

            name = parts[0].rstrip("*")
            gres = parts[1]

            if gres and "gpu" in gres.lower():
                total = 0
                for match in re.finditer(r"gpu(?::[^:,\s]+)?:(\d+)", gres):
                    total += int(match.group(1))
                if total > 0:
                    partitions[name] = total

        return partitions if partitions else self.partition_gpus

    def is_available(self) -> bool:
        """Check if GPU monitoring commands are available."""
        _, _, rc = self._run_command(["squeue", "--version"])
        return rc == 0
