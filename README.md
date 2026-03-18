# SLURM TUI

A modern terminal user interface for SLURM cluster management with real-time GPU monitoring.

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## Features

- **GPU Allocation Monitor** - Real-time GPU usage per partition with color-coded progress bars (10s auto-refresh)
- **GPU Hours Tracking** - User ranking by GPU hours consumed with relative bar charts
- **Job Management** - View, submit, cancel, and attach to jobs with partition and GPU info
- **Log Viewer** - Incremental log loading with scroll-aware auto-follow and clipboard copy
- **Bookmarks** - Bookmark jobs and scripts for quick access (stored in `~/.config/slurm-tui/`)
- **Script Editor** - Edit SLURM scripts with file browser and bookmark integration
- **Embedded Console** - Persistent shell session within the TUI (toggle with backtick)
- **Interactive Sessions** - Quick launch of interactive SLURM sessions with configurable resources
- **Job Attach** - Attach to running jobs with full terminal access via `app.suspend()`
- **Tokyo Night Theme** - Modern dark color scheme with borderless, minimal design

## Screenshot

```
┌───────────────────────────────────────────────────────────────────────┐
│  SLURM TUI                                               10s refresh │
├────────────────────────────────┬──────────────────────────────────────┤
│ GPU Allocation                 │ Job Details                          │
│ p0    4/8   ████████░░░  50%  │ ┌─ Script ──────────────────────────┐│
│ p1   12/16  ██████████░  75%  ││ #!/bin/bash                       ││
│ p2    8/32  ████░░░░░░░  25%  ││ #SBATCH --partition=p2            ││
│                                ││ #SBATCH --gres=gpu:4              ││
│ GPU Hours (2026)               │└────────────────────────────────────┘│
│ 1  alice    ██████  1,234h    │ ┌─ Logs ─────────────────────────────┐│
│ 2  bob      ████    890h      ││ Epoch 1/10 loss=0.234              ││
│ 3  charlie  ███     654h      ││ Epoch 2/10 loss=0.198              ││
│                                │└────────────────────────────────────┘│
│ Jobs (my jobs: 2)              │                                      │
│     ID  Name            ● R p2│                                      │
│  12345  training-exp1   ◐ PD  │                                      │
│  12346  eval-model            │                                      │
├────────────────────────────────┴──────────────────────────────────────┤
│ > Console                                              Esc=back `=tog│
│ $ squeue -u $USER                                                     │
│ $ nvidia-smi --query-gpu=...                                          │
├───────────────────────────────────────────────────────────────────────┤
│ attach  cancel  logs  new  interactive  users  bookmarks  editor  `   │
└───────────────────────────────────────────────────────────────────────┘
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

### Main Screen

| Key | Action |
|-----|--------|
| `q` | Quit |
| `r` | Refresh all data |
| `n` | New job (submit script) |
| `i` | Start interactive session |
| `a` | Attach to running job |
| `c` | Cancel selected job |
| `u` | Toggle all users / my jobs |
| `l` | View job logs |
| `b` | Bookmarks |
| `B` | Add current job to bookmarks |
| `e` | Script editor |
| `` ` `` | Toggle embedded console |
| `?` | Show help |

### Job Details Panel

| Key | Action |
|-----|--------|
| `y` | Copy logs to clipboard |
| `Ctrl+S` | Save script |

### Console

| Key | Action |
|-----|--------|
| `Escape` | Return focus to job table |
| `` ` `` | Toggle console visibility |

## Project Structure

```
slurm-tui/
├── pyproject.toml
├── scripts/                       # Legacy bash scripts
│   ├── attach_slurm_job.sh
│   ├── batch_slurm_job.sh
│   ├── cancel_slurm_job.sh
│   ├── check_slurm_gpu_hours.sh
│   ├── create_slurm_job.sh
│   ├── interactive_slurm_job.sh
│   └── show_alloc_gpus.sh
└── src/slurm_tui/
    ├── app.py                     # Main application
    ├── screens/
    │   ├── main.py                # Dashboard screen
    │   ├── job_submit.py          # Job submission & cancel dialogs
    │   ├── log_viewer.py          # Log viewer modal
    │   ├── bookmarks.py           # Bookmarks modal
    │   └── editor.py              # Script editor
    ├── utils/
    │   ├── slurm.py               # SLURM command wrappers
    │   ├── gpu.py                 # GPU monitoring utilities
    │   ├── bookmarks.py           # Bookmark persistence
    │   └── log_reader.py          # Log file reading with CR simulation
    └── widgets/
        ├── gpu_monitor.py         # GPU allocation widget
        ├── gpu_hours.py           # GPU hours ranking widget
        ├── job_table.py           # Job table widget
        ├── job_details.py         # Job details (script + logs)
        └── console.py             # Embedded shell console
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

Bookmarks are stored in `~/.config/slurm-tui/bookmarks.json`.

## License

MIT
