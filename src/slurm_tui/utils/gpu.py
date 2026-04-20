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
    non_preemptible: int = 0

    @property
    def preemptible(self) -> int:
        return self.allocated - self.non_preemptible

    @property
    def usage_percent(self) -> float:
        """Calculate usage percentage."""
        if self.total == 0:
            return 0.0
        return (self.allocated / self.total) * 100

    @property
    def non_preemptible_percent(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.non_preemptible / self.total) * 100


@dataclass
class GPUHoursEntry:
    """GPU hours for a user."""

    hours: float
    user: str
    account: str
    cluster: str


@dataclass
class NodeGPU:
    """GPU info for a single node."""

    node: str
    gpu_type: str
    gpu_count: int
    state: str
    cpus: int
    memory_mb: int
    free_memory_mb: int


@dataclass
class GPUStats:
    """Live GPU stats for a single GPU device."""

    index: int
    name: str
    utilization: float      # percent 0-100
    memory_used: float      # MiB
    memory_total: float     # MiB
    temperature: float      # Celsius
    power_draw: float       # Watts
    power_limit: float      # Watts

    @property
    def memory_percent(self) -> float:
        if self.memory_total == 0:
            return 0.0
        return (self.memory_used / self.memory_total) * 100

    @property
    def power_percent(self) -> float:
        if self.power_limit == 0:
            return 0.0
        return (self.power_draw / self.power_limit) * 100


class GPUMonitor:
    """Monitor GPU allocation and usage."""

    # Known partitions with GPU counts (can be overridden)
    DEFAULT_PARTITION_GPUS = {
        "p0": 8,
        "p1": 8,
        "p2": 8,
        "p4": 8,
        "p6": 4,
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
        """Get GPU allocation per partition using only 2 subprocess calls total."""
        # Single squeue call for all running jobs' GRES + QOS
        allocated_by_part: dict[str, int] = {}
        non_preempt_by_part: dict[str, int] = {}
        stdout, _, rc = self._run_command(
            ["squeue", "-h", "-t", "R", "-o", "%P|%b|%q"]
        )
        if rc == 0:
            for line in stdout.strip().split("\n"):
                if not line or "|" not in line:
                    continue
                parts = line.split("|")
                part_name = parts[0].strip().rstrip("*")
                gres = parts[1].strip() if len(parts) > 1 else ""
                qos = parts[2].strip() if len(parts) > 2 else ""
                if gres and "gpu" in gres.lower():
                    for match in re.finditer(r"gpu(?::[^:,\s]+)?:(\d+)", gres):
                        gpu_count = int(match.group(1))
                        allocated_by_part[part_name] = (
                            allocated_by_part.get(part_name, 0) + gpu_count
                        )
                        if qos != "preemptible":
                            non_preempt_by_part[part_name] = (
                                non_preempt_by_part.get(part_name, 0) + gpu_count
                            )

        # Single sinfo call for all partitions' total GPUs
        total_by_part: dict[str, int] = {}
        stdout, _, rc = self._run_command(
            ["sinfo", "-h", "-o", "%P|%G"]
        )
        if rc == 0:
            for line in stdout.strip().split("\n"):
                if not line or "|" not in line:
                    continue
                parts = line.split("|", 1)
                part_name = parts[0].strip().rstrip("*")
                gres = parts[1].strip() if len(parts) > 1 else ""
                if gres and "gpu" in gres.lower():
                    for match in re.finditer(r"gpu(?::[^:,\s]+)?:(\d+)", gres):
                        total_by_part[part_name] = (
                            total_by_part.get(part_name, 0) + int(match.group(1))
                        )

        allocations = []
        for partition in self.partition_gpus:
            total = total_by_part.get(partition, self.partition_gpus.get(partition, 0))
            allocated = allocated_by_part.get(partition, 0)
            non_preemptible = non_preempt_by_part.get(partition, 0)
            allocations.append(PartitionGPU(
                partition=partition,
                allocated=allocated,
                total=total,
                non_preemptible=non_preemptible,
            ))

        return allocations

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

    def get_partition_details(self, partition: str) -> list[NodeGPU]:
        """Get per-node GPU details for a partition."""
        cmd = ["sinfo", "-h", "-p", partition, "-N", "-o", "%N|%G|%T|%c|%m|%e"]
        stdout, stderr, rc = self._run_command(cmd)

        if rc != 0:
            return []

        nodes = []
        for line in stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|")
            if len(parts) < 6:
                continue

            node = parts[0]
            gres = parts[1]
            state = parts[2]

            # Parse GPU type and count from GRES (e.g. "gpu:rtx3090:2")
            gpu_type = "gpu"
            gpu_count = 0
            gres_match = re.search(r"gpu:([^:]+):(\d+)", gres)
            if gres_match:
                gpu_type = gres_match.group(1)
                gpu_count = int(gres_match.group(2))
            else:
                count_match = re.search(r"gpu:(\d+)", gres)
                if count_match:
                    gpu_count = int(count_match.group(1))

            try:
                cpus = int(parts[3])
            except ValueError:
                cpus = 0
            try:
                memory_mb = int(parts[4])
            except ValueError:
                memory_mb = 0
            try:
                free_memory_mb = int(parts[5])
            except ValueError:
                free_memory_mb = 0

            nodes.append(NodeGPU(
                node=node,
                gpu_type=gpu_type,
                gpu_count=gpu_count,
                state=state,
                cpus=cpus,
                memory_mb=memory_mb,
                free_memory_mb=free_memory_mb,
            ))

        return nodes

    def get_job_gpu_stats(self, job_id: str) -> list[GPUStats]:
        """Get live GPU stats for a running job via srun --overlap."""
        # srun --jobid only accepts numeric base IDs, strip array suffixes
        # e.g. '128430_0' -> '128430', '128430_[0-4]' -> '128430'
        base_id = job_id.split("_")[0] if "_" in job_id else job_id
        cmd = [
            "srun", "--overlap", f"--jobid={base_id}",
            "nvidia-smi",
            "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,"
            "temperature.gpu,power.draw,power.limit",
            "--format=csv,noheader,nounits",
        ]
        stdout, stderr, rc = self._run_command(cmd, timeout=10)
        if rc != 0:
            return []

        stats = []
        for line in stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 8:
                continue
            try:
                stats.append(GPUStats(
                    index=int(parts[0]),
                    name=parts[1],
                    utilization=float(parts[2]),
                    memory_used=float(parts[3]),
                    memory_total=float(parts[4]),
                    temperature=float(parts[5]),
                    power_draw=float(parts[6]) if parts[6] != "[N/A]" else 0.0,
                    power_limit=float(parts[7]) if parts[7] != "[N/A]" else 0.0,
                ))
            except (ValueError, IndexError):
                continue
        return stats

    def get_job_memory_stats(self, job_id: str) -> float | None:
        """Get MaxRSS (in MB) for a running job via sstat.

        Returns MaxRSS in MB, or None on failure.
        """
        for suffix in [".batch", ""]:
            cmd = [
                "sstat", "-j", f"{job_id}{suffix}",
                "--format=MaxRSS", "-n", "-P",
            ]
            stdout, _, rc = self._run_command(cmd, timeout=10)
            if rc != 0 or not stdout.strip():
                continue

            max_rss = 0.0
            for line in stdout.strip().split("\n"):
                val = line.strip()
                if not val:
                    continue
                mb = self._parse_slurm_mem(val)
                if mb > max_rss:
                    max_rss = mb
            if max_rss > 0:
                return max_rss

        return None

    @staticmethod
    def _parse_slurm_mem(value: str) -> float:
        """Parse SLURM memory strings like '4096K', '2048M', '1G' to MB."""
        value = value.strip()
        if not value:
            return 0.0
        try:
            if value.endswith("K"):
                return float(value[:-1]) / 1024
            elif value.endswith("M"):
                return float(value[:-1])
            elif value.endswith("G"):
                return float(value[:-1]) * 1024
            elif value.endswith("T"):
                return float(value[:-1]) * 1024 * 1024
            return float(value)
        except ValueError:
            return 0.0

    def is_available(self) -> bool:
        """Check if GPU monitoring commands are available."""
        _, _, rc = self._run_command(["squeue", "--version"])
        return rc == 0
