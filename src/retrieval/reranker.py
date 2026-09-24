from src.common.config import (
    DEFAULT_SEMANTIC_WEIGHT,
    DEFAULT_EXACT_WEIGHT,
    DEFAULT_WHOLE_RESUME_WEIGHT,
    DEFAULT_BEST_CHUNK_WEIGHT,
    DEFAULT_BEST_REQUIREMENT_WEIGHT,
    DEFAULT_TOP_K,
)


def get_semantic_evidence(candidate):
    """
    Extract best (minimum) distance scores for whole resume, chunk,
    and requirement matches from candidate semantic evidence.
    """
    semantic_evidence = candidate.get("semantic_evidence") or {}
    jd_results = semantic_evidence.get("jd_results", [])
    requirement_results = semantic_evidence.get("requirement_results", [])

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

    whole_resume_score = min(whole_resume_scores) if whole_resume_scores else None
    best_chunk_score = min(chunk_scores) if chunk_scores else None
    best_requirement_score = min(requirement_scores) if requirement_scores else None

    candidate["whole_resume_score"] = whole_resume_score
    candidate["best_chunk_score"] = best_chunk_score
    candidate["best_requirement_score"] = best_requirement_score

    return (
        whole_resume_score,
        best_chunk_score,
        best_requirement_score
    )


def calculate_semantic_score(
    whole_resume_score,
    best_chunk_score,
    best_requirement_score,
    whole_resume_weight=DEFAULT_WHOLE_RESUME_WEIGHT,
    best_chunk_weight=DEFAULT_BEST_CHUNK_WEIGHT,
    best_requirement_weight=DEFAULT_BEST_REQUIREMENT_WEIGHT
):
    """
    Calculate the combined raw semantic distance score using available weights.
    """
    weighted_sum = 0.0
    available_weight = 0.0

    if whole_resume_score is not None:
        weighted_sum += whole_resume_score * whole_resume_weight
        available_weight += whole_resume_weight

    if best_chunk_score is not None:
        weighted_sum += best_chunk_score * best_chunk_weight
        available_weight += best_chunk_weight

    if best_requirement_score is not None:
        weighted_sum += best_requirement_score * best_requirement_weight
        available_weight += best_requirement_weight

    if available_weight == 0:
        return None

    return weighted_sum / available_weight


def get_exact_score(candidate):
    """
    Calculate deterministic exact match ratio from exact evidence.
    """
    exact_evidence = candidate.get("exact_evidence") or {}
    matched = exact_evidence.get("total_matched_count", 0)
    total = 0

    for data in exact_evidence.values():
        if not isinstance(data, dict):
            continue
        total += data.get("matched_count", 0)
        total += data.get("unmatched_count", 0)

    if total == 0:
        return 0.0

    return matched / total


def normalize_semantic_score(score, semantic_min, semantic_max):
    """
    Invert and normalize raw semantic distance into a [0.0, 1.0] similarity score.
    Lowest distance (best fit) maps to 1.0, highest distance maps to 0.0.
    """
    if score is None or semantic_min is None or semantic_max is None:
        return 0.0

    if semantic_max == semantic_min:
        return 1.0

    normalized = (semantic_max - score) / (semantic_max - semantic_min)
    return max(0.0, min(1.0, normalized))


def rerank_candidates(
    aggregated_candidates,
    top_k=DEFAULT_TOP_K,
    semantic_weight=DEFAULT_SEMANTIC_WEIGHT,
    exact_weight=DEFAULT_EXACT_WEIGHT,
    whole_resume_weight=DEFAULT_WHOLE_RESUME_WEIGHT,
    best_chunk_weight=DEFAULT_BEST_CHUNK_WEIGHT,
    best_requirement_weight=DEFAULT_BEST_REQUIREMENT_WEIGHT,
    semantic_min=None,
    semantic_max=None
):
    """
    Compute multi-aspect scores, perform cohort normalization, and sort candidates by final score.
    """
    ranked_candidates = []

    for candidate in aggregated_candidates:
        (
            whole_resume_score,
            best_chunk_score,
            best_requirement_score
        ) = get_semantic_evidence(candidate)

        semantic_score = calculate_semantic_score(
            whole_resume_score,
            best_chunk_score,
            best_requirement_score,
            whole_resume_weight,
            best_chunk_weight,
            best_requirement_weight
        )

        exact_score = get_exact_score(candidate)

        candidate["semantic_score"] = semantic_score
        candidate["exact_score"] = exact_score
        ranked_candidates.append(candidate)

    semantic_scores = [
        c["semantic_score"]
        for c in ranked_candidates
        if c["semantic_score"] is not None
    ]

    if semantic_scores:
        if semantic_min is None:
            semantic_min = min(semantic_scores)
        if semantic_max is None:
            semantic_max = max(semantic_scores)

    for candidate in ranked_candidates:
        semantic_normalized = normalize_semantic_score(
            candidate["semantic_score"],
            semantic_min,
            semantic_max
        )
        candidate["semantic_normalized"] = semantic_normalized
        candidate["final_score"] = (
            semantic_weight * semantic_normalized
            + exact_weight * candidate["exact_score"]
        )

    ranked_candidates.sort(
        key=lambda candidate: candidate["final_score"],
        reverse=True
    )

    return ranked_candidates[:top_k], semantic_min, semantic_max