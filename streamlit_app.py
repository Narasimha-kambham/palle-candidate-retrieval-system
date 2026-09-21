import io
import os
import requests
import pandas as pd
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

# --------------------------------------------------
# Page Configuration & Minimal Dark Styling
# --------------------------------------------------
st.set_page_config(
    page_title="PCRS - Palle Candidate Retrieval System",
    page_icon="📄",
    layout="centered"
)

st.markdown(
    """
    <style>
    /* Minimal Dark Theme */
    .stApp {
        background-color: #0b0c10;
        color: #e0e0e0;
    }
    
    /* Header Typography */
    h1, h2, h3, h4, h5, h6 {
        color: #ffffff !important;
        font-weight: 600;
        letter-spacing: -0.5px;
    }
    
    /* Subtitle */
    .subtitle {
        color: #8a8d91;
        font-size: 1rem;
        margin-top: -15px;
        margin-bottom: 30px;
    }
    
    /* Section Dividers */
    hr {
        border-color: #22252a;
        margin: 25px 0;
    }

    /* Cards / Containers styling with gray borders */
    [data-testid="stFileUploader"], [data-testid="stDataFrame"], div[data-baseweb="input"] {
        border-color: #2a2e35 !important;
    }

    /* Watermark / Footer */
    .footer-watermark {
        text-align: center;
        margin-top: 60px;
        margin-bottom: 20px;
        color: #4a4d52;
        font-size: 0.8rem;
        letter-spacing: 2px;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --------------------------------------------------
# Branding Header
# --------------------------------------------------
st.title("PCRS")
st.markdown('<div class="subtitle">Palle Candidate Retrieval System</div>', unsafe_allow_html=True)

# --------------------------------------------------
# 1. Upload Section
# --------------------------------------------------
st.subheader("1. Upload")

jd_input_mode = st.radio("JD Input Method", ["Upload Document (.pdf, .docx, .txt)", "Paste Text"], horizontal=True)

jd_file = None
jd_raw_text = None

if jd_input_mode == "Upload Document (.pdf, .docx, .txt)":
    jd_file = st.file_uploader(
        "Job Description File",
        type=["pdf", "docx", "doc", "txt"],
        help="Upload the Job Description in PDF, DOCX, or TXT format"
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

col1, col2 = st.columns(2)
with col1:
    semantic_weight = st.slider("Semantic Weight", 0.0, 1.0, 0.80, 0.05)
    whole_resume_weight = st.slider("Whole Resume Weight", 0.0, 1.0, 0.30, 0.05)
    best_chunk_weight = st.slider("Best Chunk Weight", 0.0, 1.0, 0.40, 0.05)

with col2:
    exact_weight = st.slider("Exact Match Weight", 0.0, 1.0, 0.20, 0.05)
    best_requirement_weight = st.slider("Best Requirement Weight", 0.0, 1.0, 0.30, 0.05)
    top_k = st.number_input("Top Candidates (Top K)", min_value=1, max_value=100, value=20, step=1)

st.markdown("<hr>", unsafe_allow_html=True)

# --------------------------------------------------
# 3. Search Action
# --------------------------------------------------
search_clicked = st.button("Search Candidates", use_container_width=True, type="primary")

if search_clicked:
    has_jd = (jd_file is not None) or (jd_raw_text and jd_raw_text.strip())
    if not has_jd:
        st.error("Please provide a Job Description (upload a PDF/DOCX/TXT file or paste text).")
    elif not candidate_file:
        st.error("Please upload a Candidate Excel file.")
    else:
        with st.spinner("Processing JD, retrieving candidates and reranking..."):
            try:
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

                response = requests.post(
                    f"{API_URL}/api/recruitment/search",
                    files=files,
                    data=data,
                    timeout=180
                )

                if response.status_code == 200:
                    payload = response.json()
                    st.session_state["ranked_candidates"] = payload.get("candidates", [])
                    st.session_state["download_url"] = payload.get("excel_file", "/api/recruitment/download")
                    st.success("Candidate retrieval and reranking completed successfully.")
                else:
                    st.error(f"Backend error ({response.status_code}): {response.text}")

            except requests.exceptions.ConnectionError:
                st.error(f"Could not connect to FastAPI backend at {API_URL}. Please ensure the server is running.")
            except requests.exceptions.Timeout:
                st.error("Request timed out. The backend took too long to respond.")
            except Exception as e:
                st.error("An unexpected error occurred while processing the request.")

# --------------------------------------------------
# 4. Results Section
# --------------------------------------------------
if "ranked_candidates" in st.session_state and st.session_state["ranked_candidates"]:
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

