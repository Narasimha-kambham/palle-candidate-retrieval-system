import json
from pathlib import Path


def save_resume_texts(results, output_path="data/processed/resumes.json"):

    path = Path(output_path)

    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(
            results,
            file,
            ensure_ascii=False,
            indent=4
        )

    print(f"Saved resume results to: {path}")


def load_resume_texts(input_path="data/processed/resumes.json"):

    path = Path(input_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Resume text file not found: {path}"
        )

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:
        return json.load(file)