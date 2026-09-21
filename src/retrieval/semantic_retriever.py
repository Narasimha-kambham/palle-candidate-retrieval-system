from src.ingestion.document_text_extractor import extract_text_from_pdf
from src.retrieval.resume_vector_store import (
    create_embedding_model,
    get_or_create_vector_store,
)
from src.processing.jd_requirements import extract_requirements


VECTOR_STORE_PATH = "data/vector_store/resumes"
JD_PATH = "data/JD_Forward Deployed Engineer Intern (6 months -Paid).pdf"


def retrieve_by_jd(
    vector_store,
    jd_text,
    k=20
):
    """
    Perform semantic retrieval using the complete JD.
    """

    results = vector_store.similarity_search_with_score(
        jd_text,
        k=k
    )

    retrieval_results = []

    for document, score in results:

        metadata = document.metadata

        retrieval_results.append({
            "candidate_id": metadata.get("source_row"),
            "name": metadata.get("name"),

            "retrieval_type": "jd_semantic",

            "document_type": metadata.get(
                "document_type"
            ),

            "chunk_id": metadata.get(
                "chunk_id"
            ),

            "score": float(score),

            "resume_url": metadata.get(
                "resume_url"
            ),

            "local_path": metadata.get(
                "local_path"
            ),

            "query": jd_text,

            "text": document.page_content
        })

    return retrieval_results


def retrieve_by_requirements(
    vector_store,
    jd_requirements,
    k=10
):
    """
    Perform semantic retrieval for every extracted JD
    requirement.
    """

    retrieval_results = []

    requirement_groups = [
        (
            "required_skills",
            jd_requirements.required_skills
        ),
        (
            "preferred_skills",
            jd_requirements.preferred_skills
        ),
        (
            "experience_requirements",
            jd_requirements.experience_requirements
        ),
        (
            "education_requirements",
            jd_requirements.education_requirements
        ),
        (
            "other_requirements",
            jd_requirements.other_requirements
        )
    ]

    for requirement_type, requirements in requirement_groups:

        for requirement in requirements:

            original_requirement = (
                requirement.original_requirement
            )

            search_terms = (
                requirement.search_terms
            )

            # Use the original requirement as the
            # semantic query.
            query = original_requirement

            # --------------------------------------------------
            # Semantic retrieval
            # --------------------------------------------------

            results = vector_store.similarity_search_with_score(
                query,
                k=k
            )

            for document, score in results:

                metadata = document.metadata

                retrieval_results.append({
                    "candidate_id": metadata.get(
                        "source_row"
                    ),

                    "name": metadata.get(
                        "name"
                    ),

                    "retrieval_type":
                        "requirement_semantic",

                    "requirement_type":
                        requirement_type,

                    "requirement":
                        original_requirement,

                    "search_terms":
                        search_terms,

                    "document_type":
                        metadata.get(
                            "document_type"
                        ),

                    "chunk_id":
                        metadata.get(
                            "chunk_id"
                        ),

                    "score":
                        float(score),

                    "resume_url":
                        metadata.get(
                            "resume_url"
                        ),

                    "local_path":
                        metadata.get(
                            "local_path"
                        ),

                    "query":
                        query,

                    "text":
                        document.page_content
                })

    return retrieval_results


def retrieve_semantically(
    vector_store,
    jd_text,
    jd_requirements,
    jd_k=20,
    requirement_k=10
):
    """
    Run both semantic retrieval strategies.

    1. Whole JD semantic retrieval
    2. Requirement-level semantic retrieval

    Results are intentionally not deduplicated here.
    """

    jd_results = retrieve_by_jd(
        vector_store=vector_store,
        jd_text=jd_text,
        k=jd_k
    )

    requirement_results = retrieve_by_requirements(
        vector_store=vector_store,
        jd_requirements=jd_requirements,
        k=requirement_k
    )

    return {
        "jd_results": jd_results,
        "requirement_results": requirement_results
    }

