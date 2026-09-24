import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional, List


# Default retention period for completed job directories: 1 hour (3600 seconds)
DEFAULT_RETENTION_SECONDS = 3600


class JobWorkspace:
    """
    Manages request-scoped temporary directories and file paths for a recruitment search job.

    Directory structure:
    data/runs/<job_id>/
        ├── input/
        │   ├── Tracker.xlsx
        │   └── JD.txt / JD.pdf
        ├── resumes/
        │   ├── candidate_1.pdf
        │   └── candidate_2.pdf
        └── output/
            └── ranked_candidates.xlsx
    """

    def __init__(
        self,
        job_id: str,
        base_runs_dir: str | Path = "data/runs",
        retention_seconds: int = DEFAULT_RETENTION_SECONDS
    ):
        self.job_id = str(job_id).strip()
        self.base_runs_dir = Path(base_runs_dir)
        self.retention_seconds = retention_seconds

        self.job_root = self.base_runs_dir / self.job_id
        self.input_dir = self.job_root / "input"
        self.resumes_dir = self.job_root / "resumes"
        self.output_dir = self.job_root / "output"
        self.output_excel_path = self.output_dir / "ranked_candidates.xlsx"

    def create_dirs(self) -> "JobWorkspace":
        """Creates the job workspace root and all subdirectories safely."""
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.resumes_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self

    def get_candidate_file_path(self, filename: str = "Tracker.xlsx") -> Path:
        """Returns the isolated input path for the uploaded tracker spreadsheet."""
        safe_filename = Path(filename).name
        return self.input_dir / safe_filename

    def get_jd_file_path(self, filename: str = "JD.txt") -> Path:
        """Returns the isolated input path for the uploaded JD document."""
        safe_filename = Path(filename).name
        return self.input_dir / safe_filename

    def cleanup(self) -> None:
        """Deletes this entire job directory and all its contents safely."""
        if self.job_root.exists():
            shutil.rmtree(self.job_root, ignore_errors=True)

    @classmethod
    def create(
        cls,
        job_id: Optional[str] = None,
        base_runs_dir: str | Path = "data/runs",
        retention_seconds: int = DEFAULT_RETENTION_SECONDS
    ) -> "JobWorkspace":
        """Generates a collision-safe job_id (if not provided) and initializes directories."""
        if not job_id:
            job_id = uuid.uuid4().hex
        workspace = cls(job_id=job_id, base_runs_dir=base_runs_dir, retention_seconds=retention_seconds)
        workspace.create_dirs()
        return workspace

    @classmethod
    def from_job_id(
        cls,
        job_id: str,
        base_runs_dir: str | Path = "data/runs"
    ) -> "JobWorkspace":
        """
        Validates job_id for security (rejects path traversal characters) and returns workspace instance.
        """
        if not job_id or not isinstance(job_id, str):
            raise ValueError("Invalid job_id: must be a non-empty string.")

        # Strict validation: job_id must only contain alphanumeric characters and hyphens/underscores
        if not re.match(r"^[a-zA-Z0-9_\-]+$", job_id):
            raise ValueError("Invalid job_id format: potentially unsafe characters detected.")

        return cls(job_id=job_id, base_runs_dir=base_runs_dir)

    @staticmethod
    def cleanup_expired_jobs(
        base_runs_dir: str | Path = "data/runs",
        max_age_seconds: int = DEFAULT_RETENTION_SECONDS
    ) -> List[str]:
        """
        Finds and deletes job directories under base_runs_dir older than max_age_seconds.
        Never touches directories outside base_runs_dir.
        Returns a list of cleaned job IDs.
        """
        runs_path = Path(base_runs_dir)
        if not runs_path.exists() or not runs_path.is_dir():
            return []

        cleaned_jobs = []
        now = time.time()

        for item in runs_path.iterdir():
            if not item.is_dir():
                continue

            try:
                # Use directory modification time for cross-platform expiration check
                stat = item.stat()
                dir_age = now - stat.st_mtime

                if dir_age >= max_age_seconds:
                    shutil.rmtree(item, ignore_errors=True)
                    cleaned_jobs.append(item.name)
            except Exception as e:
                # Log or ignore errors gracefully without halting recruitment processing
                pass

        return cleaned_jobs
