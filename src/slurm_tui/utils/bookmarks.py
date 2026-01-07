"""Bookmark management for SLURM TUI."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class JobBookmark:
    """A bookmarked job."""

    job_id: str
    name: str
    added: str


@dataclass
class ScriptBookmark:
    """A bookmarked script."""

    path: str
    name: str
    added: str


class BookmarkManager:
    """Manages bookmarks for jobs and scripts."""

    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = Path.home() / ".config" / "slurm-tui"
        self.config_dir = config_dir
        self.config_file = self.config_dir / "bookmarks.json"
        self._ensure_config_dir()
        self._load()

    def _ensure_config_dir(self) -> None:
        """Create config directory if it doesn't exist."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        """Load bookmarks from file."""
        self.jobs: list[JobBookmark] = []
        self.scripts: list[ScriptBookmark] = []

        if not self.config_file.exists():
            return

        try:
            with open(self.config_file) as f:
                data = json.load(f)

            for job_data in data.get("jobs", []):
                self.jobs.append(JobBookmark(**job_data))

            for script_data in data.get("scripts", []):
                self.scripts.append(ScriptBookmark(**script_data))
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    def _save(self) -> None:
        """Save bookmarks to file."""
        data = {
            "jobs": [asdict(j) for j in self.jobs],
            "scripts": [asdict(s) for s in self.scripts],
        }

        with open(self.config_file, "w") as f:
            json.dump(data, f, indent=2)

    def add_job(self, job_id: str, name: str) -> bool:
        """Add a job bookmark. Returns True if added, False if already exists."""
        # Check if already exists
        for job in self.jobs:
            if job.job_id == job_id:
                return False

        bookmark = JobBookmark(
            job_id=job_id,
            name=name,
            added=datetime.now().strftime("%Y-%m-%d"),
        )
        self.jobs.append(bookmark)
        self._save()
        return True

    def remove_job(self, job_id: str) -> bool:
        """Remove a job bookmark. Returns True if removed."""
        for i, job in enumerate(self.jobs):
            if job.job_id == job_id:
                del self.jobs[i]
                self._save()
                return True
        return False

    def add_script(self, path: str, name: Optional[str] = None) -> bool:
        """Add a script bookmark. Returns True if added, False if already exists."""
        path = os.path.abspath(path)

        # Check if already exists
        for script in self.scripts:
            if script.path == path:
                return False

        if name is None:
            name = os.path.basename(path)

        bookmark = ScriptBookmark(
            path=path,
            name=name,
            added=datetime.now().strftime("%Y-%m-%d"),
        )
        self.scripts.append(bookmark)
        self._save()
        return True

    def remove_script(self, path: str) -> bool:
        """Remove a script bookmark. Returns True if removed."""
        path = os.path.abspath(path)
        for i, script in enumerate(self.scripts):
            if script.path == path:
                del self.scripts[i]
                self._save()
                return True
        return False

    def is_job_bookmarked(self, job_id: str) -> bool:
        """Check if a job is bookmarked."""
        return any(j.job_id == job_id for j in self.jobs)

    def is_script_bookmarked(self, path: str) -> bool:
        """Check if a script is bookmarked."""
        path = os.path.abspath(path)
        return any(s.path == path for s in self.scripts)

    def get_jobs(self) -> list[JobBookmark]:
        """Get all job bookmarks."""
        return self.jobs.copy()

    def get_scripts(self) -> list[ScriptBookmark]:
        """Get all script bookmarks."""
        return self.scripts.copy()
