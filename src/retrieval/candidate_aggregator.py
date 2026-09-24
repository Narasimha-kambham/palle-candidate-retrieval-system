def aggregate_candidates(
    semantic_results,
    exact_results
):
    """
    Aggregate candidate matches from semantic retrieval and exact keyword matching
    into a unified per-candidate structure keyed by source_row.
    """
    candidates = {}

    # --------------------------------------------------
    # Add whole-JD semantic results
    # --------------------------------------------------
    for result in semantic_results.get("jd_results", []):
        candidate_id = result["candidate_id"]

        if candidate_id not in candidates:
            candidates[candidate_id] = {
                "source_row": candidate_id,
                "name": result["name"],
                "resume_url": result["resume_url"],
                "local_path": result["local_path"],
                "semantic_evidence": {
                    "jd_results": [],
                    "requirement_results": []
                },
                "exact_evidence": None
            }

        candidates[candidate_id]["semantic_evidence"]["jd_results"].append(result)

    # --------------------------------------------------
    # Add requirement-level semantic results
    # --------------------------------------------------
    for result in semantic_results.get("requirement_results", []):
        candidate_id = result["candidate_id"]

        if candidate_id not in candidates:
            candidates[candidate_id] = {
                "source_row": candidate_id,
                "name": result["name"],
                "resume_url": result["resume_url"],
                "local_path": result["local_path"],
                "semantic_evidence": {
                    "jd_results": [],
                    "requirement_results": []
                },
                "exact_evidence": None
            }

        candidates[candidate_id]["semantic_evidence"]["requirement_results"].append(result)

    # --------------------------------------------------
    # Add exact retrieval results
    # --------------------------------------------------
    for result in exact_results:
        candidate_id = result["source_row"]

        if candidate_id not in candidates:
            candidates[candidate_id] = {
                "source_row": candidate_id,
                "name": result["name"],
                "resume_url": result["resume_url"],
                "local_path": result["local_path"],
                "semantic_evidence": {
                    "jd_results": [],
                    "requirement_results": []
                },
                "exact_evidence": None
            }

        candidates[candidate_id]["exact_evidence"] = result

    return sorted(
        candidates.values(),
        key=lambda x: x["source_row"]
    )
