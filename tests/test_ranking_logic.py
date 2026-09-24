import pytest
from src.retrieval.reranker import (
    calculate_semantic_score,
    normalize_semantic_score,
    get_exact_score,
    rerank_candidates,
)


# ==========================================================
# 1. Semantic Score Calculation Tests
# ==========================================================

def test_semantic_score_calculation_all_available():
    score = calculate_semantic_score(
        whole_resume_score=0.20,
        best_chunk_score=0.40,
        best_requirement_score=0.60,
        whole_resume_weight=0.3,
        best_chunk_weight=0.4,
        best_requirement_weight=0.3
    )
    assert pytest.approx(score, rel=1e-5) == 0.40


def test_semantic_score_calculation_whole_unavailable():
    score = calculate_semantic_score(
        whole_resume_score=None,
        best_chunk_score=0.40,
        best_requirement_score=0.60,
        whole_resume_weight=0.3,
        best_chunk_weight=0.4,
        best_requirement_weight=0.3
    )
    expected = (0.4 * 0.40 + 0.3 * 0.60) / 0.7
    assert pytest.approx(score, rel=1e-5) == expected


def test_semantic_score_calculation_single_evidence_type():
    score = calculate_semantic_score(
        whole_resume_score=None,
        best_chunk_score=0.55,
        best_requirement_score=None,
        whole_resume_weight=0.3,
        best_chunk_weight=0.4,
        best_requirement_weight=0.3
    )
    assert pytest.approx(score, rel=1e-5) == 0.55


def test_semantic_score_calculation_no_evidence():
    score = calculate_semantic_score(
        whole_resume_score=None,
        best_chunk_score=None,
        best_requirement_score=None,
        whole_resume_weight=0.3,
        best_chunk_weight=0.4,
        best_requirement_weight=0.3
    )
    assert score is None


# ==========================================================
# 2. Semantic Normalization Tests
# ==========================================================

def test_semantic_normalization_cases():
    s_min = 0.20
    s_max = 0.80

    assert pytest.approx(normalize_semantic_score(0.20, s_min, s_max), rel=1e-5) == 1.0
    assert pytest.approx(normalize_semantic_score(0.80, s_min, s_max), rel=1e-5) == 0.0
    assert pytest.approx(normalize_semantic_score(0.50, s_min, s_max), rel=1e-5) == 0.5
    assert normalize_semantic_score(0.50, 0.50, 0.50) == 1.0
    assert normalize_semantic_score(0.10, s_min, s_max) == 1.0
    assert normalize_semantic_score(0.90, s_min, s_max) == 0.0
    assert normalize_semantic_score(None, s_min, s_max) == 0.0


# ==========================================================
# 3. Exact Score Tests
# ==========================================================

def test_exact_score_calculation():
    cand_8_2 = {
        "exact_evidence": {
            "total_matched_count": 8,
            "skills": {"matched_count": 8, "unmatched_count": 2}
        }
    }
    assert pytest.approx(get_exact_score(cand_8_2), rel=1e-5) == 0.8

    cand_0_10 = {
        "exact_evidence": {
            "total_matched_count": 0,
            "skills": {"matched_count": 0, "unmatched_count": 10}
        }
    }
    assert pytest.approx(get_exact_score(cand_0_10), rel=1e-5) == 0.0

    cand_0_0 = {
        "exact_evidence": {
            "total_matched_count": 0,
            "skills": {"matched_count": 0, "unmatched_count": 0}
        }
    }
    assert get_exact_score(cand_0_0) == 0.0
    assert get_exact_score({}) == 0.0


# ==========================================================
# 4. Final Score Linear Combination Tests
# ==========================================================

def test_final_score_combination():
    candidates = [
        {
            "source_row": 2,
            "name": "Candidate 1",
            "semantic_evidence": {
                "jd_results": [{"document_type": "whole_resume", "score": 0.35}],
                "requirement_results": []
            },
            "exact_evidence": {
                "total_matched_count": 5,
                "skills": {"matched_count": 5, "unmatched_count": 5}
            }
        },
        {
            "source_row": 3,
            "name": "Candidate Min Anchor",
            "semantic_evidence": {"jd_results": [{"document_type": "whole_resume", "score": 0.20}]},
            "exact_evidence": None
        },
        {
            "source_row": 4,
            "name": "Candidate Max Anchor",
            "semantic_evidence": {"jd_results": [{"document_type": "whole_resume", "score": 0.80}]},
            "exact_evidence": None
        }
    ]

    ranked, s_min, s_max = rerank_candidates(candidates, top_k=3)
    cand1 = next(c for c in ranked if c["source_row"] == 2)
    assert pytest.approx(cand1["semantic_normalized"], rel=1e-5) == 0.75
    assert pytest.approx(cand1["exact_score"], rel=1e-5) == 0.50
    assert pytest.approx(cand1["final_score"], rel=1e-5) == 0.70


# ==========================================================
# 5. Ranking Monotonicity Tests
# ==========================================================

def test_ranking_monotonicity_semantic_and_exact():
    cand_a1 = {
        "source_row": 2,
        "name": "A",
        "semantic_evidence": {"jd_results": [{"document_type": "whole_resume", "score": 0.20}]},
        "exact_evidence": {"total_matched_count": 8, "s": {"matched_count": 8, "unmatched_count": 2}}
    }
    cand_b1 = {
        "source_row": 3,
        "name": "B",
        "semantic_evidence": {"jd_results": [{"document_type": "whole_resume", "score": 0.60}]},
        "exact_evidence": {"total_matched_count": 8, "s": {"matched_count": 8, "unmatched_count": 2}}
    }
    ranked1, _, _ = rerank_candidates([cand_a1, cand_b1], top_k=2)
    assert ranked1[0]["name"] == "A"
    assert ranked1[1]["name"] == "B"

    cand_a2 = {
        "source_row": 4,
        "name": "A2",
        "semantic_evidence": {"jd_results": [{"document_type": "whole_resume", "score": 0.50}]},
        "exact_evidence": {"total_matched_count": 9, "s": {"matched_count": 9, "unmatched_count": 1}}
    }
    cand_b2 = {
        "source_row": 5,
        "name": "B2",
        "semantic_evidence": {"jd_results": [{"document_type": "whole_resume", "score": 0.50}]},
        "exact_evidence": {"total_matched_count": 5, "s": {"matched_count": 5, "unmatched_count": 5}}
    }
    ranked2, _, _ = rerank_candidates([cand_a2, cand_b2], top_k=2)
    assert ranked2[0]["name"] == "A2"
    assert ranked2[1]["name"] == "B2"


# ==========================================================
# 6. Top-K Slicing and Preservation
# ==========================================================

def test_top_k_slicing_five_candidates():
    candidates = [
        {
            "source_row": i + 2,
            "name": f"Cand {i}",
            "semantic_evidence": {"jd_results": [{"document_type": "whole_resume", "score": 1.0 - (i * 0.15)}]},
            "exact_evidence": None
        }
        for i in range(5)
    ]
    ranked, _, _ = rerank_candidates(candidates, top_k=3)
    assert len(ranked) == 3
    assert ranked[0]["final_score"] >= ranked[1]["final_score"] >= ranked[2]["final_score"]


# ==========================================================
# 7. Non-Sequential Source Row Preservation
# ==========================================================

def test_non_sequential_source_row_preservation():
    input_rows = [2, 7, 15, 22, 46, 91]
    candidates = [
        {
            "source_row": row_id,
            "name": f"Candidate {row_id}",
            "semantic_evidence": {"jd_results": [{"document_type": "whole_resume", "score": 0.5 + (idx * 0.05)}]},
            "exact_evidence": None
        }
        for idx, row_id in enumerate(input_rows)
    ]
    ranked, _, _ = rerank_candidates(candidates, top_k=6)
    ranked_rows = {c["source_row"] for c in ranked}
    assert ranked_rows == set(input_rows)
    for c in ranked:
        assert c["source_row"] in input_rows


# ==========================================================
# 8. Tie Behavior Tests
# ==========================================================

def test_tie_behavior():
    candidates = [
        {
            "source_row": 10,
            "name": "Tie 1",
            "semantic_evidence": {"jd_results": [{"document_type": "whole_resume", "score": 0.50}]},
            "exact_evidence": {"total_matched_count": 5, "s": {"matched_count": 5, "unmatched_count": 5}}
        },
        {
            "source_row": 20,
            "name": "Tie 2",
            "semantic_evidence": {"jd_results": [{"document_type": "whole_resume", "score": 0.50}]},
            "exact_evidence": {"total_matched_count": 5, "s": {"matched_count": 5, "unmatched_count": 5}}
        },
    ]
    ranked, _, _ = rerank_candidates(candidates, top_k=2)
    assert len(ranked) == 2
    assert ranked[0]["final_score"] == ranked[1]["final_score"]
    assert {c["source_row"] for c in ranked} == {10, 20}


# ==========================================================
# 9. Score Range Invariants
# ==========================================================

def test_score_range_invariants():
    test_scores = [0.0, 0.25, 0.5, 0.75, 1.0]
    candidates = [
        {
            "source_row": i + 2,
            "name": f"Cand {i}",
            "semantic_evidence": {"jd_results": [{"document_type": "whole_resume", "score": score}]},
            "exact_evidence": {"total_matched_count": int(score * 10), "s": {"matched_count": int(score * 10), "unmatched_count": int((1 - score) * 10)}}
        }
        for i, score in enumerate(test_scores)
    ]
    ranked, _, _ = rerank_candidates(candidates, top_k=len(candidates))
    for c in ranked:
        assert 0.0 <= c["exact_score"] <= 1.0
        assert 0.0 <= c["semantic_normalized"] <= 1.0
        assert 0.0 <= c["final_score"] <= 1.0


# ==========================================================
# 10. Cohort Normalization Dependency Test
# ==========================================================

def test_cohort_normalization_dependency():
    norm_cohort_a = normalize_semantic_score(score=0.5, semantic_min=0.2, semantic_max=0.8)
    norm_cohort_b = normalize_semantic_score(score=0.5, semantic_min=0.2, semantic_max=0.5)

    assert pytest.approx(norm_cohort_a, rel=1e-5) == 0.50
    assert pytest.approx(norm_cohort_b, rel=1e-5) == 0.00
    assert norm_cohort_a != norm_cohort_b
