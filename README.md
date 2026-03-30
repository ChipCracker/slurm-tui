# SLURM TUI

A modern terminal user interface for SLURM cluster management with real-time GPU monitoring. Built with [Textual](https://github.com/Textualize/textual) and a Tokyo Night dark theme.

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## Features

- **GPU Allocation Monitor** - Real-time GPU usage per partition with color-coded progress bars (10s auto-refresh)
- **GPU Partition Details** - Cycle through partitions with `g` to see GPU type, VRAM, node state, memory, and CPUs
- **Live GPU Stats** - Per-GPU utilization, VRAM, power draw, and temperature for running jobs with 5s auto-refresh (`v`)
- **GPU Hours Tracking** - Top 10 user ranking by GPU hours consumed, current user highlighted
- **Running Jobs Summary** - Compact overview of running jobs (count, GPUs, CPUs), expandable with `o`
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
│ GPU Allocation                     10s  │ Partition p1                             │
│ ─────────────────────────────────────── │ ──────────────────────────────────────── │
│ p0    5/ 8  █████████████░░░░    62.5%  │   GPUs: 8 / 8 allocated  (100.0%)       │
│ p1    8/ 8  █████████████████   100.0%  │   GPU: A100-SXM4   VRAM: 40 GB HBM     │
│ p2    7/ 8  ██████████████░░░    87.5%  │   Nodes: 1   CPUs: 256   RAM: 2003 GB  │
│ p4    8/ 8  █████████████████   100.0%  │ ──────────────────────────────────────── │
│ p6    4/ 4  █████████████████   100.0%  │   Node             GPUs  State          │
│                                         │   ml1                 8  mixed          │
│ GPU Hours 2026                 Top 10   │                                          │
│  1. alice        1,234h  ████████████   ├──────────────────────────────────────────┤
│  2. bob            890h  █████████      │ Job 12345 - training-exp                 │
│  3. you            654h  ███████     ←  │ Script [Ctrl+S to save]                  │
│                                         │ /path/to/train.sh                        │
│ ── Running 3 jobs  ·  6 GPUs  ·  24 CPUs│ #!/bin/bash                              │
│                                         │ #SBATCH --partition=p2                   │
│ Jobs                       my jobs (5)  │ #SBATCH --gres=gpu:4                     │
│   ID       Name           State  Part   │──────────────────────────────────────────│
│  ─────────────────────────────────────  │ Logs (stderr)                            │
│  12345  training-exp       ● R   p2     │ Epoch 12/100  loss=0.234                 │
│  12346  eval-model         ◐ PD  p1     │ Epoch 13/100  loss=0.221                 │
├────────────────────────────────────────────────────────────────────────────────────┤
│ [y]← [x/s]ort [c]→ [a]ttach [d]ir [C]ancel [r]efresh [n]ew [i]nteractive [u]sers   │
│ [o]verview [g]pu [v]GPU [w]stderr/out [l]ogs [b]ookmarks [e]ditor [t]erminal [q]uit│
└────────────────────────────────────────────────────────────────────────────────────┘
```

## Cluster Hardware

| Partition | Host | RAM   | CPUs                          | GPUs                              |
|-----------|------|-------|-------------------------------|-----------------------------------|
| p0        | ml0  | 380G  | 96x Intel Xeon Gold 6252      | 8x RTX 2080 Ti (11 GB GDDR6)     |
| p1        | ml1  | 2 TB  | 256x AMD EPYC 7662            | 8x A100-SXM4 (40 GB HBM)         |
| p2        | ml2  | 2 TB  | 128x AMD EPYC 7713            | 8x A100-SXM4 (80 GB HBM)         |
| p4        | ml4  | 2 TB  | 384x AMD EPYC 9654            | 8x H200-SXM5 (143 GB HBM)        |
| p6        | ml6  | 2 TB  | 128x Intel Xeon Gold 6448Y    | 4x L40S (46 GB GDDR6)            |

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

| Key   | Action                               |
|-------|--------------------------------------|
| `q`   | Quit                                 |
| `r`   | Refresh all data                     |
| `n`   | New job (submit script)              |
| `i`   | Start interactive session            |
| `y` / `←` | Focus left panel                 |
| `x` / `s` | Cycle sort column               |
| `c` / `→` | Focus right panel                |
| `a`   | Attach to running job                |
| `d`   | Toggle sort direction (asc/desc)     |
| `C`   | Cancel selected job                  |
| `u`   | Toggle all users / my jobs           |
| `o`   | Overview: toggle running jobs        |
| `g`   | GPU partition details (cycle)        |
| `v`   | Live GPU stats for running job       |
| `l`   | View logs for selected job           |
| `b`   | Show bookmarks                       |
| `B`   | Bookmark selected job                |
| `e`   | Open script editor                   |
| `t`   | Terminal (open shell)                |
| `?`   | Show help                            |

`←` and `→` switch panels while the script/log view is read-only. During script editing, the arrow keys keep their normal cursor behavior.

### Job Details Panel

| Key      | Action              |
|----------|---------------------|
| `Ctrl+S` | Save script         |
| `b`      | Bookmark script     |
| `Y`      | Copy logs           |

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
    │   └── job_details.py          # Split-pane script + logs + partition details
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
    "p1": 8,
    "p2": 8,
    "p4": 8,
    "p6": 4,
}
```

Bookmarks are stored in `~/.config/slurm-tui/bookmarks.json`.

## License

MIT
