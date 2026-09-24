def retrieve_exact_matches(
    resumes,
    jd_requirements,
    k=30
):

    results = []

    # List of tuples: (requirement_type: str, requirement: SearchableRequirement)
    requirements = []

    # --------------------------------------------------
    # Collect all searchable requirements
    # --------------------------------------------------

    for requirement in jd_requirements.required_skills:
        requirements.append(
            ("required_skills", requirement)
        )

    for requirement in jd_requirements.preferred_skills:
        requirements.append(
            ("preferred_skills", requirement)
        )

    for requirement in jd_requirements.experience_requirements:
        requirements.append(
            ("experience_requirements", requirement)
        )

    for requirement in jd_requirements.education_requirements:
        requirements.append(
            ("education_requirements", requirement)
        )

    for requirement in jd_requirements.other_requirements:
        requirements.append(
            ("other_requirements", requirement)
        )

    # --------------------------------------------------
    # Check each resume
    # --------------------------------------------------

    # Iterate through each candidate resume (list of dicts loaded from resumes.json)
    for resume in resumes:

        if resume["status"] != "text_extracted":
            continue

        resume_text = resume["text"]

        if not resume_text:
            continue

        resume_text_lower = resume_text.lower()

        candidate = {
            "source_row": resume["source_row"],
            "name": resume["name"],
            "resume_url": resume["resume_url"],
            "local_path": resume["local_path"],
            "retrieval_type": "exact",

            "required_skills": {
                "matched_terms": [],
                "unmatched_terms": [],
                "matched_count": 0,
                "unmatched_count": 0
            },

            "preferred_skills": {
                "matched_terms": [],
                "unmatched_terms": [],
                "matched_count": 0,
                "unmatched_count": 0
            },

            "experience_requirements": {
                "matched_terms": [],
                "unmatched_terms": [],
                "matched_count": 0,
                "unmatched_count": 0
            },

            "education_requirements": {
                "matched_terms": [],
                "unmatched_terms": [],
                "matched_count": 0,
                "unmatched_count": 0
            },

            "other_requirements": {
                "matched_terms": [],
                "unmatched_terms": [],
                "matched_count": 0,
                "unmatched_count": 0
            }
        }

        # --------------------------------------------------
        # Match searchable terms
        # --------------------------------------------------

        # requirement is a SearchableRequirement object containing original_requirement (str) and search_terms (list[str])
        for requirement_type, requirement in requirements:

            for term in requirement.search_terms:

                term_lower = term.lower()

                if term_lower in resume_text_lower:

                    # Avoid duplicate matched terms
                    if not any(
                        existing.lower() == term_lower
                        for existing in candidate[requirement_type]["matched_terms"]
                    ):
                        candidate[requirement_type]["matched_terms"].append(
                            term
                        )

                else:

                    # Avoid duplicate unmatched terms
                    if not any(
                        existing.lower() == term_lower
                        for existing in candidate[requirement_type]["unmatched_terms"]
                    ):
                        candidate[requirement_type]["unmatched_terms"].append(
                            term
                        )

        # --------------------------------------------------
        # Calculate counts
        # --------------------------------------------------

        requirement_types = [
            "required_skills",
            "preferred_skills",
            "experience_requirements",
            "education_requirements",
            "other_requirements"
        ]

        for requirement_type in requirement_types:

            candidate[requirement_type]["matched_count"] = len(
                candidate[requirement_type]["matched_terms"]
            )

            candidate[requirement_type]["unmatched_count"] = len(
                candidate[requirement_type]["unmatched_terms"]
            )

        # --------------------------------------------------
        # Total exact matches
        # --------------------------------------------------

        candidate["total_matched_count"] = sum(
            candidate[requirement_type]["matched_count"]
            for requirement_type in requirement_types
        )

        results.append(candidate)

    # --------------------------------------------------
    # Rank candidates by exact matches
    # --------------------------------------------------

    results.sort(
        key=lambda candidate: candidate["total_matched_count"],
        reverse=True
    )

    # Return top-k exact candidates
    return results[:k]