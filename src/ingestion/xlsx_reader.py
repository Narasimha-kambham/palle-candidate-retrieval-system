import pandas as pd

def load_candidates(file_path):

    # Palle Technologies uses a fixed XLSX template.
    # The header is expected to be in the first row.  
    df = pd.read_excel(file_path)

    required_columns = ["Name", "Resume Path"]

    missing_columns = [
        column for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    candidates = []

    for index, row in df.iterrows():
        name = row['Name']
        resume_path =  row['Resume Path']
        candidates.append({
            "source_row": index + 2,
            "name": None if pd.isna(name) else str(name).strip(),
            "resume_path": None if pd.isna(resume_path) else str(resume_path).strip()
        })

    return candidates


if __name__ == "__main__":
    import os
    from .resume_downloader import download_all_resumes
    from .resume_text_extractor import extract_all_resume_texts
    from .resume_text_store import load_resume_texts, save_resume_texts

    print("Current working directory:", os.getcwd())
    print("This Python file:", __file__)

    candidates = load_candidates("data/Tracker.xlsx")

    download_results = download_all_resumes(candidates)

    text_results = extract_all_resume_texts(download_results)

    save_resume_texts(text_results)