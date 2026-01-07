"""SLURM command wrappers."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class Job:
    """Represents a SLURM job."""

    job_id: str
    name: str
    state: str
    partition: str
    gpus: int
    cpus: int
    memory: str
    runtime: str
    node: str


@dataclass
class Partition:
    """Represents a SLURM partition."""

    name: str
    state: str
    total_nodes: int
    avail_nodes: int
    total_cpus: int
    avail_cpus: int


class SlurmClient:
    """Client for interacting with SLURM."""

    def __init__(self):
        self.username = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))

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

    def get_jobs(self, user: Optional[str] = None, all_users: bool = False) -> list[Job]:
        """Get list of jobs from squeue."""
        jobs = []

        # Format: JobID|Name|State|Partition|GRES|NumCPUs|MinMemory|TimeUsed|NodeList
        fmt = "%i|%j|%t|%P|%b|%C|%m|%M|%N"

        cmd = ["squeue", "-h", "-o", fmt]
        if not all_users:
            cmd.extend(["-u", user or self.username])

        stdout, stderr, rc = self._run_command(cmd)
        if rc != 0:
            return jobs

        for line in stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split("|")
            if len(parts) < 9:
                continue

            # Parse GPU count from GRES (e.g., "gpu:4" or "gpu:a100:4")
            gpus = 0
            gres = parts[4]
            if gres and "gpu" in gres.lower():
                match = re.search(r"gpu(?::[^:]+)?:(\d+)", gres)
                if match:
                    gpus = int(match.group(1))

            jobs.append(
                Job(
                    job_id=parts[0],
                    name=parts[1],
                    state=parts[2],
                    partition=parts[3],
                    gpus=gpus,
                    cpus=int(parts[5]) if parts[5].isdigit() else 0,
                    memory=parts[6],
                    runtime=parts[7],
                    node=parts[8] if parts[8] else "-",
                )
            )

        return jobs

    def get_partitions(self) -> list[Partition]:
        """Get list of partitions from sinfo."""
        partitions = []

        # Format: Name|State|TotalNodes|AvailNodes|TotalCPUs|AvailCPUs
        cmd = ["sinfo", "-h", "-o", "%P|%a|%D|%A|%C"]
        stdout, stderr, rc = self._run_command(cmd)
        if rc != 0:
            return partitions

        for line in stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split("|")
            if len(parts) < 5:
                continue

            name = parts[0].rstrip("*")  # Remove default marker

            # Parse CPU info: "allocated/idle/other/total"
            cpu_parts = parts[4].split("/")
            total_cpus = int(cpu_parts[3]) if len(cpu_parts) >= 4 else 0
            avail_cpus = int(cpu_parts[1]) if len(cpu_parts) >= 2 else 0

            # Parse node info: "allocated/idle"
            node_parts = parts[3].split("/")
            total_nodes = int(node_parts[0]) + int(node_parts[1]) if len(node_parts) >= 2 else 0
            avail_nodes = int(node_parts[1]) if len(node_parts) >= 2 else 0

            partitions.append(
                Partition(
                    name=name,
                    state=parts[1],
                    total_nodes=total_nodes,
                    avail_nodes=avail_nodes,
                    total_cpus=total_cpus,
                    avail_cpus=avail_cpus,
                )
            )

        return partitions

    def cancel_job(self, job_id: str) -> tuple[bool, str]:
        """Cancel a job."""
        stdout, stderr, rc = self._run_command(["scancel", job_id])
        if rc == 0:
            return True, f"Job {job_id} cancelled"
        return False, stderr or "Failed to cancel job"

    def submit_job(self, script_path: str) -> tuple[bool, str]:
        """Submit a job script."""
        stdout, stderr, rc = self._run_command(["sbatch", script_path])
        if rc == 0:
            # Extract job ID from "Submitted batch job 12345"
            match = re.search(r"Submitted batch job (\d+)", stdout)
            if match:
                return True, f"Submitted job {match.group(1)}"
            return True, stdout.strip()
        return False, stderr or "Failed to submit job"

    def get_job_details(self, job_id: str) -> Optional[dict]:
        """Get detailed information about a job."""
        cmd = ["scontrol", "show", "job", job_id]
        stdout, stderr, rc = self._run_command(cmd)
        if rc != 0:
            return None

        details = {}
        for item in stdout.split():
            if "=" in item:
                key, _, value = item.partition("=")
                details[key] = value

        return details

    def get_job_log_paths(self, job_id: str) -> tuple[Optional[str], Optional[str]]:
        """Get stdout and stderr log file paths for a job.

        Returns (stdout_path, stderr_path) tuple.
        """
        details = self.get_job_details(job_id)
        if not details:
            return None, None

        stdout_path = details.get("StdOut")
        stderr_path = details.get("StdErr")

        return stdout_path, stderr_path

    def attach_to_job(self, job_id: str) -> list[str]:
        """Get command to attach to a running job."""
        return ["srun", f"--jobid={job_id}", "--overlap", "--pty", "/bin/bash", "-l"]

    def start_interactive_session(
        self,
        partition: str = "p2",
        gpus: int = 1,
        cpus: int = 4,
        memory: str = "4G",
        qos: str = "interactive",
    ) -> list[str]:
        """Get command to start an interactive session."""
        return [
            "srun",
            f"--qos={qos}",
            f"--partition={partition}",
            f"--gres=gpu:{gpus}",
            f"--cpus-per-task={cpus}",
            f"--mem-per-cpu={memory}",
            "--pty",
            "bash",
        ]

    def is_available(self) -> bool:
        """Check if SLURM commands are available."""
        _, _, rc = self._run_command(["squeue", "--version"])
        return rc == 0
