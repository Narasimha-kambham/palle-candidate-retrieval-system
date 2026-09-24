import os
import time
import tempfile
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
import pandas as pd

from src.common.job_workspace import JobWorkspace
from src.ingestion.resume_downloader import download_all_resumes
from src.api.main import app
from src.export.excel_exporter import export_ranked_candidates


def test_downloader_requires_workspace_path():
    """Test 1: Calling download_all_resumes without resumes_dir must raise TypeError or ValueError."""
    candidates = [{"source_row": 2, "name": "Alice", "resume_path": "https://example.com/a.pdf"}]
    
    with pytest.raises((TypeError, ValueError)):
        # Calling without required argument
        download_all_resumes(candidates)  # type: ignore

    with pytest.raises(ValueError, match="resumes_dir is required"):
        download_all_resumes(candidates, resumes_dir=None)

    with tempfile.TemporaryDirectory() as temp_dir:
        resumes_dir = Path(temp_dir) / "resumes"
        records = download_all_resumes([], resumes_dir=resumes_dir)
        assert isinstance(records, list)
        assert resumes_dir.exists()


def test_no_global_resume_path_in_production_code():
    """Test 2: Search production source files and assert that data/resumes and data/output do not exist."""
    src_dir = Path("src")
    forbidden_patterns = ["data/resumes", "data\\resumes", "data/output", "data\\output"]

    violations = []
    for py_file in src_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for pattern in forbidden_patterns:
            if pattern in content:
                violations.append(f"{py_file}: contains '{pattern}'")

    assert not violations, f"Found legacy global path references in production code:\n" + "\n".join(violations)


def test_job_workspace_paths_and_creation():
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = JobWorkspace(job_id="test_job_123", base_runs_dir=temp_dir)
        workspace.create_dirs()

        assert workspace.job_id == "test_job_123"
        assert workspace.job_root == Path(temp_dir) / "test_job_123"
        assert workspace.input_dir == Path(temp_dir) / "test_job_123" / "input"
        assert workspace.resumes_dir == Path(temp_dir) / "test_job_123" / "resumes"
        assert workspace.output_dir == Path(temp_dir) / "test_job_123" / "output"
        assert workspace.output_excel_path == Path(temp_dir) / "test_job_123" / "output" / "ranked_candidates.xlsx"

        # Check directories physically created
        assert workspace.input_dir.exists()
        assert workspace.resumes_dir.exists()
        assert workspace.output_dir.exists()


def test_job_workspace_isolation():
    """Test 3, 4, 5: Verify job_A and job_B isolation for input, resumes, and output."""
    with tempfile.TemporaryDirectory() as temp_dir:
        ws_a = JobWorkspace(job_id="job_alpha", base_runs_dir=temp_dir).create_dirs()
        ws_b = JobWorkspace(job_id="job_beta", base_runs_dir=temp_dir).create_dirs()

        # Resumes isolation
        file_a = ws_a.resumes_dir / "candidate_a.pdf"
        file_a.write_text("Resume A content")

        file_b = ws_b.resumes_dir / "candidate_b.pdf"
        file_b.write_text("Resume B content")

        assert file_a.exists()
        assert file_b.exists()
        assert not (ws_b.resumes_dir / "candidate_a.pdf").exists()
        assert not (ws_a.resumes_dir / "candidate_b.pdf").exists()

        # Output isolation
        out_a = ws_a.output_excel_path
        out_a.write_text("Excel A")
        out_b = ws_b.output_excel_path
        out_b.write_text("Excel B")

        assert out_a.read_text() == "Excel A"
        assert out_b.read_text() == "Excel B"
        assert ws_a.resumes_dir != ws_b.resumes_dir


def test_job_workspace_path_traversal_protection():
    """Test 6: Reject path traversal and unsafe job IDs."""
    malicious_ids = [
        "../job_escape",
        "..\\job_escape",
        "../../etc/passwd",
        "subdir/nested",
        "job;rm -rf",
        "job\\escape",
        "",
        "   "
    ]
    for bad_id in malicious_ids:
        with pytest.raises(ValueError):
            JobWorkspace.from_job_id(bad_id)


def test_job_workspace_cleanup_retention():
    """Test 7: Cleanup of expired jobs deletes the complete directory (input, resumes, output)."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create an "expired" job directory
        ws_expired = JobWorkspace(job_id="job_expired", base_runs_dir=temp_dir).create_dirs()
        (ws_expired.input_dir / "Tracker.xlsx").write_text("tracker")
        (ws_expired.resumes_dir / "res.pdf").write_text("resume")
        (ws_expired.output_dir / "ranked.xlsx").write_text("output")

        # Manually backdate the modification time of job_expired
        old_time = time.time() - 4000  # older than 3600s
        os.utime(str(ws_expired.job_root), (old_time, old_time))

        # Create a "recent" job directory
        ws_recent = JobWorkspace(job_id="job_recent", base_runs_dir=temp_dir).create_dirs()
        (ws_recent.output_dir / "ranked.xlsx").write_text("recent output")

        # Run cleanup with max_age_seconds = 3600
        cleaned = JobWorkspace.cleanup_expired_jobs(base_runs_dir=temp_dir, max_age_seconds=3600)

        assert "job_expired" in cleaned
        assert not ws_expired.job_root.exists()

        # Recent job must remain intact
        assert ws_recent.job_root.exists()
        assert ws_recent.output_excel_path.parent.exists()


def test_api_download_endpoints():
    client = TestClient(app)

    # 1. Test 400 on invalid job ID (path traversal)
    resp_invalid = client.get("/api/recruitment/download/../malicious")
    assert resp_invalid.status_code in (400, 404)

    # 2. Test 404 on non-existent job ID
    resp_not_found = client.get("/api/recruitment/download/non_existent_job_9999")
    assert resp_not_found.status_code == 404

    # 3. Test 400 on legacy endpoint without query param
    resp_legacy_no_param = client.get("/api/recruitment/download")
    assert resp_legacy_no_param.status_code == 400

    # 4. Create an actual synthetic job output and download via endpoint
    workspace = JobWorkspace.create()
    job_id = workspace.job_id
    try:
        # Create dummy ranked_candidates.xlsx
        df_dummy = pd.DataFrame([{"Rank": 1, "Name": "Alice", "Final Score": 0.95}])
        df_dummy.to_excel(str(workspace.output_excel_path), index=False)

        # Test download by path param
        resp_download = client.get(f"/api/recruitment/download/{job_id}")
        assert resp_download.status_code == 200
        assert resp_download.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        # Test download by legacy query param
        resp_query = client.get(f"/api/recruitment/download?job_id={job_id}")
        assert resp_query.status_code == 200

    finally:
        workspace.cleanup()

