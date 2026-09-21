from urllib.parse import urlparse
import os
import requests


def download_resume(url, output_path):
    response = requests.get(url)
    response.raise_for_status()

    with open(output_path, "wb") as file:
        file.write(response.content)


def download_all_resumes(candidates):

    os.makedirs("data/resumes", exist_ok=True)

    results = []

    for candidate in candidates:

        resume_url = candidate["resume_path"]

        if resume_url is None:
            result = {
                "source_row": candidate["source_row"],
                "name": candidate["name"],
                "resume_url": None,
                "local_path": None,
                "status": "missing_resume_url",
                "error": "Resume path is empty in source Excel"
            }

            results.append(result)
            continue

        parsed_url = urlparse(resume_url)
        filename = os.path.basename(parsed_url.path)

        output_path = os.path.join("data", "resumes", filename)

        result = {
            "source_row": candidate["source_row"],
            "name": candidate["name"],
            "resume_url": resume_url,
            "local_path": output_path,
            "status": None,
            "error": None
        }

        if os.path.exists(output_path):
            result["status"] = "already_exists"
            results.append(result)
            continue

        try:
            download_resume(
                url=resume_url,
                output_path=output_path
            )

            result["status"] = "downloaded"

        except requests.RequestException as e:
            result["status"] = "download_failed"
            result["error"] = str(e)

        results.append(result)

    return results

