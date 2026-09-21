from pydantic import BaseModel, Field
from src.llm.llm_executor import LLMExecutor

class SearchableRequirement(BaseModel):
    original_requirement: str = Field(
        description="The requirement faithfully extracted from the job description while preserving its original meaning"
    )
    search_terms: list[str] = Field(
        description="Conservative searchable concepts explicitly supported by the requirement"
    )

class JDRequirements(BaseModel):
    required_skills: list[SearchableRequirement] = Field(
        description="Mandatory technical skills explicitly required by the job description"
    )

    preferred_skills: list[SearchableRequirement] = Field(
        description="Preferred, optional, nice-to-have, or bonus technical skills"
    )

    experience_requirements: list[SearchableRequirement] = Field(
        description="Explicit experience, seniority, or fresher requirements"
    )

    education_requirements: list[SearchableRequirement] = Field(
        description="Explicit educational qualifications or degree requirements"
    )

    other_requirements: list[SearchableRequirement] = Field(
        description="Other explicit candidate requirements relevant to evaluating candidates"
    )

def extract_requirements(jd_text: str):

    prompt = f"""
        You are an information extraction system for a candidate retrieval system.

        Your task is to analyze the provided Job Description and extract the
        requirements that should be used to evaluate and retrieve candidates.

        For every extracted requirement, provide:
        1. original_requirement
        2. search_terms

        The original requirement should preserve the meaning of the requirement
        as stated in the Job Description.

        The search_terms should contain concise, searchable concepts that are
        explicitly supported by that requirement.

        ==================================================
        CATEGORIES
        ==================================================

        1. required_skills
        Technical skills, programming languages, frameworks, tools, technologies,
        platforms, or technical knowledge that the candidate is explicitly required
        or expected to have.

        2. preferred_skills
        Skills, technologies, tools, or knowledge explicitly described as preferred,
        nice-to-have, bonus, plus, or advantageous.

        3. experience_requirements
        Explicit requirements concerning years of experience, seniority, fresher
        status, recent graduates, or prior professional experience.

        4. education_requirements
        Explicit degree, educational qualification, academic background, or field
        of study requirements.

        5. other_requirements
        Other explicit candidate requirements that are relevant when evaluating
        a candidate and do not belong to the categories above.

        Do not include generic company descriptions or marketing statements.

        ==================================================
        SEARCH TERM RULES
        ==================================================
        - Prefer meaningful technical concepts over isolated generic words.
        - Avoid overly broad terms such as "tables", "rows", "storage", "queries",
        "technology", or "development" unless they are sufficiently specific in context.
        - A search term should provide useful signal when matching a candidate resume.
        - Do not create a search term merely because it appears as an individual word
        in the requirement.

        Generate search terms conservatively.

        A search term MUST be supported by the original requirement or explicitly
        stated in the Job Description.

        DO NOT invent technologies, frameworks, tools, vendors, certifications,
        synonyms, or related concepts that are not supported by the JD.

        For example:

        Requirement:
        "Working knowledge of building applications (React, Node.js, or similar)"

        Good search_terms:
        ["React", "Node.js", "application development"]

        Do NOT generate:
        ["Angular", "Vue", "Express", "MongoDB"]

        because those technologies were not explicitly mentioned.

        Another example:

        Requirement:
        "Basic understanding of cloud concepts (hosting, deployment, storage)"

        Good search_terms:
        ["cloud concepts", "hosting", "deployment", "storage"]

        Do NOT automatically generate:
        ["AWS", "Azure", "GCP"]

        unless those technologies are explicitly mentioned.

        ==================================================
        IMPORTANT RULES
        ==================================================

        - Extract only requirements supported by the JD.
        - Do not invent requirements.
        - Do not infer unstated qualifications.
        - Do not move required skills into preferred skills.
        - Do not move preferred skills into required skills.
        - Preserve important alternatives such as "React, Node.js, or similar".
        - Do not duplicate the same requirement unnecessarily.
        - Keep search_terms concise.
        - If a category has no requirements, return an empty list.
        - Do not treat general company culture or promotional language as a
        candidate requirement.
        - Do not convert vague personality descriptions into technical skills.
        - Search terms are for candidate retrieval, so they should be useful
        concepts rather than long sentences.

        ==================================================
        JOB DESCRIPTION
        ==================================================

        {jd_text}
    """
    return LLMExecutor.invoke_structured(
        prompt,
        JDRequirements
    )

if __name__ == "__main__":
    from src.ingestion.document_text_extractor import extract_text_from_pdf
    import json

    jd_text = extract_text_from_pdf("data/JD_Forward Deployed Engineer Intern (6 months -Paid).pdf")
    requirements = extract_requirements(jd_text)

    print(json.dumps(
        requirements.model_dump(),
        indent=4
    ))