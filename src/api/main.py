from pathlib import Path
import shutil
import tempfile

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse

from typing import Optional
from src.ingestion.document_text_extractor import extract_document_text
from src.ingestion.resume_text_store import load_resume_texts
from src.retrieval.resume_vector_store import (
    create_embedding_model,
    get_or_create_vector_store,
)
from src.processing.jd_requirements import extract_requirements
from src.retrieval.semantic_retriever import retrieve_semantically
from src.retrieval.exact_retriever import retrieve_exact_matches
from src.retrieval.candidate_aggregator import aggregate_candidates
from src.retrieval.reranker import rerank_candidates
from src.export.excel_exporter import export_ranked_candidates


app = FastAPI(
    title="Candidate Retrieval API"
)


@app.post("/api/recruitment/search")
async def search_candidates(
    candidate_file: UploadFile = File(...),
    jd_file: Optional[UploadFile] = File(None),
    jd_text: Optional[str] = Form(None),
    semantic_weight: float = Form(0.8),
    exact_weight: float = Form(0.2),
    whole_resume_weight: float = Form(0.3),
    best_chunk_weight: float = Form(0.4),
    best_requirement_weight: float = Form(0.3),
    top_k: int = Form(20),
):
    if not jd_file and (not jd_text or not jd_text.strip()):
        return {
            "error": "Please provide either a Job Description file (.pdf, .docx, .txt) or paste JD text."
        }

    with tempfile.TemporaryDirectory() as temp_dir:

        temp_dir = Path(temp_dir)
        candidate_path = temp_dir / candidate_file.filename

        with open(candidate_path, "wb") as file:
            shutil.copyfileobj(
                candidate_file.file,
                file
            )

        if jd_file:
            jd_path = temp_dir / jd_file.filename
            with open(jd_path, "wb") as file:
                shutil.copyfileobj(
                    jd_file.file,
                    file
                )
            extracted_jd = extract_document_text(filepath=str(jd_path))
        else:
            extracted_jd = extract_document_text(raw_text=jd_text)

        resumes = load_resume_texts()

        embedding_model = create_embedding_model()

        vector_store = get_or_create_vector_store(
            "data/vector_store/resumes",
            embedding_model
        )

        jd_requirements = extract_requirements(
            extracted_jd
        )

        semantic_results = retrieve_semantically(
            vector_store,
            extracted_jd,
            jd_requirements
        )

        exact_results = retrieve_exact_matches(
            resumes,
            jd_requirements,
            k=top_k
        )

        aggregated_candidates = aggregate_candidates(
            semantic_results,
            exact_results
        )

        ranked_candidates, semantic_min, semantic_max = rerank_candidates(
            aggregated_candidates,
            top_k=top_k,
            semantic_weight=semantic_weight,
            exact_weight=exact_weight,
            whole_resume_weight=whole_resume_weight,
            best_chunk_weight=best_chunk_weight,
            best_requirement_weight=best_requirement_weight
        )

        output_path = Path(
            "data/output/ranked_candidates.xlsx"
        )

        export_ranked_candidates(
            input_excel=str(candidate_path),
            output_excel=str(output_path),
            ranked_candidates=ranked_candidates
        )

        candidates = []

        for rank, candidate in enumerate(
            ranked_candidates,
            start=1
        ):
            candidates.append({
                "rank": rank,
                "name": candidate["name"],
                "source_row": candidate["source_row"],
                "final_score": candidate["final_score"],
                "semantic_score": candidate["semantic_score"],
                "semantic_normalized": candidate[
                    "semantic_normalized"
                ],
                "exact_score": candidate["exact_score"],
            })

        return {
            "candidates": candidates,
            "excel_file": "/api/recruitment/download"
        }


@app.get("/api/recruitment/download")
def download_results():
    return FileResponse(
        "data/output/ranked_candidates.xlsx",
        filename="ranked_candidates.xlsx",
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
    )