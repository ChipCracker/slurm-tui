# SLURM TUI

A modern terminal user interface for SLURM cluster management with real-time GPU monitoring.

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## Features

- **GPU Allocation Monitor** - Real-time GPU usage per partition with progress bars (10s auto-refresh)
- **GPU Hours Tracking** - User ranking by GPU hours consumed
- **Job Management** - View, submit, cancel, and attach to jobs
- **Interactive Sessions** - Quick launch of interactive SLURM sessions
- **Keyboard Navigation** - Full keyboard control for efficient workflow

## Screenshot

```
┌─────────────────────────────────────────────────────────────────────┐
│  SLURM TUI                                              12:34:56   │
├─────────────────────────────────────────────────────────────────────┤
│ GPU Allocation (auto-refresh 10s)      │ GPU Hours (2026)          │
│ ┌─────────────────────────────────────┐│ ┌────────────────────────┐│
│ │ p0    4/8   ████████░░░░░░░  50.0% ││ │ #  User     Hours     ││
│ │ p1   12/16  ████████████░░░  75.0% ││ │ 1  alice    1,234.5   ││
│ │ p2    8/32  ████░░░░░░░░░░░  25.0% ││ │ 2  bob        890.2   ││
│ │ p4    0/8   ░░░░░░░░░░░░░░░   0.0% ││ │ 3  charlie    654.1   ││
│ └─────────────────────────────────────┘│ └────────────────────────┘│
├─────────────────────────────────────────────────────────────────────┤
│ My Jobs (2)                                                         │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ JobID    Name           State Part  GPUs CPUs Runtime    Node   │ │
│ │ 12345    training-exp1  R     p2    4    12   02:34:12   node01 │ │
│ │ 12346    eval-model     PD    p4    2    8    --:--:--   -      │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│ [a]ttach  [c]ancel  [d]etails  [u] toggle all users                 │
└─────────────────────────────────────────────────────────────────────┘
```

## Installation

```bash
# Clone the repository
git clone https://github.com/ChipCracker/slurm-tui.git
cd slurm-tui

# Install with pip
pip install -e .

# Run
slurm-tui
```

## Requirements

- Python 3.10+
- SLURM cluster access (squeue, sinfo, sbatch, scancel, sreport)
- Dependencies: `textual`, `rich`

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` | Quit |
| `r` | Refresh all data |
| `n` | New job (submit script) |
| `i` | Start interactive session |
| `a` | Attach to selected job |
| `c` | Cancel selected job |
| `u` | Toggle all users / my jobs |
| `?` | Show help |

## Project Structure

```
slurm-tui/
├── pyproject.toml
├── scripts/                    # Legacy bash scripts
│   ├── attach_slurm_job.sh
│   ├── batch_slurm_job.sh
│   ├── cancel_slurm_job.sh
│   ├── check_slurm_gpu_hours.sh
│   ├── create_slurm_job.sh
│   ├── interactive_slurm_job.sh
│   └── show_alloc_gpus.sh
└── src/slurm_tui/
    ├── app.py                  # Main application
    ├── screens/
    │   ├── main.py             # Dashboard screen
    │   └── job_submit.py       # Job submission dialogs
    ├── utils/
    │   ├── slurm.py            # SLURM command wrappers
    │   └── gpu.py              # GPU monitoring utilities
    └── widgets/
        ├── gpu_monitor.py      # GPU allocation widget
        ├── gpu_hours.py        # GPU hours widget
        └── job_table.py        # Job table widget
```

## Configuration

The TUI auto-discovers partitions from your SLURM cluster. Default partitions can be configured in `utils/gpu.py`:

```python
DEFAULT_PARTITION_GPUS = {
    "p0": 8,
    "p1": 16,
    "p2": 32,
    "p4": 8,
}
```

## License

MIT
