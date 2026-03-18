# SLURM TUI

A modern terminal user interface for SLURM cluster management with real-time GPU monitoring. Built with [Textual](https://github.com/Textualize/textual) and a Tokyo Night dark theme.

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## Features

- **GPU Allocation Monitor** - Real-time GPU usage per partition with color-coded progress bars (10s auto-refresh)
- **GPU Hours Tracking** - Top 10 user ranking by GPU hours consumed, current user highlighted
- **Running Jobs Summary** - Compact one-line overview of your running jobs (jobs, GPUs, CPUs), expandable with `o`
- **Job Management** - View, submit, cancel, and attach to jobs with 10s auto-refresh
- **Column Sorting** - Sort job table by any column (ID, Name, State, Partition, GPU, Time) with visual indicator
- **Job Details Panel** - Split-view with editable job script and live stderr/stdout logs
- **Log Viewer** - Incremental log loading, follow mode, tqdm-compatible terminal simulation, one-click copy
- **Script Editor** - Syntax-highlighted editor with sidebar file browser and bookmark integration
- **Bookmarks** - Save frequently used jobs and scripts for quick access
- **Interactive Sessions** - Launch interactive SLURM sessions with live command preview
- **Job Attach** - Connect to running jobs via terminal suspension (`srun --overlap`)
- **Embedded Console** - Shell session within the TUI via `app.suspend()`, toggle with `t`
- **Non-blocking I/O** - Background workers keep the UI responsive during SLURM commands

## Screenshot

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│ SLURM TUI                                                           10s refresh    │
├─────────────────────────────────────────┬──────────────────────────────────────────┤
│ GPU Allocation                          │ Job Details                              │
│                                         │                                          │
│  p0    4/8   ████████░░░░░░░░    50.0%  │  Script: train.sh            [modified]  │
│  p1   12/16  ████████████░░░░    75.0%  │  #!/bin/bash                             │
│  p2    8/32  ████░░░░░░░░░░░░    25.0%  │  #SBATCH --partition=p2                  │
│  p4    0/8   ░░░░░░░░░░░░░░░░     0.0%  │  #SBATCH --gres=gpu:4                    │
│                                         │  python train.py --epochs 100            │
│ GPU Hours 2026                 Top 10   │──────────────────────────────────────────│
│  1. alice        1,234h  ████████████   │  Logs (stderr)                 [follow]  │
│  2. bob            890h  █████████      │  Epoch 12/100  loss=0.234                │
│  3. charlie        654h  ███████        │  Epoch 13/100  loss=0.221                │
│                                         │  Epoch 14/100  loss=0.198                │
│ ── Running 3 jobs  ·  6 GPUs  ·  24 CPUs                                          │
│                                         │                                          │
│ Jobs                       my jobs (2)  │                                          │
│   ID▲      Name                 State   Part       GPU      Time                   │
│  ──────────────────────────────────────────────────────────────────                │
│   12345    training-exp         ● R     p2           4    12:34:56                 │
│   12346    eval-model           ◐ PD    p1           2          —                  │
├────────────────────────────────────────────────────────────────────────────────────┤
│ [a]ttach [c]ancel [l]ogs [n]ew [i]nteractive [u]sers [s]ort [d]ir [o]verview      │
│ [b]ookmarks [e]ditor [t]erminal [q]uit                                             │
└────────────────────────────────────────────────────────────────────────────────────┘
```

## Installation

```bash
# Clone the repository
git clone https://github.com/ChipCracker/slurm-tui.git
cd slurm-tui

# Install with pip (editable mode for development)
pip install -e .

# Run
slurm-tui

# Or run directly without installing
python -m slurm_tui
```

## Requirements

- Python 3.10+
- SLURM cluster access (`squeue`, `sinfo`, `scontrol`, `sbatch`, `scancel`, `srun`, `sreport`)
- Dependencies (installed automatically): `textual>=0.47.0`, `rich>=13.0.0`

## Keyboard Shortcuts

### Dashboard

| Key   | Action                                 |
|-------|----------------------------------------|
| `q`   | Quit                                   |
| `r`   | Refresh all data                       |
| `n`   | New job (submit script)                |
| `i`   | Start interactive session              |
| `a`   | Attach to running job                  |
| `c`   | Cancel selected job                    |
| `u`   | Toggle all users / my jobs             |
| `s`   | Cycle sort column                      |
| `d`   | Toggle sort direction (asc/desc)       |
| `o`   | Toggle running jobs (compact/expanded) |
| `l`   | View logs for selected job             |
| `b`   | Show bookmarks                         |
| `B`   | Bookmark selected job                  |
| `e`   | Open script editor                     |
| `t`   | Open terminal (shell)                  |
| `?`   | Show help                              |

### Log Viewer

| Key      | Action                       |
|----------|------------------------------|
| `f`      | Toggle follow mode           |
| `r`      | Refresh logs                 |
| `y`      | Copy active log to clipboard |
| `Escape` | Close                        |

### Script Editor

| Key                  | Action          |
|----------------------|-----------------|
| `Ctrl+S`             | Save file       |
| `Ctrl+O`             | Open file       |
| `Ctrl+R`             | Refresh sidebar |
| `Ctrl+Q` / `Escape`  | Close editor    |

### Bookmarks

| Key      | Action                     |
|----------|----------------------------|
| `d`      | Delete selected bookmark   |
| `e`      | Edit script (scripts tab)  |
| `Escape` | Close                      |

## Project Structure

```
slurm-tui/
├── pyproject.toml
├── scripts/                        # Legacy bash scripts (reference)
│   ├── attach_slurm_job.sh
│   ├── batch_slurm_job.sh
│   ├── cancel_slurm_job.sh
│   ├── check_slurm_gpu_hours.sh
│   ├── create_slurm_job.sh
│   ├── interactive_slurm_job.sh
│   └── show_alloc_gpus.sh
└── src/slurm_tui/
    ├── app.py                      # Main application (Tokyo Night theme)
    ├── __main__.py                 # CLI entry point
    ├── screens/
    │   ├── main.py                 # Dashboard screen (split-view layout)
    │   ├── job_submit.py           # Job submission & interactive sessions
    │   ├── log_viewer.py           # Log viewer with follow mode
    │   ├── bookmarks.py            # Bookmark management
    │   └── editor.py               # Script editor with file browser
    ├── widgets/
    │   ├── gpu_monitor.py          # GPU allocation progress bars
    │   ├── gpu_hours.py            # GPU hours ranking + running jobs
    │   ├── job_table.py            # Sortable job listing table
    │   └── job_details.py          # Split-pane script + logs viewer
    └── utils/
        ├── slurm.py                # SLURM command wrappers
        ├── gpu.py                  # GPU monitoring (sinfo + sreport)
        ├── log_reader.py           # Incremental log file reader
        └── bookmarks.py            # Bookmark persistence (~/.config/slurm-tui/)
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
