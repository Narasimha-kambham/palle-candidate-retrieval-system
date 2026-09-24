import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.api.main import app, get_job_status
from src.common.errors import (
    PipelineException,
    classify_llm_exception,
)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def valid_tracker(tmp_path):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["Name", "Resume Path"])
    ws.append(["Alice Smith", "https://example.com/alice.pdf"])
    path = tmp_path / "Tracker.xlsx"
    wb.save(str(path))
    return str(path)


# ----------------------------------------------------------------------
# 1. Pure Classification Unit Tests
# ----------------------------------------------------------------------

def test_error_classification_llm_authentication():
    """Verify 401 / Invalid API Key maps to LLM_AUTHENTICATION_ERROR."""
    auth_errors = [
        Exception("401 Unauthorized / Invalid API Key: secret_key_12345"),
        Exception("API key not valid. Please pass a valid API key."),
        Exception("Authentication failed for user credentials."),
    ]
    for exc in auth_errors:
        classified = classify_llm_exception(exc, stage="jd_requirement_extraction")
        assert isinstance(classified, PipelineException)
        assert classified.code == "LLM_AUTHENTICATION_ERROR"
        assert classified.status_code == 502
        assert classified.stage == "jd_requirement_extraction"
        assert "secret_key_12345" not in classified.message
        assert classified.message == "AI service authentication failed. Please contact the administrator."


def test_error_classification_llm_rate_limit():
    """Verify 429 / Quota / Rate limit maps to LLM_RATE_LIMIT_ERROR."""
    rate_errors = [
        Exception("429 Too Many Requests: Rate limit exceeded"),
        Exception("RESOURCE_EXHAUSTED: Daily quota reached"),
        Exception("Quota exceeded for quota metric 'Generate Content API'"),
    ]
    for exc in rate_errors:
        classified = classify_llm_exception(exc, stage="jd_requirement_extraction")
        assert isinstance(classified, PipelineException)
        assert classified.code == "LLM_RATE_LIMIT_ERROR"
        assert classified.status_code == 429
        assert classified.stage == "jd_requirement_extraction"
        assert classified.message == "AI service rate limit or quota has been exceeded. Please contact the administrator."


def test_error_classification_llm_provider_failure():
    """Verify 500 / 503 / Provider exhaustion maps to LLM_PROVIDER_ERROR."""
    provider_errors = [
        Exception("503 Service Unavailable: High load"),
        Exception("504 Gateway Timeout"),
        Exception("ProvidersExhausted: OpenAI and Gemini failed twice. Both providers are exhausted."),
    ]
    for exc in provider_errors:
        classified = classify_llm_exception(exc, stage="jd_requirement_extraction")
        assert isinstance(classified, PipelineException)
        assert classified.code == "LLM_PROVIDER_ERROR"
        assert classified.status_code == 503
        assert classified.stage == "jd_requirement_extraction"
        assert classified.message == "AI service is currently unavailable. Please try again later."


def test_error_classification_llm_generic_request():
    """Verify generic LLM errors map to LLM_REQUEST_ERROR."""
    exc = Exception("Bad Gateway / unknown internal error")
    classified = classify_llm_exception(exc, stage="jd_requirement_extraction")
    assert isinstance(classified, PipelineException)
    assert classified.code == "LLM_REQUEST_ERROR"
    assert classified.status_code == 502
    assert classified.stage == "jd_requirement_extraction"
    assert classified.message == "AI service request failed. Please contact the administrator if the problem continues."


# ----------------------------------------------------------------------
# 2. Integration / Status Error Endpoint Tests
# ----------------------------------------------------------------------

def test_api_endpoint_llm_authentication_error(client, valid_tracker):
    """Test API error response when LLM auth fails."""
    fake_downloaded = [{
        "source_row": 2, "name": "Alice Smith", "resume_url": "https://example.com/alice.pdf",
        "local_path": "fake.pdf", "status": "downloaded", "error": None
    }]
    fake_resumes = [{
        "source_row": 2, "name": "Alice Smith", "resume_url": "https://example.com/alice.pdf",
        "local_path": "fake.pdf", "status": "text_extracted",
        "text": "Alice Smith is a Python Django engineer with 5 years experience.", "error": None
    }]

    with patch("src.api.main.download_all_resumes", return_value=fake_downloaded):
        with patch("src.api.main.extract_all_resume_texts", return_value=fake_resumes):
            with patch("src.api.main.extract_requirements") as mock_extract:
                mock_extract.side_effect = Exception("401 Invalid API Key: secret_test_abc123")

                with open(valid_tracker, "rb") as f:
                    response = client.post(
                        "/api/recruitment/search",
                        files={"candidate_file": ("Tracker.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                        data={"jd_text": "Python engineer"}
                    )

                assert response.status_code == 202
                job_id = response.json()["job_id"]
                stat_resp = client.get(f"/api/recruitment/jobs/{job_id}/status")
                assert stat_resp.status_code == 200
                data = stat_resp.json()
                assert data["status"] == "failed"
                assert "error" in data
                assert data["error"]["code"] == "LLM_AUTHENTICATION_ERROR"
                assert data["error"]["stage"] == "jd_requirement_extraction"
                assert "secret_test" not in data["error"]["message"]


def test_api_endpoint_llm_rate_limit_error(client, valid_tracker):
    """Test API error response when LLM rate limit is reached."""
    fake_downloaded = [{
        "source_row": 2, "name": "Alice Smith", "resume_url": "https://example.com/alice.pdf",
        "local_path": "fake.pdf", "status": "downloaded", "error": None
    }]
    fake_resumes = [{
        "source_row": 2, "name": "Alice Smith", "resume_url": "https://example.com/alice.pdf",
        "local_path": "fake.pdf", "status": "text_extracted",
        "text": "Alice Smith is a Python Django engineer with 5 years experience.", "error": None
    }]

    with patch("src.api.main.download_all_resumes", return_value=fake_downloaded):
        with patch("src.api.main.extract_all_resume_texts", return_value=fake_resumes):
            with patch("src.api.main.extract_requirements") as mock_extract:
                mock_extract.side_effect = Exception("429 Too Many Requests: Rate limit exceeded")

                with open(valid_tracker, "rb") as f:
                    response = client.post(
                        "/api/recruitment/search",
                        files={"candidate_file": ("Tracker.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                        data={"jd_text": "Python engineer"}
                    )

                assert response.status_code == 202
                job_id = response.json()["job_id"]
                stat_resp = client.get(f"/api/recruitment/jobs/{job_id}/status")
                assert stat_resp.status_code == 200
                data = stat_resp.json()
                assert data["status"] == "failed"
                assert "error" in data
                assert data["error"]["code"] == "LLM_RATE_LIMIT_ERROR"
                assert data["error"]["stage"] == "jd_requirement_extraction"


def test_api_endpoint_non_llm_input_validation(client, valid_tracker):
    """Test API endpoint response on non-LLM synchronous validation error (empty JD)."""
    with open(valid_tracker, "rb") as f:
        response = client.post(
            "/api/recruitment/search",
            files={"candidate_file": ("Tracker.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"jd_text": ""}
        )

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "INVALID_INPUT_ERROR"
    assert data["error"]["stage"] == "input_validation"


def test_api_endpoint_non_llm_candidate_ingestion_error(client):
    """Test API response on corrupt Excel file (ingestion failure)."""
    # Send a plain text file pretending to be Excel
    response = client.post(
        "/api/recruitment/search",
        files={"candidate_file": ("Tracker.xlsx", b"invalid corrupt xlsx content", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"jd_text": "Python engineer"}
    )

    assert response.status_code == 202
    job_id = response.json()["job_id"]
    stat_resp = client.get(f"/api/recruitment/jobs/{job_id}/status")
    assert stat_resp.status_code == 200
    data = stat_resp.json()
    assert data["status"] == "failed"
    assert "error" in data
    assert data["error"]["code"] == "CANDIDATE_INGESTION_ERROR"
    assert data["error"]["stage"] == "candidate_ingestion"
