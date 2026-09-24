import os
import threading
import time
import requests
import pandas as pd
import streamlit as st

from src.common.config import (
    DEFAULT_SEMANTIC_WEIGHT,
    DEFAULT_EXACT_WEIGHT,
    DEFAULT_WHOLE_RESUME_WEIGHT,
    DEFAULT_BEST_CHUNK_WEIGHT,
    DEFAULT_BEST_REQUIREMENT_WEIGHT,
    DEFAULT_TOP_K,
    STREAMLIT_REQUEST_TIMEOUT,
)

API_URL = os.getenv("API_URL", "http://localhost:8000")

# Stage display mapping for the 10 stages
STAGE_DISPLAY_NAMES = [
    (1, "Candidate ingestion"),
    (2, "JD requirement extraction"),
    (3, "Resume download"),
    (4, "Resume extraction"),
    (5, "Vector store creation"),
    (6, "Semantic retrieval"),
    (7, "Exact retrieval"),
    (8, "Candidate aggregation"),
    (9, "Reranking"),
    (10, "Excel export"),
]

# --------------------------------------------------
# Streamlit Page Config & Custom Styling
# --------------------------------------------------
st.set_page_config(
    page_title="Candidate Retrieval System - Palle Technologies",
    page_icon="🎯",
    layout="wide"
)

st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .footer-watermark {
        position: fixed;
        bottom: 10px;
        right: 20px;
        font-size: 0.85rem;
        font-weight: 600;
        color: #9CA3AF;
        letter-spacing: 0.05em;
        pointer-events: none;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown('<div class="main-title">🎯 Candidate Retrieval System</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Automated JD Extraction, Hybrid Semantic Retrieval & Reranking</div>', unsafe_allow_html=True)

# --------------------------------------------------
# 1. Inputs Section
# --------------------------------------------------
st.subheader("1. Ingestion & Job Description")

input_mode = st.radio(
    "Job Description Input Method",
    ["Upload JD Document (.pdf, .docx, .txt)", "Paste JD Text"],
    horizontal=True
)

jd_file = None
jd_raw_text = None

if input_mode == "Upload JD Document (.pdf, .docx, .txt)":
    jd_file = st.file_uploader(
        "Upload Job Description",
        type=["pdf", "docx", "txt"],
        help="Upload a Job Description file in PDF, Word (.docx), or plain text format."
    )
else:
    jd_raw_text = st.text_area(
        "Paste Job Description Text",
        height=150,
        placeholder="Paste full job description requirements here..."
    )

candidate_file = st.file_uploader(
    "Candidate Excel File",
    type=["xlsx", "xls"],
    help="Upload the candidate tracker in Excel format (.xlsx)"
)

st.markdown("<hr>", unsafe_allow_html=True)

# --------------------------------------------------
# 2. Ranking Settings Section
# --------------------------------------------------
st.subheader("2. Ranking Settings")
st.caption("Configure weights below to experiment with retrieval and ranking behavior.")

col1, col2, col3 = st.columns(3)
with col1:
    semantic_weight = st.slider("Semantic Weight", 0.0, 1.0, DEFAULT_SEMANTIC_WEIGHT, 0.05)
with col2:
    exact_weight = st.slider("Exact Match Weight", 0.0, 1.0, DEFAULT_EXACT_WEIGHT, 0.05)
with col3:
    top_k = st.number_input("Top Candidates (Top K)", min_value=1, max_value=100, value=DEFAULT_TOP_K, step=1)

st.markdown("#### Semantic Retrieval Weights")

col_sem1, col_sem2 = st.columns(2)
with col_sem1:
    st.markdown("##### Resume-Level Matching")
    whole_resume_weight = st.slider("Whole Resume Weight", 0.0, 1.0, DEFAULT_WHOLE_RESUME_WEIGHT, 0.05)
    best_chunk_weight = st.slider("Best Chunk Weight", 0.0, 1.0, DEFAULT_BEST_CHUNK_WEIGHT, 0.05)

with col_sem2:
    st.markdown("##### Requirement-Level Matching")
    best_requirement_weight = st.slider("Best Requirement Weight", 0.0, 1.0, DEFAULT_BEST_REQUIREMENT_WEIGHT, 0.05)

st.markdown("<hr>", unsafe_allow_html=True)

# --------------------------------------------------
# 3. Search Action with Concurrent Polling Display
# --------------------------------------------------
search_clicked = st.button("Search Candidates", use_container_width=True, type="primary")

if search_clicked:
    has_jd = (jd_file is not None) or (jd_raw_text and jd_raw_text.strip())
    if not has_jd:
        st.error("Please provide a Job Description (upload a PDF/DOCX/TXT file or paste text).")
    elif not candidate_file:
        st.error("Please upload a Candidate Excel file.")
    else:
        # Clear previous state
        st.session_state["ranked_candidates"] = None
        st.session_state["download_url"] = None

        status_container = st.empty()

        files = {
            "candidate_file": (
                candidate_file.name,
                candidate_file.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        }
        if jd_file:
            files["jd_file"] = (jd_file.name, jd_file.getvalue(), jd_file.type or "application/octet-stream")

        data = {
            "semantic_weight": semantic_weight,
            "exact_weight": exact_weight,
            "whole_resume_weight": whole_resume_weight,
            "best_chunk_weight": best_chunk_weight,
            "best_requirement_weight": best_requirement_weight,
            "top_k": top_k
        }
        if jd_raw_text and jd_raw_text.strip():
            data["jd_text"] = jd_raw_text.strip()

        try:
            resp = requests.post(
                f"{API_URL}/api/recruitment/search",
                files=files,
                data=data,
                timeout=30
            )

            if resp.status_code == 202:
                init_data = resp.json()
                job_id = init_data.get("job_id")
                st.session_state["active_job_id"] = job_id

                poll_interval = 0.8
                start_time = time.time()

                while True:
                    try:
                        stat_resp = requests.get(
                            f"{API_URL}/api/recruitment/jobs/{job_id}/status",
                            timeout=5
                        )
                        if stat_resp.status_code == 200:
                            stat_data = stat_resp.json()
                            job_status = stat_data.get("status", "running")
                            current_stage = stat_data.get("stage", 1)
                            stage_message = stat_data.get("message", "Processing recruitment pipeline...")

                            with status_container.container():
                                st.markdown("### 🔄 Pipeline Progress")
                                st.info(f"**Current Status:** {stage_message}")

                                for stg_num, stg_title in STAGE_DISPLAY_NAMES:
                                    if stg_num < current_stage or job_status == "completed":
                                        st.write(f"✅ **Stage {stg_num}/10: {stg_title}** — Completed")
                                    elif stg_num == current_stage and job_status == "running":
                                        st.write(f"⏳ **Stage {stg_num}/10: {stg_title}** — In Progress...")
                                    elif stg_num == current_stage and job_status == "failed":
                                        st.write(f"❌ **Stage {stg_num}/10: {stg_title}** — Failed")
                                    else:
                                        st.write(f"⚪ Stage {stg_num}/10: {stg_title} — Pending")

                            if job_status == "completed":
                                status_container.empty()
                                st.session_state["ranked_candidates"] = stat_data.get("candidates", [])
                                st.session_state["download_url"] = stat_data.get("download_url", f"/api/recruitment/download/{job_id}")
                                st.success("Candidate retrieval and reranking completed successfully.")
                                break
                            elif job_status == "failed":
                                status_container.empty()
                                err = stat_data.get("error", {})
                                stage_lbl = err.get("stage", "Pipeline").replace("_", " ").title()
                                msg = err.get("message", "An error occurred during search.")
                                st.error(f"**{stage_lbl} Failed**\n\n{msg}")
                                break
                        elif stat_resp.status_code == 404:
                            status_container.empty()
                            st.error(f"Job {job_id} was not found or has expired.")
                            break
                    except Exception:
                        pass

                    if time.time() - start_time > STREAMLIT_REQUEST_TIMEOUT:
                        status_container.empty()
                        st.error("Recruitment search timed out while waiting for pipeline completion.")
                        break

                    time.sleep(poll_interval)
            else:
                try:
                    payload = resp.json()
                    if isinstance(payload, dict) and "error" in payload:
                        err = payload["error"]
                        stage = err.get("stage", "Input Validation").replace("_", " ").title()
                        msg = err.get("message", "Request failed.")
                        st.error(f"**{stage} Failed**\n\n{msg}")
                    else:
                        st.error(f"Search request failed (HTTP {resp.status_code})")
                except Exception:
                    st.error(f"Search request failed (HTTP {resp.status_code})")
        except Exception as exc:
            st.error(f"Failed to connect to backend: {exc}")

# --------------------------------------------------
# 4. Results Section
# --------------------------------------------------
if st.session_state.get("ranked_candidates"):
    st.markdown("<hr>", unsafe_allow_html=True)
    st.subheader("RANKED CANDIDATES")

    df_results = pd.DataFrame(st.session_state["ranked_candidates"])

    # Rename & format columns for clean display
    column_mapping = {
        "rank": "Rank",
        "name": "Candidate Name",
        "source_row": "Source Row",
        "semantic_score": "Semantic Score",
        "exact_score": "Exact Score",
        "final_score": "Final Score"
    }

    display_cols = [col for col in column_mapping.keys() if col in df_results.columns]
    df_display = df_results[display_cols].rename(columns=column_mapping)

    # Format float scores if present
    for score_col in ["Semantic Score", "Exact Score", "Final Score"]:
        if score_col in df_display.columns:
            df_display[score_col] = df_display[score_col].apply(
                lambda v: f"{v:.4f}" if isinstance(v, (int, float)) and pd.notnull(v) else v
            )

    st.dataframe(df_display, use_container_width=True, hide_index=True)

    # --------------------------------------------------
    # 5. Excel Download Section
    # --------------------------------------------------
    try:
        download_endpoint = st.session_state.get("download_url", "/api/recruitment/download")
        full_download_url = f"{API_URL}{download_endpoint}" if download_endpoint.startswith("/") else download_endpoint
        excel_response = requests.get(full_download_url, timeout=60)

        if excel_response.status_code == 200:
            st.download_button(
                label="Download Ranked Excel",
                data=excel_response.content,
                file_name="ranked_candidates.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        else:
            st.error("Could not fetch the generated Excel file from backend.")
    except Exception:
        st.error("Failed to connect to backend for Excel download.")

# --------------------------------------------------
# Watermark / Footer
# --------------------------------------------------
st.markdown('<div class="footer-watermark">PALLE TECHNOLOGIES</div>', unsafe_allow_html=True)

