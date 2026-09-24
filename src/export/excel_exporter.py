import os
import pandas as pd


def export_ranked_candidates(
    input_excel,
    output_excel,
    ranked_candidates,
    downloaded_records=None,
    resumes=None
):
    df = pd.read_excel(input_excel)

    # --------------------------------------------------
    # Sheet 1: Primary Result Sheet (Ranked Candidates)
    # --------------------------------------------------
    rows = []

    for rank, candidate in enumerate(
        ranked_candidates,
        start=1
    ):
        source_row = candidate["source_row"]

        row_index = source_row - 2

        if row_index < 0 or row_index >= len(df):
            continue

        row = df.iloc[row_index].copy()

        row["Rank"] = rank
        row["Final Score"] = candidate["final_score"]
        row["Semantic Score"] = candidate["semantic_score"]
        row["Semantic Normalized"] = candidate[
            "semantic_normalized"
        ]
        row["Exact Score"] = candidate["exact_score"]
        row["Whole Resume Score"] = candidate.get(
            "whole_resume_score"
        )
        row["Best Chunk Score"] = candidate.get(
            "best_chunk_score"
        )
        row["Best Requirement Score"] = candidate.get(
            "best_requirement_score"
        )

        rows.append(row)

    output_df = pd.DataFrame(rows)

    os.makedirs(
        os.path.dirname(output_excel),
        exist_ok=True
    )

    # --------------------------------------------------
    # Sheet 2: Processing Status (Audit / Tracking Sheet)
    # --------------------------------------------------
    downloads_by_row = {
        record["source_row"]: record
        for record in (downloaded_records or [])
        if "source_row" in record
    }

    parses_by_row = {
        record["source_row"]: record
        for record in (resumes or [])
        if "source_row" in record
    }

    selected_source_rows = {
        candidate["source_row"]
        for candidate in ranked_candidates
    }

    status_rows = []

    for index, row in df.iterrows():
        source_row = index + 2

        download_rec = downloads_by_row.get(source_row)
        parse_rec = parses_by_row.get(source_row)

        if download_rec is not None:
            download_status = download_rec.get("status") or ""
            download_error = download_rec.get("error") or ""
        else:
            download_status = ""
            download_error = ""

        if parse_rec is not None:
            parse_status = parse_rec.get("status") or ""
            parse_error = parse_rec.get("error") or ""
        else:
            parse_status = ""
            parse_error = ""

        if download_status == "missing_resume_url":
            final_status = "skipped"
        elif download_status == "download_failed":
            final_status = "failed"
        elif parse_status == "text_extraction_failed":
            final_status = "failed"
        elif parse_status == "text_extracted":
            if source_row in selected_source_rows:
                final_status = "selected"
            else:
                final_status = "processed_not_selected"
        elif parse_status == "skipped":
            # Only resolve this using the authoritative download result.
            if download_status == "missing_resume_url":
                final_status = "skipped"
            elif download_status == "download_failed":
                final_status = "failed"
            else:
                final_status = "skipped"
        else:
            final_status = ""

        name = row.get("Name")
        resume_path = row.get("Resume Path")

        status_rows.append({
            "Source Row": source_row,
            "Name": None if pd.isna(name) else str(name).strip(),
            "Resume Path": None if pd.isna(resume_path) else str(resume_path).strip(),
            "Download Status": download_status,
            "Download Error": download_error,
            "Parse Status": parse_status,
            "Parse Error": parse_error,
            "Final Status": final_status,
        })

    status_df = pd.DataFrame(status_rows)

    with pd.ExcelWriter(output_excel, engine="openpyxl") as writer:
        output_df.to_excel(
            writer,
            sheet_name="Ranked Candidates",
            index=False
        )
        status_df.to_excel(
            writer,
            sheet_name="Processing Status",
            index=False
        )

    return output_df


if __name__ == "__main__":
    from pathlib import Path

    input_excel = "data/runs/test_job/input/Tracker.xlsx"
    output_excel = "data/runs/test_job/output/ranked_candidates.xlsx"

    output_excel_path = Path(output_excel)
    output_excel_path.parent.mkdir(parents=True, exist_ok=True)

    test_candidates = [
        {
            "source_row": 22,
            "name": "Sudharshan Reddy Kuluru",
            "final_score": 0.8471,
            "semantic_score": 0.6764,
            "semantic_normalized": 1.0,
            "exact_score": 0.2353,
            "whole_resume_score": 0.6017,
            "best_chunk_score": 0.6257,
            "best_requirement_score": 0.8187,
        },
        {
            "source_row": 46,
            "name": "shrishail y uppar",
            "final_score": 0.8259,
            "semantic_score": 0.6811,
            "semantic_normalized": 0.9931,
            "exact_score": 0.1569,
            "whole_resume_score": 0.6181,
            "best_chunk_score": 0.5906,
            "best_requirement_score": 0.8649,
        },
    ]

    result = export_ranked_candidates(
        input_excel=input_excel,
        output_excel=output_excel,
        ranked_candidates=test_candidates
    )

    print("=" * 80)
    print("EXCEL EXPORT TEST")
    print("=" * 80)
    print(f"Input  : {input_excel}")
    print(f"Output : {output_excel}")
    print(f"Rows exported: {len(result)}")
    print("=" * 80)