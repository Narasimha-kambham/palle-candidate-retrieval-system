import os
import tempfile
import pandas as pd
import pytest

from src.export.excel_exporter import export_ranked_candidates


def test_excel_status_processing_canonical_cases():
    """
    Validates the 5 canonical processing status cases on Sheet 2 and
    the Top-K selection on Sheet 1 using synthetic stage records.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        input_excel = os.path.join(temp_dir, "test_tracker.xlsx")
        output_excel = os.path.join(temp_dir, "test_ranked_candidates.xlsx")

        # 1. Create temporary input Excel with 5 candidates (rows 2 to 6)
        input_data = [
            {"Name": "Candidate 1", "Resume Path": None, "Email": "c1@test.com"},
            {"Name": "Candidate 2", "Resume Path": "https://example.com/broken.pdf", "Email": "c2@test.com"},
            {"Name": "Candidate 3", "Resume Path": "https://example.com/empty.pdf", "Email": "c3@test.com"},
            {"Name": "Candidate 4", "Resume Path": "https://example.com/good1.pdf", "Email": "c4@test.com"},
            {"Name": "Candidate 5", "Resume Path": "https://example.com/good2.pdf", "Email": "c5@test.com"},
        ]
        df_input = pd.DataFrame(input_data)
        df_input.to_excel(input_excel, index=False)

        # 2. Authoritative downloaded_records
        downloaded_records = [
            {
                "source_row": 2,
                "name": "Candidate 1",
                "resume_url": None,
                "local_path": None,
                "status": "missing_resume_url",
                "error": "Resume path is empty in source Excel"
            },
            {
                "source_row": 3,
                "name": "Candidate 2",
                "resume_url": "https://example.com/broken.pdf",
                "local_path": None,
                "status": "download_failed",
                "error": "Connection timeout"
            },
            {
                "source_row": 4,
                "name": "Candidate 3",
                "resume_url": "https://example.com/empty.pdf",
                "local_path": "data/resumes/empty.pdf",
                "status": "downloaded",
                "error": None
            },
            {
                "source_row": 5,
                "name": "Candidate 4",
                "resume_url": "https://example.com/good1.pdf",
                "local_path": "data/resumes/good1.pdf",
                "status": "already_exists",
                "error": None
            },
            {
                "source_row": 6,
                "name": "Candidate 5",
                "resume_url": "https://example.com/good2.pdf",
                "local_path": "data/resumes/good2.pdf",
                "status": "downloaded",
                "error": None
            },
        ]

        # 3. Authoritative resumes (Text Extraction)
        resumes = [
            {
                "source_row": 2,
                "name": "Candidate 1",
                "status": "skipped",
                "error": "Resume download status: missing_resume_url"
            },
            {
                "source_row": 3,
                "name": "Candidate 2",
                "status": "skipped",
                "error": "Resume download status: download_failed"
            },
            {
                "source_row": 4,
                "name": "Candidate 3",
                "status": "text_extraction_failed",
                "text": None,
                "error": "Resume contains no extractable text"
            },
            {
                "source_row": 5,
                "name": "Candidate 4",
                "status": "text_extracted",
                "text": "Python Django AWS SQL",
                "error": None
            },
            {
                "source_row": 6,
                "name": "Candidate 5",
                "status": "text_extracted",
                "text": "Java Spring SQL",
                "error": None
            },
        ]

        # 4. Authoritative ranked_candidates (Top-K only includes source_row 5)
        ranked_candidates = [
            {
                "source_row": 5,
                "name": "Candidate 4",
                "final_score": 0.95,
                "semantic_score": 0.90,
                "semantic_normalized": 1.0,
                "exact_score": 0.80,
                "whole_resume_score": 0.90,
                "best_chunk_score": 0.92,
                "best_requirement_score": 0.91,
            }
        ]

        # 5. Call exporter
        export_ranked_candidates(
            input_excel=input_excel,
            output_excel=output_excel,
            ranked_candidates=ranked_candidates,
            downloaded_records=downloaded_records,
            resumes=resumes
        )

        # 6. Read back both sheets
        sheet1_df = pd.read_excel(output_excel, sheet_name="Ranked Candidates")
        sheet2_df = pd.read_excel(output_excel, sheet_name="Processing Status")

        # Assertion 1: Sheet 1 contains exactly 1 row
        assert len(sheet1_df) == 1

        # Assertion 2: Sheet 2 contains exactly 5 rows
        assert len(sheet2_df) == 5

        # Assertion 3: Sheet 1 contains Candidate 4 / source row 5
        assert sheet1_df.iloc[0]["Name"] == "Candidate 4"
        assert sheet1_df.iloc[0]["Rank"] == 1
        assert sheet1_df.iloc[0]["Final Score"] == 0.95

        # Assertion 4: Sheet 2 exact columns
        expected_columns = [
            "Source Row",
            "Name",
            "Resume Path",
            "Download Status",
            "Download Error",
            "Parse Status",
            "Parse Error",
            "Final Status",
        ]
        assert list(sheet2_df.columns) == expected_columns

        # Convert sheet 2 to dict keyed by source_row for precise inspection
        # Fill NaN with empty string for clean error/path assertions
        sheet2_clean = sheet2_df.fillna("").to_dict(orient="records")
        status_by_row = {row["Source Row"]: row for row in sheet2_clean}

        # Assertion 5: Verify all 5 canonical cases individually
        # Case 1: Missing Resume URL
        row2 = status_by_row[2]
        assert row2["Name"] == "Candidate 1"
        assert row2["Download Status"] == "missing_resume_url"
        assert row2["Download Error"] == "Resume path is empty in source Excel"
        assert row2["Parse Status"] == "skipped"
        assert row2["Parse Error"] == "Resume download status: missing_resume_url"
        assert row2["Final Status"] == "skipped"

        # Case 2: Download Failed
        row3 = status_by_row[3]
        assert row3["Name"] == "Candidate 2"
        assert row3["Download Status"] == "download_failed"
        assert row3["Download Error"] == "Connection timeout"
        assert row3["Parse Status"] == "skipped"
        assert row3["Parse Error"] == "Resume download status: download_failed"
        assert row3["Final Status"] == "failed"

        # Case 3: Text Extraction Failed
        row4 = status_by_row[4]
        assert row4["Name"] == "Candidate 3"
        assert row4["Download Status"] == "downloaded"
        assert row4["Download Error"] == ""
        assert row4["Parse Status"] == "text_extraction_failed"
        assert row4["Parse Error"] == "Resume contains no extractable text"
        assert row4["Final Status"] == "failed"

        # Case 4: Text Extracted + Selected
        row5 = status_by_row[5]
        assert row5["Name"] == "Candidate 4"
        assert row5["Download Status"] == "already_exists"
        assert row5["Download Error"] == ""
        assert row5["Parse Status"] == "text_extracted"
        assert row5["Parse Error"] == ""
        assert row5["Final Status"] == "selected"

        # Case 5: Text Extracted + Processed Not Selected
        row6 = status_by_row[6]
        assert row6["Name"] == "Candidate 5"
        assert row6["Download Status"] == "downloaded"
        assert row6["Download Error"] == ""
        assert row6["Parse Status"] == "text_extracted"
        assert row6["Parse Error"] == ""
        assert row6["Final Status"] == "processed_not_selected"

        # Assertion 6: Zero occurrences of fabricated statuses
        forbidden_terms = ["not_attempted", "not_tracked", "embedded", "evaluated"]
        for term in forbidden_terms:
            assert not (sheet2_df == term).any().any(), f"Found forbidden term '{term}' in Sheet 2"

        # Assertion 7: No Embedding/Matching columns exist
        forbidden_cols = ["Embedding Status", "Embedding Error", "Matching Status", "Matching Error"]
        for col in forbidden_cols:
            assert col not in sheet2_df.columns, f"Found forbidden column '{col}' in Sheet 2"


def test_excel_status_missing_stage_records_edge_case():
    """
    Validates that when stage records are absent/unavailable,
    the exporter produces empty strings without fabricating placeholder statuses.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        input_excel = os.path.join(temp_dir, "test_incomplete_tracker.xlsx")
        output_excel = os.path.join(temp_dir, "test_incomplete_ranked.xlsx")

        input_data = [
            {"Name": "Candidate Incomplete", "Resume Path": "https://example.com/inc.pdf"},
        ]
        pd.DataFrame(input_data).to_excel(input_excel, index=False)

        # Pass empty stage records
        export_ranked_candidates(
            input_excel=input_excel,
            output_excel=output_excel,
            ranked_candidates=[],
            downloaded_records=[],
            resumes=[]
        )

        sheet2_df = pd.read_excel(output_excel, sheet_name="Processing Status")
        assert len(sheet2_df) == 1

        sheet2_clean = sheet2_df.fillna("").to_dict(orient="records")[0]
        assert sheet2_clean["Source Row"] == 2
        assert sheet2_clean["Name"] == "Candidate Incomplete"
        assert sheet2_clean["Download Status"] == ""
        assert sheet2_clean["Download Error"] == ""
        assert sheet2_clean["Parse Status"] == ""
        assert sheet2_clean["Parse Error"] == ""
        assert sheet2_clean["Final Status"] == ""

