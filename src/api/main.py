from contextlib import asynccontextmanager
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import shutil
import threading
import time
from typing import Any, Dict, List, Optional
import uuid

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse, JSONResponse

from src.common.job_workspace import JobWorkspace
from src.common.errors import PipelineException, classify_llm_exception
from src.common.config import (
    LOG_MAX_BYTES,
    LOG_BACKUP_COUNT,
    LOG_FORMAT,
    DEFAULT_SEMANTIC_WEIGHT,
    DEFAULT_EXACT_WEIGHT,
    DEFAULT_WHOLE_RESUME_WEIGHT,
    DEFAULT_BEST_CHUNK_WEIGHT,
    DEFAULT_BEST_REQUIREMENT_WEIGHT,
    DEFAULT_TOP_K,
    EMBEDDING_MODEL_NAME,
)
from src.ingestion.xlsx_reader import load_candidates
from src.ingestion.resume_downloader import download_all_resumes
from src.ingestion.resume_text_extractor import extract_all_resume_texts
from src.ingestion.document_text_extractor import extract_document_text
from src.retrieval.resume_vector_store import (
    create_embedding_model,
    create_resume_documents,
    create_vector_store,
)
from src.processing.jd_requirements import extract_requirements
from src.retrieval.semantic_retriever import retrieve_semantically
from src.retrieval.exact_retriever import retrieve_exact_matches
from src.retrieval.candidate_aggregator import aggregate_candidates
from src.retrieval.reranker import rerank_candidates
from src.export.excel_exporter import export_ranked_candidates

# Configure standard logging with console and rotating file handlers
LOGS_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOGS_DIR / "server.log"

file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=LOG_MAX_BYTES,
    backupCount=LOG_BACKUP_COUNT,
    encoding="utf-8"
)
file_handler.setFormatter(logging.Formatter(LOG_FORMAT))

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(LOG_FORMAT))

logging.basicConfig(
    level=logging.INFO,
    handlers=[console_handler, file_handler]
)
logger = logging.getLogger("pcrs.api")

# -------------------------------------------------------------------
# Thread-safe in-memory ephemeral job status store
# -------------------------------------------------------------------
_job_statuses: Dict[str, Dict[str, Any]] = {}
_status_lock = threading.Lock()

TOTAL_STAGES = 10

STAGE_METADATA = {
    1: ("candidate_ingestion", "Candidate ingestion", "Reading candidate spreadsheet and validating columns..."),
    2: ("jd_requirement_extraction", "JD requirement extraction", "Extracting key technical requirements from job description..."),
    3: ("resume_download", "Downloading candidate resumes", "Downloading candidate resumes from storage..."),
    4: ("resume_extraction", "Extracting resume texts", "Parsing and extracting text from candidate resumes..."),
    5: ("vector_store_creation", "Creating vector embeddings", "Building in-memory vector embeddings for semantic search..."),
    6: ("semantic_retrieval", "Performing semantic search", "Retrieving candidate chunks matching JD semantics..."),
    7: ("exact_retrieval", "Performing exact keyword match", "Matching explicit technical skills and keywords..."),
    8: ("candidate_aggregation", "Aggregating evidence", "Combining semantic and exact retrieval evidence..."),
    9: ("reranking", "Scoring and reranking", "Scoring, normalizing, and ranking candidates..."),
    10: ("excel_export", "Generating Excel report", "Generating finalized ranked candidate spreadsheet..."),
}


def update_job_status(
    job_id: str,
    status: str,
    stage: int = 1,
    total_stages: int = TOTAL_STAGES,
    stage_name: str = "",
    label: str = "",
    message: str = "",
    completed_stages: Optional[int] = None,
    error: Optional[Dict[str, Any]] = None,
    download_url: Optional[str] = None,
    candidates: Optional[list] = None,
) -> None:
    """Thread-safe helper to update the in-memory ephemeral status of a specific job_id."""
    with _status_lock:
        if job_id not in _job_statuses:
            _job_statuses[job_id] = {}

        entry = _job_statuses[job_id]
        entry["job_id"] = job_id
        entry["status"] = status
        entry["stage"] = stage
        entry["total_stages"] = total_stages
        entry["stage_name"] = stage_name
        entry["label"] = label
        entry["message"] = message
        entry["completed_stages"] = completed_stages if completed_stages is not None else max(0, stage - 1)
        entry["updated_at"] = time.time()

        if error is not None:
            entry["error"] = error
        if download_url is not None:
            entry["download_url"] = download_url
        if candidates is not None:
            entry["candidates"] = candidates


def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Thread-safe getter for a specific job status."""
    with _status_lock:
        status_data = _job_statuses.get(job_id)
        if status_data is None:
            return None
        return dict(status_data)


def cleanup_expired_jobs_and_statuses(
    base_runs_dir: str | Path = "data/runs",
    max_age_seconds: int = 3600
) -> List[str]:
    """
    Cleans up expired job workspace directories from disk and removes
    their corresponding entries from the in-memory _job_statuses dictionary.
    """
    cleaned_jobs = JobWorkspace.cleanup_expired_jobs(
        base_runs_dir=base_runs_dir,
        max_age_seconds=max_age_seconds
    )
    if cleaned_jobs:
        with _status_lock:
            for jid in cleaned_jobs:
                _job_statuses.pop(jid, None)
        logger.info(f"Cleaned up {len(cleaned_jobs)} expired job(s) from disk and status store: {cleaned_jobs}")
    return cleaned_jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load embedding model once on application startup
    logger.info(f"Initializing shared embedding model ({EMBEDDING_MODEL_NAME})...")
    app.state.embedding_model = create_embedding_model()
    logger.info("Shared embedding model loaded successfully into app.state.")
    # Sweep expired directories on startup
    try:
        cleanup_expired_jobs_and_statuses()
    except Exception as e:
        logger.warning(f"Error during startup cleanup: {e}")
    yield
    # Cleanup on application shutdown
    app.state.embedding_model = None


app = FastAPI(
    title="Candidate Retrieval API",
    lifespan=lifespan
)


@app.exception_handler(PipelineException)
async def pipeline_exception_handler(request: Request, exc: PipelineException):
    logger.error(
        f"Pipeline error occurred: stage={exc.stage} code={exc.code} "
        f"message='{exc.message}' technical_details='{exc.technical_details}'"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict()
    )


def _set_stage(job_id: str, stage_num: int):
    """Helper to update logger and status store for a specific stage boundary."""
    s_name, s_lbl, s_msg = STAGE_METADATA[stage_num]
    logger.info(f"Job {job_id} stage {s_name} ({stage_num}/{TOTAL_STAGES}) started")
    update_job_status(
        job_id=job_id,
        status="running",
        stage=stage_num,
        total_stages=TOTAL_STAGES,
        stage_name=s_name,
        label=s_lbl,
        message=s_msg,
        completed_stages=stage_num - 1,
    )


def run_pipeline(
    job_id: str,
    workspace: JobWorkspace,
    candidate_path: Path,
    jd_doc_path: Optional[Path],
    jd_raw_text: Optional[str],
    embedding_model: Any,
    semantic_weight: float,
    exact_weight: float,
    whole_resume_weight: float,
    best_chunk_weight: float,
    best_requirement_weight: float,
    top_k: int,
) -> None:
    """
    Executes the 10-stage recruitment pipeline in the background.
    Updates the specific job_id's status at each stage boundary.
    """
    try:
        # -------------------------------------------------------------------------
        # Stage 1: Candidate Ingestion & JD Document Parsing
        # -------------------------------------------------------------------------
        _set_stage(job_id, 1)
        try:
            if jd_doc_path:
                extracted_jd = extract_document_text(filepath=str(jd_doc_path))
            else:
                extracted_jd = extract_document_text(raw_text=jd_raw_text)

            candidates = load_candidates(str(candidate_path))
        except Exception as exc:
            logger.error(f"[{job_id}] Failure during candidate_ingestion: {type(exc).__name__}: {exc}")
            pe = PipelineException(
                code="CANDIDATE_INGESTION_ERROR",
                stage="candidate_ingestion",
                message=f"Failed to process candidate spreadsheet: {str(exc)}",
                status_code=400,
                technical_details=f"{type(exc).__name__}: {exc}"
            )
            update_job_status(
                job_id=job_id,
                status="failed",
                stage=1,
                stage_name="candidate_ingestion",
                label="Failed at candidate ingestion",
                message=pe.message,
                error=pe.to_dict()["error"]
            )
            return

        # -------------------------------------------------------------------------
        # Stage 2: JD Requirement Extraction (Fail-Fast before expensive downloads)
        # -------------------------------------------------------------------------
        _set_stage(job_id, 2)
        try:
            jd_requirements = extract_requirements(extracted_jd)
        except Exception as exc:
            logger.error(f"[{job_id}] Failure during jd_requirement_extraction: {type(exc).__name__}: {exc}")
            pe = classify_llm_exception(exc, stage="jd_requirement_extraction")
            update_job_status(
                job_id=job_id,
                status="failed",
                stage=2,
                stage_name="jd_requirement_extraction",
                label="Failed at JD requirement extraction",
                message=pe.message,
                error=pe.to_dict()["error"]
            )
            return

        # -------------------------------------------------------------------------
        # Stage 3: Resume Download directly into workspace.resumes_dir
        # -------------------------------------------------------------------------
        _set_stage(job_id, 3)
        try:
            downloaded_records = download_all_resumes(
                candidates,
                resumes_dir=workspace.resumes_dir
            )
        except Exception as exc:
            logger.error(f"[{job_id}] Failure during resume_download: {type(exc).__name__}: {exc}")
            pe = PipelineException(
                code="RESUME_DOWNLOAD_ERROR",
                stage="resume_download",
                message="Failed to download candidate resumes.",
                status_code=500,
                technical_details=f"{type(exc).__name__}: {exc}"
            )
            update_job_status(
                job_id=job_id,
                status="failed",
                stage=3,
                stage_name="resume_download",
                label="Failed at resume download",
                message=pe.message,
                error=pe.to_dict()["error"]
            )
            return

        # -------------------------------------------------------------------------
        # Stage 4: Resume Text Extraction
        # -------------------------------------------------------------------------
        _set_stage(job_id, 4)
        try:
            resumes = extract_all_resume_texts(downloaded_records)
        except Exception as exc:
            logger.error(f"[{job_id}] Failure during resume_extraction: {type(exc).__name__}: {exc}")
            pe = PipelineException(
                code="RESUME_EXTRACTION_ERROR",
                stage="resume_extraction",
                message="Failed to extract text from candidate resumes.",
                status_code=500,
                technical_details=f"{type(exc).__name__}: {exc}"
            )
            update_job_status(
                job_id=job_id,
                status="failed",
                stage=4,
                stage_name="resume_extraction",
                label="Failed at resume extraction",
                message=pe.message,
                error=pe.to_dict()["error"]
            )
            return

        logger.info(f"[{job_id}] Current run resumes extracted: {len(resumes)}")

        # -------------------------------------------------------------------------
        # Stage 5: In-Memory FAISS Vector Store Creation
        # -------------------------------------------------------------------------
        _set_stage(job_id, 5)
        try:
            documents = create_resume_documents(resumes)
            logger.info(f"[{job_id}] Documents/chunks created: {len(documents)}")

            vector_store = create_vector_store(
                documents,
                embedding_model
            )
        except Exception as exc:
            logger.error(f"[{job_id}] Failure during vector_store_creation: {type(exc).__name__}: {exc}")
            pe = PipelineException(
                code="VECTOR_STORE_ERROR",
                stage="vector_store_creation",
                message="Failed to initialize resume vector index. Please check candidate resumes.",
                status_code=500,
                technical_details=f"{type(exc).__name__}: {exc}"
            )
            update_job_status(
                job_id=job_id,
                status="failed",
                stage=5,
                stage_name="vector_store_creation",
                label="Failed at vector store creation",
                message=pe.message,
                error=pe.to_dict()["error"]
            )
            return

        # -------------------------------------------------------------------------
        # Stage 6: Semantic Retrieval
        # -------------------------------------------------------------------------
        _set_stage(job_id, 6)
        try:
            semantic_results = retrieve_semantically(
                vector_store,
                extracted_jd,
                jd_requirements
            )
        except Exception as exc:
            logger.error(f"[{job_id}] Failure during semantic_retrieval: {type(exc).__name__}: {exc}")
            pe = PipelineException(
                code="SEMANTIC_RETRIEVAL_ERROR",
                stage="semantic_retrieval",
                message="Failed during semantic retrieval.",
                status_code=500,
                technical_details=f"{type(exc).__name__}: {exc}"
            )
            update_job_status(
                job_id=job_id,
                status="failed",
                stage=6,
                stage_name="semantic_retrieval",
                label="Failed at semantic retrieval",
                message=pe.message,
                error=pe.to_dict()["error"]
            )
            return

        # -------------------------------------------------------------------------
        # Stage 7: Exact Keyword Retrieval
        # -------------------------------------------------------------------------
        _set_stage(job_id, 7)
        try:
            exact_results = retrieve_exact_matches(
                resumes,
                jd_requirements,
                k=top_k
            )
        except Exception as exc:
            logger.error(f"[{job_id}] Failure during exact_retrieval: {type(exc).__name__}: {exc}")
            pe = PipelineException(
                code="EXACT_RETRIEVAL_ERROR",
                stage="exact_retrieval",
                message="Failed during exact keyword retrieval.",
                status_code=500,
                technical_details=f"{type(exc).__name__}: {exc}"
            )
            update_job_status(
                job_id=job_id,
                status="failed",
                stage=7,
                stage_name="exact_retrieval",
                label="Failed at exact retrieval",
                message=pe.message,
                error=pe.to_dict()["error"]
            )
            return

        # -------------------------------------------------------------------------
        # Stage 8: Candidate Evidence Aggregation
        # -------------------------------------------------------------------------
        _set_stage(job_id, 8)
        try:
            aggregated_candidates = aggregate_candidates(
                semantic_results,
                exact_results
            )
        except Exception as exc:
            logger.error(f"[{job_id}] Failure during candidate_aggregation: {type(exc).__name__}: {exc}")
            pe = PipelineException(
                code="AGGREGATION_ERROR",
                stage="candidate_aggregation",
                message="Failed to aggregate candidate retrieval results.",
                status_code=500,
                technical_details=f"{type(exc).__name__}: {exc}"
            )
            update_job_status(
                job_id=job_id,
                status="failed",
                stage=8,
                stage_name="candidate_aggregation",
                label="Failed at candidate aggregation",
                message=pe.message,
                error=pe.to_dict()["error"]
            )
            return

        # -------------------------------------------------------------------------
        # Stage 9: Scoring & Reranking
        # -------------------------------------------------------------------------
        _set_stage(job_id, 9)
        try:
            ranked_candidates, semantic_min, semantic_max = rerank_candidates(
                aggregated_candidates,
                top_k=top_k,
                semantic_weight=semantic_weight,
                exact_weight=exact_weight,
                whole_resume_weight=whole_resume_weight,
                best_chunk_weight=best_chunk_weight,
                best_requirement_weight=best_requirement_weight
            )
        except Exception as exc:
            logger.error(f"[{job_id}] Failure during reranking: {type(exc).__name__}: {exc}")
            pe = PipelineException(
                code="RERANKING_ERROR",
                stage="reranking",
                message="Failed during candidate scoring and reranking.",
                status_code=500,
                technical_details=f"{type(exc).__name__}: {exc}"
            )
            update_job_status(
                job_id=job_id,
                status="failed",
                stage=9,
                stage_name="reranking",
                label="Failed at reranking",
                message=pe.message,
                error=pe.to_dict()["error"]
            )
            return

        # -------------------------------------------------------------------------
        # Stage 10: Excel Export & Status Finalization
        # -------------------------------------------------------------------------
        _set_stage(job_id, 10)
        try:
            export_ranked_candidates(
                input_excel=str(candidate_path),
                output_excel=str(workspace.output_excel_path),
                ranked_candidates=ranked_candidates,
                downloaded_records=downloaded_records,
                resumes=resumes
            )
        except Exception as exc:
            logger.error(f"[{job_id}] Failure during excel_export: {type(exc).__name__}: {exc}")
            pe = PipelineException(
                code="EXCEL_EXPORT_ERROR",
                stage="excel_export",
                message="Failed to generate the ranked Excel report.",
                status_code=500,
                technical_details=f"{type(exc).__name__}: {exc}"
            )
            update_job_status(
                job_id=job_id,
                status="failed",
                stage=10,
                stage_name="excel_export",
                label="Failed at Excel export",
                message=pe.message,
                error=pe.to_dict()["error"]
            )
            return

        # Construct final candidates payload
        candidates_response = []
        for rank, candidate in enumerate(ranked_candidates, start=1):
            candidates_response.append({
                "rank": rank,
                "name": candidate["name"],
                "source_row": candidate["source_row"],
                "final_score": candidate["final_score"],
                "semantic_score": candidate["semantic_score"],
                "semantic_normalized": candidate["semantic_normalized"],
                "exact_score": candidate["exact_score"],
            })

        download_url = f"/api/recruitment/download/{job_id}"

        update_job_status(
            job_id=job_id,
            status="completed",
            stage=10,
            total_stages=TOTAL_STAGES,
            stage_name="excel_export",
            label="Completed",
            message="Candidate retrieval and reranking completed successfully.",
            completed_stages=10,
            download_url=download_url,
            candidates=candidates_response,
        )

        logger.info(f"Job {job_id} pipeline completed successfully.")

        # Trigger opportunistic cleanup of expired jobs & statuses
        try:
            cleanup_expired_jobs_and_statuses()
        except Exception as clean_exc:
            logger.warning(f"Error during opportunistic cleanup: {clean_exc}")

    except Exception as unexpected_exc:
        logger.error(f"[{job_id}] Unexpected error in pipeline: {unexpected_exc}")
        update_job_status(
            job_id=job_id,
            status="failed",
            stage=1,
            stage_name="unknown",
            label="Failed",
            message="An unexpected server error occurred.",
            error={
                "code": "INTERNAL_SERVER_ERROR",
                "stage": "unknown",
                "message": "An unexpected server error occurred."
            }
        )


@app.post("/api/recruitment/search", status_code=202)
def search_candidates(
    request: Request,
    background_tasks: BackgroundTasks,
    candidate_file: UploadFile = File(...),
    jd_file: Optional[UploadFile] = File(None),
    jd_text: Optional[str] = Form(None),
    semantic_weight: float = Form(DEFAULT_SEMANTIC_WEIGHT),
    exact_weight: float = Form(DEFAULT_EXACT_WEIGHT),
    whole_resume_weight: float = Form(DEFAULT_WHOLE_RESUME_WEIGHT),
    best_chunk_weight: float = Form(DEFAULT_BEST_CHUNK_WEIGHT),
    best_requirement_weight: float = Form(DEFAULT_BEST_REQUIREMENT_WEIGHT),
    top_k: int = Form(DEFAULT_TOP_K),
):
    """
    Accepts candidate file & JD, generates backend job_id, registers job,
    schedules execution in background, and returns HTTP 202 immediately.
    """
    if not jd_file and (not jd_text or not jd_text.strip()):
        raise PipelineException(
            code="INVALID_INPUT_ERROR",
            stage="input_validation",
            message="Please provide either a Job Description file (.pdf, .docx, .txt) or paste JD text.",
            status_code=400
        )

    # 1. Backend strictly generates job_id
    job_id = uuid.uuid4().hex
    workspace = JobWorkspace(job_id=job_id)
    workspace.create_dirs()

    # 2. Save uploaded files to workspace synchronously before dispatching
    candidate_path = workspace.get_candidate_file_path(candidate_file.filename or "Tracker.xlsx")
    with open(candidate_path, "wb") as file:
        shutil.copyfileobj(candidate_file.file, file)

    jd_doc_path = None
    if jd_file:
        jd_doc_path = workspace.get_jd_file_path(jd_file.filename or "JD.txt")
        with open(jd_doc_path, "wb") as file:
            shutil.copyfileobj(jd_file.file, file)

    # 3. Register initial status in thread-safe status store
    s_name, s_lbl, s_msg = STAGE_METADATA[1]
    update_job_status(
        job_id=job_id,
        status="running",
        stage=1,
        total_stages=TOTAL_STAGES,
        stage_name=s_name,
        label=s_lbl,
        message=s_msg,
        completed_stages=0,
    )

    # 4. Dispatch background pipeline execution
    embedding_model = request.app.state.embedding_model
    background_tasks.add_task(
        run_pipeline,
        job_id=job_id,
        workspace=workspace,
        candidate_path=candidate_path,
        jd_doc_path=jd_doc_path,
        jd_raw_text=jd_text,
        embedding_model=embedding_model,
        semantic_weight=semantic_weight,
        exact_weight=exact_weight,
        whole_resume_weight=whole_resume_weight,
        best_chunk_weight=best_chunk_weight,
        best_requirement_weight=best_requirement_weight,
        top_k=top_k,
    )

    logger.info(f"Job {job_id} registered and scheduled in background.")

    # 5. Return HTTP 202 with backend-generated job_id immediately
    return {
        "job_id": job_id,
        "status": "running"
    }


@app.get("/api/recruitment/jobs/{job_id}/status")
def get_job_status_endpoint(job_id: str):
    """
    Returns the real-time execution status of the exact requested job_id.
    """
    try:
        JobWorkspace.from_job_id(job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    status_data = get_job_status(job_id)
    if status_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job not found: {job_id}. The job may have expired or does not exist."
        )

    return status_data


@app.get("/api/recruitment/download/{job_id}")
def download_results_by_job_id(job_id: str):
    try:
        workspace = JobWorkspace.from_job_id(job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not workspace.output_excel_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No results found for job ID: {job_id}. The job may have expired or not finished."
        )

    return FileResponse(
        str(workspace.output_excel_path),
        filename="ranked_candidates.xlsx",
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
    )


@app.get("/api/recruitment/download")
def download_results_legacy(job_id: Optional[str] = None):
    if not job_id:
        raise HTTPException(
            status_code=400,
            detail="Please provide a job_id query parameter, e.g. /api/recruitment/download?job_id=<job_id>, or use /api/recruitment/download/{job_id}"
        )
    return download_results_by_job_id(job_id)