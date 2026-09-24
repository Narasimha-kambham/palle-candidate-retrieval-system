from src.ingestion.document_text_extractor import extract_document_text

def extract_resume_text(file_path):
    text = extract_document_text(filepath=file_path)

    if not text.strip():
        raise ValueError("Resume contains no extractable text")

    return text

def extract_all_resume_texts(resume_records):

    results = []

    for record in resume_records:

        result = {
            "source_row": record["source_row"],
            "name": record["name"],
            "resume_url": record["resume_url"],
            "local_path": record["local_path"],
            "status": None,
            "text": None,
            "error": None
        }

        # Only process successfully downloaded resumes
        if record["status"] not in ("downloaded", "already_exists"):
            result["status"] = "skipped"
            result["error"] = (
                f"Resume download status: {record['status']}"
            )
            results.append(result)
            continue

        try:
            text = extract_resume_text(record["local_path"])

            result["text"] = text
            result["status"] = "text_extracted"

        except Exception as e:
            result["status"] = "text_extraction_failed"
            result["error"] = str(e)

        results.append(result)

    return results

if __name__ == "__main__":

    pdf_path = "data/runs/test_job/resumes/25659.pdf"
    docx_path = "data/runs/test_job/resumes/25779.docx"

    pdf_text = extract_resume_text(pdf_path)
    print(pdf_text[:1000])

    docx_text = extract_resume_text(docx_path)
    print(docx_text[:1000])