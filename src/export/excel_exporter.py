import os
import pandas as pd


def export_ranked_candidates(
    input_excel,
    output_excel,
    ranked_candidates
):
    df = pd.read_excel(input_excel)

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

    output_df.to_excel(
        output_excel,
        index=False
    )

    return output_df


if __name__ == "__main__":
    from pathlib import Path

    input_excel = "data/input/Tracker.xlsx"
    output_excel = "data/output/ranked_candidates.xlsx"

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