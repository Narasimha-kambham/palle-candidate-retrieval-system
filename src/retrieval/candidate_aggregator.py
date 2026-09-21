def aggregate_candidates(
    semantic_results,
    exact_results
):

    candidates = {}

    # --------------------------------------------------
    # Add whole-JD semantic results
    # --------------------------------------------------

    for result in semantic_results["jd_results"]:

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

        candidates[candidate_id]["semantic_evidence"][
            "jd_results"
        ].append(result)

    # --------------------------------------------------
    # Add requirement-level semantic results
    # --------------------------------------------------

    for result in semantic_results["requirement_results"]:

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

        candidates[candidate_id]["semantic_evidence"][
            "requirement_results"
        ].append(result)

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


# ==========================================================
# TEST
# ==========================================================

if __name__ == "__main__":

    from src.ingestion.resume_text_store import load_resume_texts
    from src.ingestion.document_text_extractor import (
        extract_text_from_pdf
    )

    from src.processing.jd_requirements import (
        extract_requirements
    )

    from src.retrieval.resume_vector_store import (
        create_embedding_model,
        get_or_create_vector_store
    )

    from src.retrieval.semantic_retriever import (
        retrieve_semantically
    )

    from src.retrieval.exact_retriever import (
        retrieve_exact_matches
    )

    # --------------------------------------------------
    # Paths
    # --------------------------------------------------

    VECTOR_STORE_PATH = "data/vector_store/resumes"

    JD_PATH = (
        "data/"
        "JD_Forward Deployed Engineer Intern "
        "(6 months -Paid).pdf"
    )

    # --------------------------------------------------
    # Load resumes
    # --------------------------------------------------

    resumes = load_resume_texts(
        "data/processed/resumes.json"
    )

    # --------------------------------------------------
    # Load JD
    # --------------------------------------------------

    jd_text = extract_text_from_pdf(
        JD_PATH
    )

    # --------------------------------------------------
    # Extract JD requirements
    # --------------------------------------------------

    jd_requirements = extract_requirements(
        jd_text
    )

    # --------------------------------------------------
    # Load embedding model
    # --------------------------------------------------

    embeddings = create_embedding_model()

    # --------------------------------------------------
    # Load existing FAISS store
    # --------------------------------------------------

    vector_store = get_or_create_vector_store(
        VECTOR_STORE_PATH,
        embeddings,
        []
    )

    # --------------------------------------------------
    # Semantic retrieval
    # --------------------------------------------------

    semantic_results = retrieve_semantically(
        vector_store,
        jd_text,
        jd_requirements
    )

    # --------------------------------------------------
    # Exact retrieval
    # --------------------------------------------------

    exact_results = retrieve_exact_matches(
        resumes,
        jd_requirements,
        k=30
    )

    # --------------------------------------------------
    # Aggregate
    # --------------------------------------------------

    candidates = aggregate_candidates(
        semantic_results,
        exact_results
    )

    # --------------------------------------------------
    # Test output
    # --------------------------------------------------

    print("=" * 100)
    print("CANDIDATE AGGREGATION")
    print("=" * 100)

    print(
        f"Whole JD results       : "
        f"{len(semantic_results['jd_results'])}"
    )

    print(
        f"Requirement results    : "
        f"{len(semantic_results['requirement_results'])}"
    )

    print(
        f"Exact candidates       : "
        f"{len(exact_results)}"
    )

    print(
        f"Unique candidates      : "
        f"{len(candidates)}"
    )

    print("\nTOP CANDIDATES")
    print("-" * 100)

    for index, candidate in enumerate(
        candidates[:20],
        start=1
    ):

        semantic = candidate["semantic_evidence"]

        print(
            f"{index}. "
            f"{candidate['name']} "
            f"| row={candidate['source_row']} "
            f"| JD semantic="
            f"{len(semantic['jd_results'])} "
            f"| requirement semantic="
            f"{len(semantic['requirement_results'])} "
            f"| exact="
            f"{candidate['exact_evidence'] is not None}"
        )

        import json

    print(
        json.dumps(
            candidates[0],
            indent=4,
            ensure_ascii=False
        )
    )