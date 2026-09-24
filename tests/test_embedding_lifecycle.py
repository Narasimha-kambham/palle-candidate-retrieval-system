import os
import openpyxl
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def valid_tracker():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["Name", "Resume Path"])
    ws.append(["Alice Smith", "https://example.com/alice.pdf"])

    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    wb.save(tmp.name)
    tmp.close()
    yield tmp.name
    if os.path.exists(tmp.name):
        try:
            os.remove(tmp.name)
        except OSError:
            pass


def test_lifespan_loads_shared_embedding_model_once():
    """Verify that TestClient entering lifespan loads the model once into app.state."""
    mock_model = MagicMock()
    with patch("src.api.main.create_embedding_model", return_value=mock_model) as mock_create:
        with TestClient(app) as client:
            # Model should be loaded upon startup
            assert mock_create.call_count == 1
            assert app.state.embedding_model is mock_model


def test_search_handler_reuses_app_state_model_without_reloading(valid_tracker):
    """Verify that multiple consecutive searches reuse the app.state model without calling create_embedding_model()."""
    mock_model = MagicMock()

    fake_downloaded = [{
        "source_row": 2, "name": "Alice Smith", "resume_url": "https://example.com/alice.pdf",
        "local_path": "fake.pdf", "status": "downloaded", "error": None
    }]
    fake_resumes = [{
        "source_row": 2, "name": "Alice Smith", "resume_url": "https://example.com/alice.pdf",
        "local_path": "fake.pdf", "status": "text_extracted",
        "text": "Alice is a Python engineer with FastAPI experience.", "error": None
    }]

    with patch("src.api.main.create_embedding_model", return_value=mock_model) as mock_create:
        with TestClient(app) as client:
            assert mock_create.call_count == 1  # Loaded once at startup

            with patch("src.api.main.download_all_resumes", return_value=fake_downloaded), \
                 patch("src.api.main.extract_all_resume_texts", return_value=fake_resumes), \
                 patch("src.api.main.create_vector_store") as mock_cvs, \
                 patch("src.api.main.extract_requirements"), \
                 patch("src.api.main.retrieve_semantically", return_value={"jd_results": [], "requirement_results": []}), \
                 patch("src.api.main.retrieve_exact_matches", return_value=[]), \
                 patch("src.api.main.export_ranked_candidates"):

                # Request 1
                with open(valid_tracker, "rb") as f:
                    resp1 = client.post(
                        "/api/recruitment/search",
                        files={"candidate_file": ("Tracker.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                        data={"jd_text": "Python engineer"}
                    )
                assert resp1.status_code == 202

                # Request 2
                with open(valid_tracker, "rb") as f:
                    resp2 = client.post(
                        "/api/recruitment/search",
                        files={"candidate_file": ("Tracker.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                        data={"jd_text": "Python engineer"}
                    )
                assert resp2.status_code == 202

                # Request 3
                with open(valid_tracker, "rb") as f:
                    resp3 = client.post(
                        "/api/recruitment/search",
                        files={"candidate_file": ("Tracker.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                        data={"jd_text": "Python engineer"}
                    )
                assert resp3.status_code == 202

                # Crucial assertion: create_embedding_model was NOT called during requests
                assert mock_create.call_count == 1

                # Crucial assertion: create_vector_store was called 3 times, each with the shared embedding_model
                assert mock_cvs.call_count == 3
                for call in mock_cvs.call_args_list:
                    # call[0][1] is the embeddings argument passed to create_vector_store(documents, embedding_model)
                    assert call[0][1] is mock_model
