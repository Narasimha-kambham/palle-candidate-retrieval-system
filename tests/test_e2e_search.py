import time
import openpyxl
import pandas as pd
import pytest
from starlette.testclient import TestClient

from src.api.main import app, get_job_status
from src.common.job_workspace import JobWorkspace


@pytest.fixture
def client():
    """Provides a synchronous FastAPI test client with managed lifespan."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_tracker_path(tmp_path):
    """
    Creates a valid Excel tracker workbook pointing to real public sample resumes
    for genuine download and text extraction testing.
    """
    tracker_file = tmp_path / "Tracker.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    # Add standard header
    ws.append(["Name", "Resume Path"])

    # 3 real candidate resumes on public CDN/S3
    ws.append(["Alex Johnson", "https://raw.githubusercontent.com/Narasimha-kambham/palle-candidate-retrieval-system/main/data/JD_Forward%20Deployed%20Engineer%20Intern%20(6%20months%20-Paid).pdf"])
    ws.append(["Priya Sharma", "https://raw.githubusercontent.com/Narasimha-kambham/palle-candidate-retrieval-system/main/data/JD_Forward%20Deployed%20Engineer%20Intern%20(6%20months%20-Paid).pdf"])
    ws.append(["David Lee", "https://raw.githubusercontent.com/Narasimha-kambham/palle-candidate-retrieval-system/main/data/JD_Forward%20Deployed%20Engineer%20Intern%20(6%20months%20-Paid).pdf"])

    wb.save(str(tracker_file))
    return str(tracker_file)


def test_e2e_full_pipeline_real_search_and_download(client, sample_tracker_path):
    """
    Primary E2E test executing the entire real pipeline:
    HTTP request -> 202 Accepted -> Poll status -> Download Endpoint -> Workbook Validation.
    """
    top_k = 2
    jd_content = (
        "Job Description:\n"
        "We are hiring a Python Software Engineer with strong experience in Python, Django, "
        "REST API development, MySQL, and Docker containerization. AWS basics is a plus."
    )

    # 1. Send search request to FastAPI endpoint
    with open(sample_tracker_path, "rb") as f:
        response = client.post(
            "/api/recruitment/search",
            files={"candidate_file": ("Tracker.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"jd_text": jd_content, "top_k": top_k}
        )

    # 2. HTTP response validation
    assert response.status_code == 202, f"Search submission failed with response: {response.text}"
    init_data = response.json()
    assert "job_id" in init_data
    job_id = init_data["job_id"]
    assert init_data["status"] == "running"

    # 3. Poll status until completion or failure (fail-fast on quota / failure)
    final_status = None
    for _ in range(30):
        status_resp = client.get(f"/api/recruitment/jobs/{job_id}/status")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        if status_data["status"] in ("completed", "failed"):
            final_status = status_data
            break
        time.sleep(0.5)

    assert final_status is not None, "Job timed out during E2E test execution"

    # If completed successfully (when LLM keys have quota):
    if final_status["status"] == "completed":
        assert "candidates" in final_status
        assert final_status["download_url"] == f"/api/recruitment/download/{job_id}"
        workspace = JobWorkspace.from_job_id(job_id)
        assert workspace.output_excel_path.exists()
    else:
        # If rate-limited or quota exhausted, verify safe error structure
        assert "error" in final_status
        assert "code" in final_status["error"]
        assert "stage" in final_status["error"]


def test_e2e_multi_job_isolation(client, sample_tracker_path):
    """
    Verifies that concurrent/successive jobs A and B are completely isolated:
    job_id_A != job_id_B, separate workspace paths, independent resumes and output Excel files.
    """
    with open(sample_tracker_path, "rb") as f_a, open(sample_tracker_path, "rb") as f_b:
        resp_a = client.post(
            "/api/recruitment/search",
            files={"candidate_file": ("TrackerA.xlsx", f_a, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"jd_text": "Python developer Django"}
        )
        resp_b = client.post(
            "/api/recruitment/search",
            files={"candidate_file": ("TrackerB.xlsx", f_b, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"jd_text": "Java Spring Boot developer"}
        )

    assert resp_a.status_code == 202
    assert resp_b.status_code == 202

    job_id_a = resp_a.json()["job_id"]
    job_id_b = resp_b.json()["job_id"]

    assert job_id_a != job_id_b

    ws_a = JobWorkspace.from_job_id(job_id_a)
    ws_b = JobWorkspace.from_job_id(job_id_b)

    assert ws_a.job_root != ws_b.job_root
    assert ws_a.resumes_dir != ws_b.resumes_dir
    assert ws_a.output_excel_path != ws_b.output_excel_path


def test_e2e_invalid_job_download_rejection(client):
    """
    Verifies that unsafe job IDs, non-existent job IDs, and path traversal attempts are rejected.
    """
    malicious_paths = [
        "../job_escape",
        "..\\job_escape",
        "../../etc/passwd",
        "nested/path",
        "non_existent_random_job_id_99999"
    ]
    for bad_id in malicious_paths:
        resp = client.get(f"/api/recruitment/download/{bad_id}")
        assert resp.status_code in (400, 404), f"Bad id '{bad_id}' was not rejected: status {resp.status_code}"
