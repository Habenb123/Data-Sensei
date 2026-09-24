"""DataCrew — Split UI AI Data Analyst & Session Dashboard
Inspired by Neo-Brutalist & Cyber Editorial Design.
"""

from __future__ import annotations
import os
import io
import re
import time
import json
import streamlit as st
import pandas as pd
import plotly.express as px
from dotenv import load_dotenv

from src.database.duckdb_manager import DuckDBManager
from src.agents.crew_builder import create_datacrew, build_llm
from src.utils.chart_builder import extract_chart_spec, extract_sql_query, render_plotly_chart
from src.utils.data_profiler import profile_dataset

load_dotenv()

# Streamlit Page Config
st.set_page_config(
    page_title="DATACREW // AI DATA ANALYST",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ---------------------------------------------------------
# Custom Styling (Neo-Brutalist Split Palette: Crimson + Carbon)
# ---------------------------------------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Mono:ital,wght@0,400;0,700;1,400&family=Syne:wght@700;800&family=Inter:wght@300;400;600;700&display=swap');

    :root {
        --accent-red: #e11d48;
        --accent-red-hover: #be123c;
        --carbon-bg: #09090b;
        --carbon-surface: #121215;
        --carbon-border: #27272a;
        --text-bright: #f4f4f5;
        --text-dim: #a1a1aa;
    }

    .stApp {
        background-color: var(--carbon-bg);
        color: var(--text-bright);
        font-family: 'Inter', sans-serif;
    }

    /* Top Brand Nav */
    .brand-nav {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.75rem 1.5rem;
        border-bottom: 1px solid var(--carbon-border);
        background-color: #000000;
        margin-bottom: 1.5rem;
    }
    .brand-logo {
        font-family: 'Syne', sans-serif;
        font-size: 1.3rem;
        font-weight: 800;
        letter-spacing: -0.5px;
        color: var(--text-bright);
    }
    .brand-tag {
        font-family: 'Space Mono', monospace;
        font-size: 0.75rem;
        background-color: var(--accent-red);
        color: #fff;
        padding: 0.2rem 0.6rem;
        border-radius: 2px;
        text-transform: uppercase;
    }

    /* Split Hero Panels */
    .split-red-panel {
        background: linear-gradient(145deg, #e11d48 0%, #9f1239 100%);
        color: white;
        padding: 2.2rem;
        border-radius: 8px;
        border: 1px solid rgba(255,255,255,0.15);
        min-height: 520px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .split-carbon-panel {
        background-color: var(--carbon-surface);
        padding: 2.2rem;
        border-radius: 8px;
        border: 1px solid var(--carbon-border);
        min-height: 520px;
    }

    .headline-huge {
        font-family: 'Syne', sans-serif;
        font-size: 2.4rem;
        font-weight: 800;
        line-height: 1.1;
        letter-spacing: -1px;
        text-transform: uppercase;
        margin-bottom: 1rem;
    }
    .subtext-mono {
        font-family: 'Space Mono', monospace;
        font-size: 0.85rem;
        color: #e2e8f0;
        line-height: 1.6;
    }

    .step-box {
        font-family: 'Space Mono', monospace;
        font-size: 0.8rem;
        background: rgba(0,0,0,0.4);
        padding: 0.6rem 0.8rem;
        border-left: 3px solid var(--accent-red);
        margin-bottom: 0.5rem;
    }

    .history-card {
        background-color: var(--carbon-surface);
        border: 1px solid var(--carbon-border);
        padding: 0.8rem 1rem;
        border-radius: 6px;
        margin-bottom: 0.6rem;
        transition: all 0.2s ease;
    }
    .history-card:hover {
        border-color: var(--accent-red);
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------
if "db_manager" not in st.session_state:
    st.session_state.db_manager = DuckDBManager(table_name="dataset")
if "current_page" not in st.session_state:
    st.session_state.current_page = "intake"  # "intake" or "dashboard"
if "history" not in st.session_state:
    st.session_state.history = []  # List of dicts {id, time, question, sql, df, report, spec}
if "active_session_idx" not in st.session_state:
    st.session_state.active_session_idx = -1
if "provider" not in st.session_state:
    st.session_state.provider = "Ollama (Local)"
if "model_name" not in st.session_state:
    st.session_state.model_name = "qwen2.5-coder:14b"
if "api_key" not in st.session_state:
    st.session_state.api_key = ""


# ---------------------------------------------------------
# Top Navigation Bar
# ---------------------------------------------------------
nav_col1, nav_col2, nav_col3 = st.columns([2.5, 5, 2.5])
with nav_col1:
    st.markdown('<div class="brand-logo">DATACREW <span style="color:#e11d48">//</span> 01</div>', unsafe_allow_html=True)
with nav_col2:
    if st.session_state.db_manager.loaded:
        st.markdown(
            f"<div style='font-family:Space Mono; font-size:0.8rem; color:#a1a1aa; padding-top:6px;'>"
            f"DATASET: <span style='color:#fff;'>{st.session_state.db_manager.source_filename}</span> | "
            f"ROWS: <span style='color:#fff;'>{st.session_state.db_manager.row_count:,}</span> | "
            f"COLS: <span style='color:#fff;'>{st.session_state.db_manager.column_count}</span></div>",
            unsafe_allow_html=True
        )
with nav_col3:
    if st.session_state.current_page == "dashboard":
        if st.button("⬅️ File Ingestion", use_container_width=True):
            st.session_state.current_page = "intake"
            st.rerun()
    elif st.session_state.db_manager.loaded:
        if st.button("📊 Open Dashboard", type="primary", use_container_width=True):
            st.session_state.current_page = "dashboard"
            st.rerun()

st.divider()


# =========================================================
# PAGE 1: SPLIT INTAKE / UPLOAD PAGE
# =========================================================
if st.session_state.current_page == "intake":

    col_left, col_right = st.columns([1.1, 1], gap="large")

    # LEFT PANEL: Crimson File Drop & Engine Config
    with col_left:
        st.markdown("""
        <div class="split-red-panel">
            <div>
                <div style="font-family: 'Space Mono', monospace; font-size: 0.8rem; letter-spacing: 2px; opacity: 0.85;">
                    [ 01 // DATA INGESTION & ENGINE ]
                </div>
                <div class="headline-huge" style="margin-top: 0.8rem; margin-bottom: 0.5rem;">
                    UPLOAD DATA &<br>INITIALIZE
                </div>
                <div class="subtext-mono" style="margin-bottom: 1.5rem;">
                    DuckDB local OLAP engine loads tabular data directly into memory for sub-second analytical execution.
                </div>
            </div>
        """, unsafe_allow_html=True)

        # File Uploader
        uploaded_file = st.file_uploader(
            "Drop your CSV, Excel, or Parquet file:",
            type=["csv", "xlsx", "xls", "parquet"],
            label_visibility="collapsed"
        )

        btn_c1, btn_c2 = st.columns(2)
        with btn_c1:
            if uploaded_file is not None:
                if st.button("⚡ Ingest Uploaded File", type="primary", use_container_width=True):
                    ok, msg = st.session_state.db_manager.load_file(uploaded_file, uploaded_file.name)
                    if ok:
                        st.session_state.current_page = "dashboard"
                        st.rerun()
                    else:
                        st.error(msg)
        with btn_c2:
            if st.button("📂 Load Sample Data", use_container_width=True):
                sample_path = os.path.join(os.path.dirname(__file__), "sample_data", "ecommerce_sales.csv")
                if os.path.exists(sample_path):
                    ok, msg = st.session_state.db_manager.load_file(sample_path, "ecommerce_sales.csv")
                    if ok:
                        st.session_state.current_page = "dashboard"
                        st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    # RIGHT PANEL: Carbon LLM Setup & Agent Lineup
    with col_right:
        st.markdown("""
        <div class="split-carbon-panel">
            <div style="font-family: 'Space Mono', monospace; font-size: 0.8rem; letter-spacing: 2px; color: #e11d48;">
                [ 02 // AGENT ORCHESTRATION ]
            </div>
            <div class="headline-huge" style="color: #f4f4f5; margin-top: 0.8rem; margin-bottom: 0.8rem;">
                MULTI-AGENT<br>INTELLIGENCE
            </div>
        """, unsafe_allow_html=True)

        # Provider Selector
        p_col1, p_col2 = st.columns(2)
        with p_col1:
            provider = st.selectbox("LLM Provider", ["Ollama (Local)", "OpenAI", "Google Gemini", "Groq", "Anthropic"], index=0)
        with p_col2:
            default_model = "qwen2.5-coder:14b" if provider == "Ollama (Local)" else "gpt-4o-mini"
            model_name = st.text_input("Model Name", value=default_model)

        api_key = ""
        if provider != "Ollama (Local)":
            api_key = st.text_input(f"{provider} API Key", type="password")

        # Save settings in session
        st.session_state.provider = provider
        st.session_state.model_name = model_name
        st.session_state.api_key = api_key

        st.markdown("<div style='margin-top: 1rem;'>", unsafe_allow_html=True)
        st.markdown("<div class='step-box'><b>[1] DATA EXPLORER</b> — Auto-profiles schema & verifies types</div>", unsafe_allow_html=True)
        st.markdown("<div class='step-box'><b>[2] SQL SPECIALIST</b> — Writes & verifies DuckDB SQL dialect</div>", unsafe_allow_html=True)
        st.markdown("<div class='step-box'><b>[3] QUANT ANALYST</b> — Extracts statistical trends & outliers</div>", unsafe_allow_html=True)
        st.markdown("<div class='step-box'><b>[4] REPORT & VIZ</b> — Formats executive brief & interactive Plotly specs</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        if st.session_state.db_manager.loaded:
            st.success(f"Active: `{st.session_state.db_manager.source_filename}` ({st.session_state.db_manager.row_count:,} rows)")
            if st.button("🚀 Proceed to Findings Dashboard", type="primary", use_container_width=True):
                st.session_state.current_page = "dashboard"
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# PAGE 2: DASHBOARD & SESSION HISTORY
# =========================================================
elif st.session_state.current_page == "dashboard":

    # Layout: Left side Session History (3.2 cols) | Right side Active Analysis (8.8 cols)
    hist_col, main_col = st.columns([3.2, 8.8], gap="medium")

    # -----------------------------------------------------
    # LEFT COLUMN: SESSIONS & DATASET HEALTH
    # -----------------------------------------------------
    with hist_col:
        st.markdown("### 🕒 **Analysis Sessions**")
        st.caption(f"{len(st.session_state.history)} saved queries in session")

        if st.button("➕ New Analytical Query", use_container_width=True):
            st.session_state.active_session_idx = -1
            st.rerun()

        st.markdown("<div style='max-height: 380px; overflow-y: auto;'>", unsafe_allow_html=True)
        for idx, item in enumerate(reversed(st.session_state.history)):
            real_idx = len(st.session_state.history) - 1 - idx
            is_active = (st.session_state.active_session_idx == real_idx)
            btn_label = f"{'🔴 ' if is_active else ''}#{real_idx+1}: {item['question'][:28]}..."
            if st.button(btn_label, key=f"hist_{real_idx}", use_container_width=True):
                st.session_state.active_session_idx = real_idx
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

        st.divider()

        # Dataset Profiling Accordion
        with st.expander("📊 Dataset Health & Schema", expanded=False):
            df_full = st.session_state.db_manager.get_full_dataframe()
            prof = profile_dataset(df_full)
            st.write(f"**Total Rows:** {prof.get('total_rows', 0):,}")
            st.write(f"**Total Columns:** {prof.get('total_cols', 0)}")
            st.write(f"**Duplicates:** {prof.get('duplicate_pct', 0)}%")
            if prof.get("column_summary_df") is not None:
                st.dataframe(prof["column_summary_df"][["Column", "Type", "Missing %"]], height=200)

    # -----------------------------------------------------
    # RIGHT COLUMN: ACTIVE ANALYSIS & WORKSPACE
    # -----------------------------------------------------
    with main_col:
        # Check if viewing a historical session
        active_item = None
        if st.session_state.active_session_idx >= 0 and st.session_state.active_session_idx < len(st.session_state.history):
            active_item = st.session_state.history[st.session_state.active_session_idx]

        st.markdown("### 🤖 **Multi-Agent Analytical Workspace**")

        # Query Input Bar
        default_q = active_item["question"] if active_item else ""
        user_query = st.text_area(
            "Enter your analytical question:",
            value=default_q,
            placeholder="e.g. Which product category generated the highest total profit, and what was its profit margin?",
            height=70
        )

        col_q1, col_q2, col_q3 = st.columns([1.5, 3, 3])
        run_btn = False
        with col_q1:
            run_btn = st.button("🚀 Run Analysis", type="primary", use_container_width=True)
        with col_q2:
            st.caption("Quick suggestions:")
            if st.button("📈 Profit & Sales by Category", use_container_width=True):
                user_query = "What is the total sales and total profit broken down by category? Include profit margin."
                run_btn = True
        with col_q3:
            st.caption(" ")
            if st.button("🌍 Regional Performance", use_container_width=True):
                user_query = "Compare total sales, profit, and average discount across different regions."
                run_btn = True

        # Run CrewAI Pipeline
        if run_btn and user_query.strip():
            provider = st.session_state.get("provider", "Ollama (Local)")
            model_name = st.session_state.get("model_name", "qwen2.5-coder:14b")
            api_key = st.session_state.get("api_key", "")

            try:
                with st.status("⚡ Agents collaborating in real-time...", expanded=True) as status_box:
                    st.write("🔍 **Explorer:** Scanning schema, data types, and sample records...")
                    time.sleep(0.3)
                    st.write("🦆 **SQL Specialist:** Generating DuckDB SQL query and executing...")
                    time.sleep(0.3)
                    st.write("📈 **Data Analyst:** Computing statistical metrics, growth, and trends...")
                    time.sleep(0.3)
                    st.write("📑 **Report Agent:** Synthesizing executive brief & Plotly visualization...")

                    llm_inst = build_llm(provider, model_name, api_key)
                    crew = create_datacrew(st.session_state.db_manager, user_query, llm_inst)
                    crew_out = crew.kickoff()
                    report_text = str(crew_out)
                    status_box.update(label="✅ Analysis Complete!", state="complete", expanded=False)

                # Extract SQL & Spec
                sql = extract_sql_query(report_text)
                spec = extract_chart_spec(report_text)
                res_df = None
                if sql:
                    res_df, _, _ = st.session_state.db_manager.execute_query(sql)

                # Save to History
                new_session = {
                    "id": len(st.session_state.history) + 1,
                    "time": time.strftime("%H:%M:%S"),
                    "question": user_query,
                    "sql": sql,
                    "df": res_df,
                    "report": report_text,
                    "spec": spec
                }
                st.session_state.history.append(new_session)
                st.session_state.active_session_idx = len(st.session_state.history) - 1
                active_item = new_session

            except Exception as e:
                st.error(f"Error during analysis: {str(e)}")

        # Display Current or Selected Historical Findings
        if active_item:
            st.divider()
            f_col1, f_col2 = st.columns([1.1, 0.9])

            with f_col1:
                st.markdown("#### 📑 **Executive Findings**")
                clean_report = re.sub(r"```(?:chart_spec|json)\s*\{.*?\}\s*```", "", active_item["report"], flags=re.DOTALL)
                st.markdown(clean_report)

                st.download_button(
                    "📥 Export Report (.md)",
                    data=clean_report,
                    file_name=f"DataCrew_Session_{active_item['id']}.md",
                    mime="text/markdown"
                )

            with f_col2:
                st.markdown("#### 📊 **Interactive Chart**")
                if active_item.get("df") is not None and not active_item["df"].empty:
                    fig = render_plotly_chart(active_item["df"], active_item.get("spec"))
                    if fig:
                        st.plotly_chart(fig, use_container_width=True)

                    st.markdown("#### 🗃️ **Query Result Data**")
                    st.dataframe(active_item["df"], use_container_width=True, height=220)

                    # CSV Download
                    csv_bytes = active_item["df"].to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "📥 Download Result Data (CSV)",
                        data=csv_bytes,
                        file_name=f"DataCrew_Query_{active_item['id']}.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("No numerical query results table to plot.")
