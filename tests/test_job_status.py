import os
import tempfile
import time
import pytest
from starlette.testclient import TestClient
from unittest.mock import patch, MagicMock
from src.api.main import (
    app,
    update_job_status,
    get_job_status,
    cleanup_expired_jobs_and_statuses,
    _job_statuses,
    _status_lock,
)
from src.common.job_workspace import JobWorkspace


@pytest.fixture(autouse=True)
def clean_statuses():
    with _status_lock:
        _job_statuses.clear()
    yield
    with _status_lock:
        _job_statuses.clear()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_job_status_initialization():
    update_job_status(
        job_id="test-job-1",
        status="running",
        stage=1,
        total_stages=10,
        stage_name="candidate_ingestion",
        label="Candidate ingestion",
        message="Reading candidate spreadsheet..."
    )
    status = get_job_status("test-job-1")
    assert status is not None
    assert status["job_id"] == "test-job-1"
    assert status["status"] == "running"
    assert status["stage"] == 1
    assert status["stage_name"] == "candidate_ingestion"
    assert status["completed_stages"] == 0


def test_job_status_update_progression():
    update_job_status(
        job_id="test-job-prog",
        status="running",
        stage=3,
        total_stages=10,
        stage_name="resume_download",
        label="Downloading candidate resumes",
        message="Downloading resumes..."
    )
    status = get_job_status("test-job-prog")
    assert status["stage"] == 3
    assert status["completed_stages"] == 2
    assert status["stage_name"] == "resume_download"


def test_job_status_running_to_completed():
    update_job_status(
        job_id="test-job-complete",
        status="completed",
        stage=10,
        stage_name="excel_export",
        label="Completed",
        message="Done",
        completed_stages=10,
        download_url="/api/recruitment/download/test-job-complete",
        candidates=[{"name": "Alice", "rank": 1, "final_score": 0.95}]
    )
    status = get_job_status("test-job-complete")
    assert status["status"] == "completed"
    assert status["completed_stages"] == 10
    assert status["download_url"] == "/api/recruitment/download/test-job-complete"
    assert len(status["candidates"]) == 1


def test_job_status_running_to_failed():
    update_job_status(
        job_id="test-job-fail",
        status="failed",
        stage=2,
        stage_name="jd_requirement_extraction",
        label="Failed at JD extraction",
        message="Quota exceeded",
        error={
            "code": "LLM_RATE_LIMIT_ERROR",
            "stage": "jd_requirement_extraction",
            "message": "AI quota exceeded."
        }
    )
    status = get_job_status("test-job-fail")
    assert status["status"] == "failed"
    assert status["error"]["code"] == "LLM_RATE_LIMIT_ERROR"
    assert status["error"]["stage"] == "jd_requirement_extraction"


def test_job_status_unknown_404(client):
    response = client.get("/api/recruitment/jobs/0123456789abcdef0123456789abcdef/status")
    assert response.status_code == 404
    assert "Job not found" in response.json()["detail"]


def test_job_status_invalid_path_traversal_rejected(client):
    response = client.get("/api/recruitment/jobs/../malicious/status")
    assert response.status_code in (400, 404)


def test_two_jobs_maintain_independent_status():
    update_job_status(
        job_id="job-alpha",
        status="running",
        stage=2,
        stage_name="jd_requirement_extraction"
    )
    update_job_status(
        job_id="job-beta",
        status="completed",
        stage=10,
        stage_name="excel_export"
    )
    status_a = get_job_status("job-alpha")
    status_b = get_job_status("job-beta")

    assert status_a["status"] == "running"
    assert status_a["stage"] == 2

    assert status_b["status"] == "completed"
    assert status_b["stage"] == 10


def test_failed_llm_job_preserves_safe_structured_error():
    update_job_status(
        job_id="job-llm-fail",
        status="failed",
        stage=2,
        stage_name="jd_requirement_extraction",
        error={
            "code": "LLM_AUTHENTICATION_ERROR",
            "stage": "jd_requirement_extraction",
            "message": "Invalid API key provided."
        }
    )
    status = get_job_status("job-llm-fail")
    assert status["error"]["code"] == "LLM_AUTHENTICATION_ERROR"
    assert status["error"]["stage"] == "jd_requirement_extraction"
    assert status["error"]["message"] == "Invalid API key provided."
    assert "technical_details" not in status["error"]
    assert "api_key" not in status["error"]


def test_expired_job_cleans_status_from_in_memory_dictionary():
    """
    Verifies that cleanup_expired_jobs_and_statuses() removes:
    1. The expired directory on disk.
    2. The corresponding in-memory status in _job_statuses.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create an expired job directory
        ws_expired = JobWorkspace(job_id="job_expired_123", base_runs_dir=temp_dir).create_dirs()
        (ws_expired.input_dir / "Tracker.xlsx").write_text("test")

        # Backdate folder modification time to 4000s ago
        old_time = time.time() - 4000
        os.utime(str(ws_expired.job_root), (old_time, old_time))

        # Register status in memory
        update_job_status(
            job_id="job_expired_123",
            status="completed",
            stage=10,
            stage_name="excel_export"
        )
        assert get_job_status("job_expired_123") is not None

        # Create an active/recent job
        ws_recent = JobWorkspace(job_id="job_recent_456", base_runs_dir=temp_dir).create_dirs()
        update_job_status(
            job_id="job_recent_456",
            status="running",
            stage=5,
            stage_name="vector_store_creation"
        )

        # Run synchronized cleanup with max_age_seconds=3600
        cleaned = cleanup_expired_jobs_and_statuses(base_runs_dir=temp_dir, max_age_seconds=3600)

        assert "job_expired_123" in cleaned
        assert not ws_expired.job_root.exists()
        # In-memory status must be removed
        assert get_job_status("job_expired_123") is None

        # Active job must remain untouched on disk and in memory
        assert ws_recent.job_root.exists()
        assert get_job_status("job_recent_456") is not None
