from src.ingestion.document_text_extractor import extract_text_from_pdf
from src.ingestion.resume_text_store import load_resume_texts
from src.retrieval.resume_vector_store import (
    create_embedding_model,
    get_or_create_vector_store,
)
from src.processing.jd_requirements import extract_requirements
from src.retrieval.semantic_retriever import retrieve_semantically
from src.retrieval.exact_retriever import retrieve_exact_matches
from src.retrieval.candidate_aggregator import aggregate_candidates


VECTOR_STORE_PATH = "data/vector_store/resumes"
JD_PATH = "data/JD_Forward Deployed Engineer Intern (6 months -Paid).pdf"
RESUME_PATH = "data/processed/resumes.json"

TOP_K = 20

SEMANTIC_WEIGHT = 0.8
EXACT_WEIGHT = 0.2

WHOLE_RESUME_WEIGHT = 0.3
BEST_CHUNK_WEIGHT = 0.4
BEST_REQUIREMENT_WEIGHT = 0.3

SEMANTIC_MIN = None
SEMANTIC_MAX = None


def get_semantic_evidence(candidate):

    semantic_evidence = (
        candidate.get("semantic_evidence") or {}
    )

    jd_results = semantic_evidence.get(
        "jd_results",
        []
    )

    requirement_results = semantic_evidence.get(
        "requirement_results",
        []
    )

    whole_resume_scores = []
    chunk_scores = []
    requirement_scores = []

    for result in jd_results:

        score = float(result["score"])

        if result.get("document_type") == "whole_resume":
            whole_resume_scores.append(score)
        else:
            chunk_scores.append(score)

    for result in requirement_results:

        score = float(result["score"])
        requirement_scores.append(score)

    whole_resume_score = (
        min(whole_resume_scores)
        if whole_resume_scores
        else None
    )

    best_chunk_score = (
        min(chunk_scores)
        if chunk_scores
        else None
    )

    best_requirement_score = (
        min(requirement_scores)
        if requirement_scores
        else None
    )

    candidate["whole_resume_score"] = whole_resume_score
    candidate["best_chunk_score"] = best_chunk_score
    candidate["best_requirement_score"] = (
        best_requirement_score
    )

    return (
        whole_resume_score,
        best_chunk_score,
        best_requirement_score
    )


def calculate_semantic_score(
    whole_resume_score,
    best_chunk_score,
    best_requirement_score,
    whole_resume_weight,
    best_chunk_weight,
    best_requirement_weight
):

    weighted_sum = 0.0
    available_weight = 0.0

    if whole_resume_score is not None:

        weighted_sum += (
            whole_resume_score
            * whole_resume_weight
        )

        available_weight += (
            whole_resume_weight
        )

    if best_chunk_score is not None:

        weighted_sum += (
            best_chunk_score
            * best_chunk_weight
        )

        available_weight += (
            best_chunk_weight
        )

    if best_requirement_score is not None:

        weighted_sum += (
            best_requirement_score
            * best_requirement_weight
        )

        available_weight += (
            best_requirement_weight
        )

    if available_weight == 0:
        return None

    return (
        weighted_sum
        / available_weight
    )


def get_exact_score(candidate):

    exact_evidence = (
        candidate.get("exact_evidence") or {}
    )

    matched = exact_evidence.get(
        "total_matched_count",
        0
    )

    total = 0

    for data in exact_evidence.values():

        if not isinstance(data, dict):
            continue

        total += data.get(
            "matched_count",
            0
        )

        total += data.get(
            "unmatched_count",
            0
        )

    if total == 0:
        return 0.0

    return matched / total


def normalize_semantic_score(
    score,
    semantic_min,
    semantic_max
):

    if score is None:
        return 0.0

    if semantic_min is None:
        return 0.0

    if semantic_max is None:
        return 0.0

    if semantic_max == semantic_min:
        return 1.0

    normalized = (
        semantic_max - score
    ) / (
        semantic_max - semantic_min
    )

    return max(
        0.0,
        min(1.0, normalized)
    )


def rerank_candidates(
    aggregated_candidates,
    top_k=20,
    semantic_weight=0.8,
    exact_weight=0.2,
    whole_resume_weight=0.3,
    best_chunk_weight=0.4,
    best_requirement_weight=0.3,
    semantic_min=None,
    semantic_max=None
):

    ranked_candidates = []

    for candidate in aggregated_candidates:

        (
            whole_resume_score,
            best_chunk_score,
            best_requirement_score
        ) = get_semantic_evidence(
            candidate
        )

        semantic_score = calculate_semantic_score(
            whole_resume_score,
            best_chunk_score,
            best_requirement_score,
            whole_resume_weight,
            best_chunk_weight,
            best_requirement_weight
        )

        exact_score = get_exact_score(
            candidate
        )

        candidate["semantic_score"] = (
            semantic_score
        )

        candidate["exact_score"] = (
            exact_score
        )

        ranked_candidates.append(
            candidate
        )

    semantic_scores = [
        candidate["semantic_score"]
        for candidate in ranked_candidates
        if candidate["semantic_score"] is not None
    ]

    if semantic_scores:

        if semantic_min is None:
            semantic_min = min(
                semantic_scores
            )

        if semantic_max is None:
            semantic_max = max(
                semantic_scores
            )

    for candidate in ranked_candidates:

        semantic_normalized = (
            normalize_semantic_score(
                candidate["semantic_score"],
                semantic_min,
                semantic_max
            )
        )

        candidate["semantic_normalized"] = (
            semantic_normalized
        )

        candidate["final_score"] = (
            semantic_weight
            * semantic_normalized
            +
            exact_weight
            * candidate["exact_score"]
        )

    ranked_candidates.sort(
        key=lambda candidate:
            candidate["final_score"],
        reverse=True
    )

    return ranked_candidates[:top_k], semantic_min, semantic_max


def print_results(
    ranked_candidates,
    semantic_weight,
    exact_weight,
    whole_resume_weight,
    best_chunk_weight,
    best_requirement_weight,
    semantic_min,
    semantic_max
):

    print("=" * 100)
    print("RERANKED CANDIDATES")
    print("=" * 100)

    print(
        f"Semantic weight          : "
        f"{semantic_weight}"
    )

    print(
        f"Exact weight             : "
        f"{exact_weight}"
    )

    print(
        f"Whole resume weight      : "
        f"{whole_resume_weight}"
    )

    print(
        f"Best chunk weight        : "
        f"{best_chunk_weight}"
    )

    print(
        f"Best requirement weight  : "
        f"{best_requirement_weight}"
    )

    print(
        f"Semantic min             : "
        f"{semantic_min}"
    )

    print(
        f"Semantic max             : "
        f"{semantic_max}"
    )

    print("-" * 100)

    for index, candidate in enumerate(
        ranked_candidates,
        start=1
    ):

        print(
            f"{index}. "
            f"{candidate['name']} "
            f"| row={candidate['source_row']}"
        )

        print(
            f"   Whole resume     : "
            f"{candidate.get('whole_resume_score')}"
        )

        print(
            f"   Best chunk       : "
            f"{candidate.get('best_chunk_score')}"
        )

        print(
            f"   Best requirement : "
            f"{candidate.get('best_requirement_score')}"
        )

        print(
            f"   Semantic score   : "
            f"{candidate['semantic_score']}"
        )

        print(
            f"   Semantic norm.   : "
            f"{candidate['semantic_normalized']:.4f}"
        )

        print(
            f"   Exact score      : "
            f"{candidate['exact_score']:.4f}"
        )

        print(
            f"   Final score      : "
            f"{candidate['final_score']:.4f}"
        )

        print()


if __name__ == "__main__":

    resumes = load_resume_texts(
        RESUME_PATH
    )

    embedding_model = create_embedding_model()

    vector_store = get_or_create_vector_store(
        VECTOR_STORE_PATH,
        embedding_model
    )

    jd_text = extract_text_from_pdf(
        JD_PATH
    )

    jd_requirements = extract_requirements(
        jd_text
    )

    semantic_results = retrieve_semantically(
        vector_store,
        jd_text,
        jd_requirements
    )

    exact_results = retrieve_exact_matches(
        resumes,
        jd_requirements,
        k=30
    )

    aggregated_candidates = aggregate_candidates(
        semantic_results,
        exact_results
    )

    ranked_candidates, semantic_min, semantic_max = (
        rerank_candidates(
            aggregated_candidates,
            top_k=TOP_K,
            semantic_weight=SEMANTIC_WEIGHT,
            exact_weight=EXACT_WEIGHT,
            whole_resume_weight=WHOLE_RESUME_WEIGHT,
            best_chunk_weight=BEST_CHUNK_WEIGHT,
            best_requirement_weight=BEST_REQUIREMENT_WEIGHT,
            semantic_min=SEMANTIC_MIN,
            semantic_max=SEMANTIC_MAX
        )
    )

    print_results(
        ranked_candidates,
        SEMANTIC_WEIGHT,
        EXACT_WEIGHT,
        WHOLE_RESUME_WEIGHT,
        BEST_CHUNK_WEIGHT,
        BEST_REQUIREMENT_WEIGHT,
        semantic_min,
        semantic_max
    )