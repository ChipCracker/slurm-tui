"""SLURM TUI Widgets."""

from .gpu_monitor import GPUMonitorWidget
from .gpu_hours import GPUHoursWidget
from .job_table import JobTableWidget

__all__ = ["GPUMonitorWidget", "GPUHoursWidget", "JobTableWidget"]
