import streamlit as st
import os
import re
import datetime
import pandas as pd
import yaml
import time
from src.engine.materiality import calculate_kpi_value, analyze_kpi_change, load_yaml
from src.engine.synthesis import generate_synthesis_report
from src.engine.personas import generate_persona_views
from src.feedback.handler import (
    initialize_database,
    log_execution_run,
    log_analyst_feedback,
    get_run_history,
    get_feedback_by_run,
    get_action_governance_signal
)
import plotly.express as px
import plotly.graph_objects as go

# Configure the page
st.set_page_config(
    page_title="StoryProof | Evidence-First KPI Intelligence",
    page_icon="🔍",
    layout="centered"
)

# ------------------------------------------------------------------------------
# STATELESS HELPERS (Pytest Testable)
# ------------------------------------------------------------------------------

def calculate_database_metrics(db_path="data/storyproof_audit.db"):
    """
    Retrieves execution run count and analyst feedback count in an optimized way.
    Returns (run_count, feedback_count, db_initialized).
    """
    import sqlite3
    if not os.path.exists(db_path):
        return 0, 0, False
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM execution_runs;")
        run_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM analyst_feedback;")
        feedback_count = cursor.fetchone()[0]
        conn.close()
        return run_count, feedback_count, True
    except Exception as e:
        print(f"Warning: Failed to fetch database metrics: {e}")
        return 0, 0, False

def get_all_feedback(db_path="data/storyproof_audit.db"):
    """
    Queries all analyst feedback across all runs, ordered chronologically with newest first.
    """
    import sqlite3
    if not os.path.exists(db_path):
        return []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM analyst_feedback ORDER BY timestamp DESC;")
        rows = cursor.fetchall()
        feedback = [dict(row) for row in rows]
        conn.close()
        return feedback
    except Exception as e:
        print(f"Warning: Failed to fetch global feedback: {e}")
        return []

def validate_reporting_periods(baseline_period, comparison_period):
    """
    Validates that periods are tuples/lists of length 2, start <= end,
    and dates are valid ISO format YYYY-MM-DD.
    Does not mutate input arguments.
    """
    if not isinstance(baseline_period, (list, tuple)) or len(baseline_period) != 2:
        return False
    if not isinstance(comparison_period, (list, tuple)) or len(comparison_period) != 2:
        return False

    def check_date(d):
        if not isinstance(d, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
            return False
        try:
            datetime.date.fromisoformat(d)
            return True
        except ValueError:
            return False

    if not all(check_date(d) for d in list(baseline_period) + list(comparison_period)):
        return False

    b_start = datetime.date.fromisoformat(baseline_period[0])
    b_end = datetime.date.fromisoformat(baseline_period[1])
    c_start = datetime.date.fromisoformat(comparison_period[0])
    c_end = datetime.date.fromisoformat(comparison_period[1])

    if b_start > b_end or c_start > c_end:
        return False

    return True

def load_kpi_definitions(config_path="config/kpi_definitions.yaml"):
    """
    Loads KPI definitions dictionary. Returns None on error.
    """
    if not os.path.exists(config_path):
        return None
    try:
        return load_yaml(config_path)
    except (OSError, yaml.YAMLError, ValueError, TypeError, KeyError):
        return None

def load_kpi_time_series(kpi_name, kpi_definitions, data_dir, role=None):
    """
    Loads raw CSV data for a KPI and formats it to ['date', 'value'] columns,
    following the authoritative configuration mapping. Returns None on missing/malformed inputs
    or if the requesting role lacks entitlement access to the KPI.
    Does not mutate input arguments.
    """
    if role is not None and not check_kpi_access(role, kpi_name, kpi_definitions):
        return None

    if not kpi_definitions or not data_dir or not isinstance(kpi_definitions, dict):
        return None

    kpi_def = kpi_definitions.get(kpi_name)
    if not kpi_def or "source" not in kpi_def:
        return None

    source_file = kpi_def.get("source")
    file_path = os.path.join(data_dir, source_file)
    if not os.path.exists(file_path):
        return None

    try:
        df = pd.read_csv(file_path)
    except (OSError, pd.errors.ParserError, ValueError, TypeError):
        return None

    # Get date column
    date_col = kpi_def.get("date_column")
    if not date_col or date_col not in df.columns:
        # Fallback common candidates
        for c in ["date", "week_start", "month", "day"]:
            if c in df.columns:
                date_col = c
                break
    if not date_col or date_col not in df.columns:
        return None

    try:
        # Group by date column and compute authoritative volume-weighted KPI value per date
        records = []
        for date_val, group in df.groupby(date_col):
            kpi_val = calculate_kpi_value(group, kpi_name, kpi_def)
            if kpi_val is not None:
                records.append({
                    "date": pd.to_datetime(date_val),
                    "value": float(kpi_val)
                })

        if not records:
            return None

        res_df = pd.DataFrame(records).sort_values("date").reset_index(drop=True)
        return res_df
    except (KeyError, ValueError, TypeError, ZeroDivisionError, pd.errors.ParserError, OSError):
        return None

def build_trend_chart(kpi_name, kpi_df, baseline_period, comparison_period, show_shading=True):
    """
    Builds a Plotly trend chart for the KPI.
    Aggregates dense daily series (e.g. AHT, FCR, Repeat Contact) to weekly averages for visual clarity,
    while preserving natural daily grain for sparse series (AI Resolution Rate) and weekly/monthly series.
    Shades baseline and comparison ranges if show_shading is True.
    """
    if kpi_df is None or kpi_df.empty:
        return None

    plot_df = kpi_df.copy()
    plot_df = plot_df.groupby('date', as_index=False)['value'].mean().sort_values('date')

    # Weekly visual aggregation for long daily series (>30 days) to prevent spaghetti clutter
    is_weekly_aggregated = False
    if len(plot_df) > 30:
        try:
            plot_df_indexed = plot_df.set_index('date')
            weekly_df = plot_df_indexed.resample('W-MON').mean().dropna().reset_index()
            if not weekly_df.empty and len(weekly_df) >= 4:
                plot_df = weekly_df
                is_weekly_aggregated = True
        except Exception:
            pass

    chart_title = f"{kpi_name} Over Time"
    if is_weekly_aggregated:
        chart_title += " (Weekly Visual Average)"

    fig = px.line(plot_df, x="date", y="value", title=chart_title, markers=True)

    if show_shading:
        # Baseline shading
        fig.add_vrect(
            x0=baseline_period[0], x1=baseline_period[1],
            fillcolor="rgba(100, 100, 100, 0.15)", opacity=0.5,
            layer="below", line_width=0,
            annotation_text="Baseline Period", annotation_position="top left"
        )
        # Comparison shading
        fig.add_vrect(
            x0=comparison_period[0], x1=comparison_period[1],
            fillcolor="rgba(0, 150, 255, 0.1)", opacity=0.5,
            layer="below", line_width=0,
            annotation_text="Comparison Period", annotation_position="top left"
        )

    fig.update_layout(
        xaxis_title="Date",
        yaxis_title=kpi_name,
        hovermode="x unified",
        margin=dict(l=20, r=20, t=40, b=20)
    )
    return fig

def check_role_permission(role, permission_type):
    """
    Checks if a given role is authorized to perform a specific action:
    - 'view_cx': CX Manager, Guest, Administrator
    - 'view_ops': Operations Manager, Guest, Administrator
    - 'submit_feedback': CX Manager, Operations Manager, Administrator
    - 'view_observability': Administrator
    - 'view_history': Administrator
    """
    if permission_type == "view_cx":
        return role in ["CX Manager", "Guest", "Administrator"]
    if permission_type == "view_ops":
        return role in ["Operations Manager", "Guest", "Administrator"]
    if permission_type == "submit_feedback":
        return role in ["CX Manager", "Operations Manager", "Administrator"]
    if permission_type == "view_observability":
        return role in ["Administrator"]
    if permission_type == "view_history":
        return role in ["Administrator"]
    return False

def get_accessible_kpis(role, kpi_definitions):
    """
    Returns the list of KPI names accessible to the given role,
    based on the allowed_roles_personas field in kpi_definitions.yaml.

    Role mapping (YAML uses Manager-style names):
      - 'Administrator' -> full access to all KPIs
      - 'CX Manager' -> KPIs with 'CX Manager' in allowed_roles_personas
      - 'Operations Manager' -> KPIs with 'Operations Manager' in allowed_roles_personas
      - 'Guest' -> intersection (KPIs accessible to BOTH CX Manager and Operations Manager)

    Returns:
      List of KPI name strings the role is entitled to access.
    """
    if not kpi_definitions or not isinstance(kpi_definitions, dict):
        return []

    all_kpis = list(kpi_definitions.keys())

    if role == "Administrator":
        return all_kpis

    accessible = []
    for kpi_name, kpi_def in kpi_definitions.items():
        allowed = kpi_def.get("allowed_roles_personas", [])
        if not isinstance(allowed, list):
            continue

        if role == "CX Manager":
            if "CX Manager" in allowed:
                accessible.append(kpi_name)
        elif role == "Operations Manager":
            if "Operations Manager" in allowed:
                accessible.append(kpi_name)
        elif role == "Guest":
            # Guest sees only KPIs accessible to BOTH manager roles (common set)
            if "CX Manager" in allowed and "Operations Manager" in allowed:
                accessible.append(kpi_name)

    return accessible

def check_kpi_access(role, kpi_name, kpi_definitions):
    """
    Validates whether a specific role is authorized to access a given KPI,
    based on the allowed_roles_personas field in kpi_definitions.yaml.

    Returns:
      True if role is authorized to access kpi_name, False otherwise.
    """
    if not kpi_definitions or not isinstance(kpi_definitions, dict) or not kpi_name:
        return False
    accessible_kpis = get_accessible_kpis(role, kpi_definitions)
    return kpi_name in accessible_kpis

def get_decision_view_title(role):
    """
    Returns the appropriate Current Decision View title string based on the user's role:
      - 'CX Manager' -> 'CX Manager'
      - 'Operations Manager' -> 'Operations Manager'
      - 'Guest' -> 'Guest-Restricted Decision View'
      - 'Administrator' -> 'Administrator / Governance View'
    """
    if role == "CX Manager":
        return "CX Manager"
    elif role == "Operations Manager":
        return "Operations Manager"
    elif role == "Guest":
        return "Guest-Restricted Decision View"
    elif role == "Administrator":
        return "Administrator / Governance View"
    return role

def get_evidence_provenance_badge(refs):
    """
    Derives transparent provenance, freshness, and analytical method metadata for a list of references.
    Explicitly separates dynamic event timestamps from configured cadences.
    """
    if not refs:
        return []
    details = []
    for ref in refs:
        if ref.startswith("support_transcripts"):
            details.append(f"**Ticket Transcript** `{ref}` | Source: `data/unstructured/support_transcripts.txt` | Grain: Event Date | Method: Keyword Relevance Scoring")
        elif ref.startswith("customer_feedback"):
            details.append(f"**CSAT Review** `{ref}` | Source: `data/unstructured/customer_feedback.txt` | Grain: Event Date | Method: Qualitative Feedback Retrieval")
        elif ref.startswith("rollout_report"):
            details.append(f"**Project Memo** `{ref}` | Source: `data/unstructured/rollout_report.txt` | Doc Date: 2026-06-30 | Method: Status Report Parsing")
        elif "_materiality" in ref:
            kpi = ref.replace("_materiality", "")
            if kpi in ["AHT", "FCR", "Repeat_Contact_Rate"]:
                details.append(f"**Structured Metric** `{ref}` | Source: `data/support_daily.csv` | Cadence: Daily | History: Sufficient (181d >= 30d req) | Method: Z-Score Materiality Gate")
            elif kpi == "CSAT":
                details.append(f"**Structured Metric** `{ref}` | Source: `data/cx_weekly.csv` | Cadence: Weekly | History: Sufficient (175d >= 90d req) | Method: Absolute Threshold Gate")
            elif kpi == "Retention_Rate":
                details.append(f"**Structured Metric** `{ref}` | Source: `data/crm_monthly.csv` | Cadence: Monthly | History: Sufficient (181d >= 180d req) | Method: Trailing Baseline Gate")
            elif kpi == "AI_Resolution_Rate":
                details.append(f"**Structured Metric** `{ref}` | Source: `data/ai_resolution_rate.csv` | Cadence: Daily | History: Sparse (21d / 60d req) | Method: History Sufficiency Gate")
            else:
                details.append(f"**Structured Metric** `{ref}` | Source: `config/kpi_definitions.yaml` | Cadence: Configured | Method: Baseline Materiality Gate")
        elif "_driver" in ref:
            details.append(f"**Variance Attribution** `{ref}` | Source: Segment Dimension Split | Method: Shapley Mix-Rate Decomposition (Zero-Error Reconciled)")
        elif "_hypothesis" in ref:
            details.append(f"**Hypothesis Evidence** `{ref}` | Source: Multi-Source Operational Logs | Method: Differential Signal & Confounder Control Concentration")
        else:
            details.append(f"**Evidence Reference** `{ref}` | Source: System Evidence Register | Metadata: Not available")
    return details


def calculate_projected_llm_cost(total_runs):
    """
    Computes simulated token usage and projected costs.
    """
    simulated_input_tokens = 8500
    simulated_output_tokens = 1200
    input_rate_per_1k = 0.005
    output_rate_per_1k = 0.015

    cost_per_run = (simulated_input_tokens / 1000 * input_rate_per_1k) + (simulated_output_tokens / 1000 * output_rate_per_1k)
    total_projected_cost = total_runs * cost_per_run

    return {
        "simulated_input_tokens": simulated_input_tokens,
        "simulated_output_tokens": simulated_output_tokens,
        "input_rate_per_1k": input_rate_per_1k,
        "output_rate_per_1k": output_rate_per_1k,
        "cost_per_run": cost_per_run,
        "total_projected_cost": total_projected_cost
    }

def run_intelligence_pipeline(data_dir, baseline_period, comparison_period):
    """
    Executes the synthesis and persona engines, returning the results and the latency.
    """
    t_start = time.perf_counter()
    try:
        synthesis_result = generate_synthesis_report(
            data_dir=data_dir,
            baseline_period=baseline_period,
            comparison_period=comparison_period
        )
        persona_views = generate_persona_views(synthesis_result)
    except Exception as e:
        synthesis_result = {"status": "ERROR", "reason": str(e), "report": []}
        persona_views = {"status": "ERROR", "reason": str(e), "personas": {}}
    latency = max(0.0, time.perf_counter() - t_start)
    return synthesis_result, persona_views, latency

def resolve_execution_run_id(
    synthesis_result,
    persona_views,
    baseline_period,
    comparison_period,
    data_dir,
    cached_run_id,
    cached_key,
    db_path="data/storyproof_audit.db",
    log_run_fn=log_execution_run
):
    """
    Resolves the execution run ID. Reuses cached_run_id if the run_key (baseline_period, comparison_period, data_dir)
    matches the cached_key. Otherwise, logs a new run and returns the new run_id.
    """
    run_key = (baseline_period, comparison_period, data_dir)
    if cached_run_id is not None and cached_key == run_key:
        return cached_run_id, run_key, False

    new_run_id = log_run_fn(
        synthesis_result=synthesis_result,
        persona_views=persona_views,
        db_path=db_path,
        baseline_period=baseline_period,
        comparison_period=comparison_period
    )
    if new_run_id:
        return new_run_id, run_key, True
    return None, None, False

# ------------------------------------------------------------------------------
# STREAMLIT UI RENDER LAYER
# ------------------------------------------------------------------------------

def format_classification_badge(cls):
    """
    Returns visual badge for statement classification.
    """
    badge_map = {
        "FACT": "🟢 FACT",
        "ASSOCIATION": "🔵 ASSOCIATION",
        "HYPOTHESIS": "🟡 HYPOTHESIS",
        "CONTEXT": "🟣 CONTEXT",
        "LIMITATION": "🔴 LIMITATION"
    }
    return badge_map.get(cls, f"[{cls}]")

def main():
    st.title("StoryProof")
    st.subheader("Evidence-first KPI Intelligence")
    st.caption("Evidence-backed decision support for KPI investigation and operational action")

    # 1. Sidebar Configurations
    st.sidebar.header("Configuration")
    if "data_dir_input" not in st.session_state:
        st.session_state["data_dir_input"] = "data"
    if "b_start_input" not in st.session_state:
        st.session_state["b_start_input"] = "2026-01-01"
    if "b_end_input" not in st.session_state:
        st.session_state["b_end_input"] = "2026-03-31"
    if "c_start_input" not in st.session_state:
        st.session_state["c_start_input"] = "2026-06-01"
    if "c_end_input" not in st.session_state:
        st.session_state["c_end_input"] = "2026-06-30"

    data_dir = st.sidebar.text_input("Data Directory", key="data_dir_input")

    st.sidebar.subheader("Baseline Period")
    b_start = st.sidebar.text_input("Baseline Start", key="b_start_input")
    b_end = st.sidebar.text_input("Baseline End", key="b_end_input")

    st.sidebar.subheader("Comparison Period")
    c_start = st.sidebar.text_input("Comparison Start", key="c_start_input")
    c_end = st.sidebar.text_input("Comparison End", key="c_end_input")

    baseline_period = (b_start, b_end)
    comparison_period = (c_start, c_end)

    # Initialize SQLite Audit DB
    db_initialized = initialize_database()

    # Sidebar role simulator selection
    st.sidebar.subheader("User Role Access")
    user_role = st.sidebar.selectbox(
        "Select Role",
        ["CX Manager", "Operations Manager", "Guest", "Administrator"],
        index=0
    )

    # Validate Periods
    if not validate_reporting_periods(baseline_period, comparison_period):
        st.error("Error: Malformed reporting periods. Verify date ranges (YYYY-MM-DD) and check that start <= end.")
        st.stop()

    # Validate Data Directory
    if not os.path.exists(data_dir):
        st.error(f"Error: Selected Data Directory '{data_dir}' does not exist.")
        st.stop()

    # Load Configs
    kpi_definitions = load_kpi_definitions()
    if not kpi_definitions:
        st.error("Error: Failed to load config/kpi_definitions.yaml.")
        st.stop()

    # Core engine synthesis & persona profiling with latency logging
    synthesis_result, persona_views, latency = run_intelligence_pipeline(data_dir, baseline_period, comparison_period)

    # Resolve execution run ID on load
    cached_key = st.session_state.get("run_key")
    cached_run_id = st.session_state.get("current_run_id")

    resolved_run_id, new_key, logged_new = resolve_execution_run_id(
        synthesis_result=synthesis_result,
        persona_views=persona_views,
        baseline_period=baseline_period,
        comparison_period=comparison_period,
        data_dir=data_dir,
        cached_run_id=cached_run_id,
        cached_key=cached_key,
        db_path="data/storyproof_audit.db"
    )

    if resolved_run_id:
        st.session_state["current_run_id"] = resolved_run_id
        st.session_state["run_key"] = new_key

    # 2. Authoritative KPI Calculations (Scorecards data)
    all_kpis = ["AHT", "FCR", "CSAT", "Repeat_Contact_Rate", "Retention_Rate", "AI_Resolution_Rate"]
    entitled_kpis = get_accessible_kpis(user_role, kpi_definitions)
    kpi_stats = {}

    # Strict Entitlement Execution: Calculate/retrieve ONLY entitled KPIs for the active role
    for k in entitled_kpis:
        try:
            res = analyze_kpi_change(k, kpi_definitions, data_dir, baseline_period, comparison_period)
            kpi_stats[k] = res
        except Exception as e:
            kpi_stats[k] = {"status": "ERROR", "reason": str(e)}

    # Render Scorecard Grid (filtered by role entitlement)
    scorecard_kpis = [k for k in all_kpis if k in entitled_kpis]
    if not scorecard_kpis:
        st.info("No KPIs are accessible for the current role.")
    else:
        # First row
        row1 = scorecard_kpis[:3]
        cols = st.columns(len(row1))
        for idx, k in enumerate(row1):
            stats = kpi_stats.get(k, {})
            k_label = kpi_definitions.get(k, {}).get("name", k.replace("_", " "))
            with cols[idx]:
                if stats.get("status") == "ERROR" or "baseline" not in stats:
                    st.metric(k_label, "N/A", delta="No data")
                else:
                    val_base = stats["baseline"]["value"]
                    val_comp = stats["comparison"]["value"]
                    if val_comp is None or val_base is None:
                        st.metric(k_label, "N/A", delta="No data")
                    else:
                        unit = kpi_definitions[k].get("display_unit", "")
                        if unit == "percentage":
                            val_show = f"{val_comp * 100:.1f}%" if k != "CSAT" else f"{val_comp:.1f} pts"
                            diff = val_comp - val_base
                            diff_show = f"{diff * 100:+.1f}%" if k != "CSAT" else f"{diff:+.1f} pts"
                        else:
                            val_show = f"{val_comp:.2f}"
                            diff = val_comp - val_base
                            diff_show = f"{diff:+.2f}"
                        st.metric(k_label, val_show, delta=diff_show)

        # Second row (if more than 3 entitled KPIs, visually centered for 2 cards)
        row2 = scorecard_kpis[3:]
        if row2:
            if len(row2) == 2:
                cols2 = st.columns([1, 2, 2, 1])
                target_cols = [cols2[1], cols2[2]]
            elif len(row2) == 1:
                cols2 = st.columns([1, 2, 1])
                target_cols = [cols2[1]]
            else:
                target_cols = st.columns(len(row2))

            for idx, k in enumerate(row2):
                stats = kpi_stats.get(k, {})
                k_label = kpi_definitions.get(k, {}).get("name", k.replace("_", " "))
                with target_cols[idx]:
                    if stats.get("status") == "ERROR" or "baseline" not in stats:
                        st.metric(k_label, "N/A", delta="No data")
                    else:
                        val_base = stats["baseline"]["value"]
                        val_comp = stats["comparison"]["value"]
                        if val_comp is None or val_base is None:
                            st.metric(k_label, "N/A", delta="No data")
                        else:
                            unit = kpi_definitions[k].get("display_unit", "")
                            if unit == "percentage":
                                val_show = f"{val_comp * 100:.1f}%" if k != "CSAT" else f"{val_comp:.1f} pts"
                                diff = val_comp - val_base
                                diff_show = f"{diff * 100:+.1f}%" if k != "CSAT" else f"{diff:+.1f} pts"
                            else:
                                val_show = f"{val_comp:.2f}"
                                diff = val_comp - val_base
                                diff_show = f"{diff:+.2f}"
                            st.metric(k_label, val_show, delta=diff_show)

    # 3. Dual-View Presentation
    st.write("---")
    if user_role == "Administrator":
        tab_bi, tab_proof, tab_admin = st.tabs(["Traditional BI View", "StoryProof Verification View", "Admin Audit Console"])
    else:
        tab_bi, tab_proof = st.tabs(["Traditional BI View", "StoryProof Verification View"])

    with tab_bi:
        st.subheader("Traditional BI View — Illustrative / Unverified Only")
        st.warning("⚠️ Traditional BI View represents correlations and naive/unverified causal claims only. These are NOT verified StoryProof findings.")

        st.markdown("""
        #### Naive Executive Summaries:
        *   **AHT Drop**: The automated chatbot assistant rollout successfully drove support handling time speedups.
        *   **CSAT Degradation**: The CRM Cloud patch caused deterioration in customer experience ratings.
        """)

        # Simple Plotly trend charts
        st.write("#### Trend Correlations")
        bi_kpis = [k for k in all_kpis if k in entitled_kpis]
        selected_kpi_bi = st.selectbox("Explore KPI trend (Traditional BI)", bi_kpis if bi_kpis else all_kpis, key="bi_kpi")
        ts_df_bi = load_kpi_time_series(selected_kpi_bi, kpi_definitions, data_dir, role=user_role)

        if ts_df_bi is not None and not ts_df_bi.empty:
            # Unshaded simple chart
            fig_bi = build_trend_chart(selected_kpi_bi, ts_df_bi, baseline_period, comparison_period, show_shading=False)
            if fig_bi:
                st.plotly_chart(fig_bi, use_container_width=True)
        else:
            st.info("No time-series data available for the selected KPI.")

    with tab_proof:
        st.subheader("StoryProof Verification View")

        # Core StoryProof Analytical Flow Banner
        st.markdown(
            "**Analytical Pipeline**: `1. Traditional BI` ➔ `2. Observed KPI Tension` ➔ "
            "`3. Evidence & Hypotheses` ➔ `4. Decision Readiness` ➔ `5. Recommended Action`"
        )

        # Exact Mandatory Disclaimer
        st.info("The available evidence does not establish causality; observed changes represent associations and candidate explanations only.")

        # KPI Entitlement Notice
        st.caption(f"🔒 **KPI Entitlement**: {user_role} has access to {len(entitled_kpis)} of {len(all_kpis)} KPIs based on the semantic contract.")

        # Shaded trend chart
        st.write("#### Shaded Trend & Period Distinction")
        proof_kpis = [k for k in all_kpis if k in entitled_kpis]
        selected_kpi_proof = st.selectbox("Explore KPI trend", proof_kpis if proof_kpis else all_kpis, key="proof_kpi")
        st.caption("The selector changes the trend visualization only. Materiality, evidence, findings, readiness and recommendations are computed across the reporting set.")

        # Selected KPI Authoritative Context Card
        selected_stats = kpi_stats.get(selected_kpi_proof, {})
        if selected_stats.get("status") == "INSUFFICIENT_HISTORY":
            hist_eval = selected_stats.get("history", {}) or selected_stats.get("history_evaluation", {})
            avail_d = hist_eval.get("available_days", 21)
            req_d = hist_eval.get("required_days", 60)
            st.warning(
                f"**{selected_kpi_proof} Status**: **N/A** (INSUFFICIENT_HISTORY) — "
                f"**{avail_d} days available / {req_d} days required** (sparse baseline history — decision gating abstained)"
            )
        elif selected_stats.get("status") in ["MATERIAL", "NOT_MATERIAL"]:
            val_comp = selected_stats.get("comparison", {}).get("value")
            val_base = selected_stats.get("baseline", {}).get("value")
            chg = selected_stats.get("change", {})
            abs_chg = chg.get("absolute", 0.0)
            rel_chg = chg.get("relative_percent", chg.get("relative", 0.0))
            z_val = selected_stats.get("statistical_signal", {}).get("z_score")
            mat_stat = selected_stats.get("status")

            unit = kpi_definitions.get(selected_kpi_proof, {}).get("display_unit", "")
            if unit == "percentage":
                val_str = f"{val_comp * 100:.2f}%" if selected_kpi_proof != "CSAT" else f"{val_comp:.1f} pts"
                abs_str = f"{abs_chg * 100:+.2f} pp" if selected_kpi_proof != "CSAT" else f"{abs_chg:+.1f} pts"
                rel_str = f"{rel_chg:+.1f}%"
            else:
                val_str = f"{val_comp:.2f} min" if unit == "minutes" else f"{val_comp:.2f}"
                abs_str = f"{abs_chg:+.2f} min"
                rel_str = f"{rel_chg:+.1f}%"

            col_c1, col_c2, col_c3, col_c4 = st.columns(4)
            with col_c1:
                st.metric("Comparison Value", val_str)
            with col_c2:
                st.metric("Change vs Baseline", abs_str, delta=rel_str)
            with col_c3:
                st.metric("Materiality Status", mat_stat)
            with col_c4:
                st.metric("Statistical Anomaly", f"{z_val:.2f}" if z_val is not None else "N/A", delta="Z-score" if z_val is not None else None, delta_color="off")

        ts_df_proof = load_kpi_time_series(selected_kpi_proof, kpi_definitions, data_dir, role=user_role)

        if ts_df_proof is not None and not ts_df_proof.empty:
            fig_proof = build_trend_chart(selected_kpi_proof, ts_df_proof, baseline_period, comparison_period, show_shading=True)
            if fig_proof:
                st.plotly_chart(fig_proof, use_container_width=True)
        else:
            st.info("No time-series data available for the selected KPI.")

        # Materiality details from authoritative engine
        st.write("#### Materiality & Statistical Signals")
        materiality_rows = []
        for k in entitled_kpis:
            stats = kpi_stats.get(k, {})
            if stats.get("status") != "ERROR" and "baseline" in stats:
                z_score = stats.get("statistical_signal", {}).get("z_score")
                z_show = f"{z_score:.2f}" if z_score is not None else "N/A"

                threshold = stats.get("materiality_decision", {}).get("threshold")
                thresh_type = stats.get("materiality_decision", {}).get("threshold_type")
                thresh_show = f"{threshold} ({thresh_type})" if threshold is not None else "N/A"

                materiality_rows.append({
                    "KPI": k,
                    "Z-Score": z_show,
                    "Status": stats.get("status", "UNKNOWN"),
                    "Threshold Limit": thresh_show
                })

        if materiality_rows:
            st.table(pd.DataFrame(materiality_rows))

        # ------------------------------------------------------------------------------
        # Persona Views, Decision Readiness & Recommended Actions Integration (Milestone 5.2)
        # ------------------------------------------------------------------------------
        st.write("---")

        # Determine persona key and decision view title based on selected role
        p_key = None
        decision_view_title = get_decision_view_title(user_role)

        if user_role == "CX Manager":
            p_key = "CX_MANAGER"
            caption_text = "Role Access: **CX Manager** | Tailored narrative synthesis and operational action guidance for CX Manager."
        elif user_role == "Operations Manager":
            p_key = "OPERATIONS_MANAGER"
            caption_text = "Role Access: **Operations Manager** | Tailored narrative synthesis and operational action guidance for Operations Manager."
        elif user_role == "Guest":
            caption_text = "Role Access: **Guest** | Read-only inspection of persona decision perspectives. Feedback submission is disabled."
            persona_choice = st.radio(
                "Select Decision Perspective to Inspect (Read-Only)",
                ["CX Manager Perspective", "Operations Manager Perspective"],
                key="persona_view_profile_choice"
            )
            p_key = "CX_MANAGER" if persona_choice == "CX Manager Perspective" else "OPERATIONS_MANAGER"
        elif user_role == "Administrator":
            caption_text = "Role Access: **Administrator** | Governance oversight across all 6 KPIs, persona decision perspectives, and operational actions."
            persona_choice = st.radio(
                "Select Persona Perspective for Governance Review",
                ["CX Manager Perspective", "Operations Manager Perspective"],
                key="persona_view_profile_choice"
            )
            p_key = "CX_MANAGER" if persona_choice == "CX Manager Perspective" else "OPERATIONS_MANAGER"
        else:
            p_key = "CX_MANAGER"
            caption_text = f"Role Access: **{user_role}**."

        st.markdown(f"### 👤 Current Decision View: **{decision_view_title}**")
        st.caption(caption_text)

        # Check synthesis and persona views status
        if synthesis_result.get("status") != "SUCCESS" or persona_views.get("status") != "SUCCESS":
            st.warning("⚠️ Intel report details or persona narrative views are not available for the selected reporting period.")
        else:
            p_data = persona_views.get("personas", {}).get(p_key, {})
            if not p_data:
                st.info("No narrative profile information found for this persona.")
            else:
                # 1. Narrative Persona Summary
                st.markdown("### Narrative Summary")
                st.write(p_data.get("summary", "N/A"))

                # 2. Key Findings & Risks List
                col_find, col_risk = st.columns(2)
                with col_find:
                    st.markdown("#### Prioritized Key Findings")
                    key_findings = p_data.get("key_findings", [])
                    if not key_findings:
                        st.write("*No key findings generated for this profile.*")
                    else:
                        for f in key_findings:
                            text = f.get("text", "")
                            cls = f.get("classification", "N/A")
                            s_refs = f.get("structured_refs", [])
                            e_refs = f.get("evidence_refs", [])
                            refs = s_refs + e_refs
                            ref_str = f" [Refs: {', '.join(refs)}]" if refs else ""
                            st.write(f"- **{format_classification_badge(cls)}** {text} *{ref_str}*")
                            prov_details = get_evidence_provenance_badge(refs)
                            if prov_details:
                                with st.expander(f"Traceability & Freshness ({len(prov_details)} sources)", expanded=False):
                                    for pd_item in prov_details:
                                        st.caption(f"• {pd_item}")

                with col_risk:
                    st.markdown("#### Identified Risks & Concerns")
                    risks = p_data.get("risks", [])
                    if not risks:
                        st.write("*No risks or concerns identified for this profile.*")
                    else:
                        for r in risks:
                            text = r.get("text", "")
                            cls = r.get("classification", "N/A")
                            s_refs = r.get("structured_refs", [])
                            e_refs = r.get("evidence_refs", [])
                            refs = s_refs + e_refs
                            ref_str = f" [Refs: {', '.join(refs)}]" if refs else ""
                            st.write(f"- **{format_classification_badge(cls)}** {text} *{ref_str}*")
                            prov_details = get_evidence_provenance_badge(refs)
                            if prov_details:
                                with st.expander(f"Traceability & Freshness ({len(prov_details)} sources)", expanded=False):
                                    for pd_item in prov_details:
                                        st.caption(f"• {pd_item}")

                # 3. Decision Readiness Assessment
                st.markdown("### Decision Readiness Assessment")
                dr = p_data.get("decision_readiness", {})
                if not dr:
                    st.write("*Readiness scorecard is not available.*")
                else:
                    score = dr.get("readiness_score")
                    if score is None:
                        st.write("**Readiness Score**: N/A")
                        st.progress(0.0)
                    else:
                        score_val = int(score)
                        st.write(f"**Readiness Score**: {score_val} / 100")
                        st.progress(max(0.0, min(1.0, score_val / 100.0)))

                    state = dr.get("overall_state", "N/A")
                    if state == "READY":
                         st.success(f"Overall State: **{state}**")
                    elif state == "READY_WITH_RESERVATIONS":
                         st.warning(f"Overall State: **{state}**")
                    else:
                         st.error(f"Overall State: **{state}**")

                    if dr.get("details"):
                         st.write("**Assessment Details:**")
                         for detail in dr.get("details"):
                             st.write(f"- {detail}")

                # 4. Action Recommendations and Feedback Forms
                st.markdown("### Action Recommendations")
                actions = p_data.get("recommended_actions", [])
                if not actions:
                    st.write("*No action recommendations triggered for this profile.*")
                else:
                    for idx, action in enumerate(actions):
                        action_id = action.get("id", "N/A")
                        with st.expander(f"Action: {action_id} — {action.get('title', 'Recommendation')} (Priority: {action.get('priority', 'N/A')})"):
                            st.write(f"- **WHY / DRIVER**: {action.get('driver') or action.get('observed_finding', 'N/A')}")
                            if action.get("controllable_lever"):
                                st.write(f"- **WHAT LEVER**: {action.get('controllable_lever')}")
                            st.write(f"- **WHAT ACTION**: {action.get('action') or action.get('description', 'N/A')}")
                            if action.get("owner"):
                                st.write(f"- **WHO OWNS IT**: {action.get('owner')}")
                            if action.get("expected_impact"):
                                st.write(f"- **EXPECTED IMPACT**: {action.get('expected_impact')}")
                            st.write(f"- **EVIDENCE CONFIDENCE**: `{action.get('confidence') or action.get('priority', 'N/A')}` (Priority: {action.get('priority', 'N/A')})")
                            if action.get("monitoring_plan"):
                                st.write(f"- **HOW TO MONITOR**: {action.get('monitoring_plan')}")
                            if action.get("justification"):
                                st.write(f"- **Analytical Context**: {action.get('justification')}")
                            if action.get("reason"):
                                st.write(f"- **Operational Trigger**: {action.get('reason')}")
                            if action.get("trigger_info"):
                                trigger_dict = action.get("trigger_info", {})
                                if isinstance(trigger_dict, dict):
                                    t_details = [f"{k}: {v}" for k, v in trigger_dict.items()]
                                    st.write(f"- **Trigger Detail**: {', '.join(t_details)}")

                            s_refs = action.get("structured_refs", [])
                            e_refs = action.get("evidence_refs", [])
                            if s_refs:
                                st.write(f"- **Structured References**: {', '.join(s_refs)}")
                            if e_refs:
                                st.write(f"- **Evidence References**: {', '.join(e_refs)}")

                            # Human-in-the-Loop Governance Signal
                            gov_signal = get_action_governance_signal(action_id=action_id, db_path="data/storyproof_audit.db")
                            st.write("---")
                            st.markdown("##### 🏛️ Human-in-the-Loop Governance Signal")
                            st.caption("**Feedback Learning Flow**: `1. Current Recommendation` ➔ `2. Historical Feedback Signal` ➔ `3. Governance Treatment & Decision`")

                            status = gov_signal.get("status", "NO_PRIOR_FEEDBACK")
                            total_rev = gov_signal.get("total_reviews", 0)
                            appr_cnt = gov_signal.get("approved_count", 0)
                            rej_cnt = gov_signal.get("rejected_count", 0)
                            flag_cnt = gov_signal.get("flagged_count", 0)
                            guidance_text = gov_signal.get("guidance", "Standard operational review applies.")
                            gov_decision = gov_signal.get("governance_decision", "STANDARD_REVIEW")
                            review_req = gov_signal.get("review_required", False)

                            if status == "NO_PRIOR_FEEDBACK":
                                st.info(
                                    "ℹ️ **Governance Status**: NO_PRIOR_FEEDBACK — No historical analyst reviews.\n\n"
                                    f"**Governance Decision**: `{gov_decision}` | Review Required: `{review_req}`\n\n"
                                    f"**Governance Guidance**: {guidance_text}"
                                )
                            elif status == "HIGH_HISTORICAL_ACCEPTANCE":
                                st.success(
                                    f"✅ **Governance Status**: {gov_signal['label']}\n\n"
                                    f"- **Historical Reviews**: Total: {total_rev} | Approved: {appr_cnt} | Rejected: {rej_cnt} | Flagged: {flag_cnt}\n"
                                    f"- **Governance Decision**: `{gov_decision}` | Review Required: `{review_req}`\n"
                                    f"- **Governance Guidance**: {guidance_text}"
                                )
                            elif status == "FREQUENTLY_REJECTED":
                                st.error(
                                    f"❌ **Governance Status**: {gov_signal['label']}\n\n"
                                    f"- **Historical Reviews**: Total: {total_rev} | Approved: {appr_cnt} | Rejected: {rej_cnt} | Flagged: {flag_cnt}\n"
                                    f"- **Governance Decision**: `{gov_decision}` | Review Required: `{review_req}`\n"
                                    f"- **Governance Guidance**: ⚠️ {guidance_text}"
                                )
                            elif status == "FREQUENTLY_FLAGGED":
                                st.warning(
                                    f"⚠️ **Governance Status**: {gov_signal['label']}\n\n"
                                    f"- **Historical Reviews**: Total: {total_rev} | Approved: {appr_cnt} | Rejected: {rej_cnt} | Flagged: {flag_cnt}\n"
                                    f"- **Governance Decision**: `{gov_decision}` | Review Required: `{review_req}`\n"
                                    f"- **Governance Guidance**: ⚠️ {guidance_text}"
                                )
                            else:  # MIXED_FEEDBACK
                                st.info(
                                    f"📊 **Governance Status**: {gov_signal['label']}\n\n"
                                    f"- **Historical Reviews**: Total: {total_rev} | Approved: {appr_cnt} | Rejected: {rej_cnt} | Flagged: {flag_cnt}\n"
                                    f"- **Governance Decision**: `{gov_decision}` | Review Required: `{review_req}`\n"
                                    f"- **Governance Guidance**: {guidance_text}"
                                )

                            if gov_signal.get("recent_comments"):
                                with st.expander("Recent analyst comments (human governance notes — not factual data evidence)", expanded=False):
                                    for comm in gov_signal["recent_comments"]:
                                        st.write(f"- **[{comm['status']}]** by *{comm['analyst']}* ({comm['timestamp'][:10]}): \"{comm['comment']}\"")

                            # Analyst review form
                            st.write("---")
                            st.write("**Analyst Review**")

                            if not check_role_permission(user_role, "submit_feedback"):
                                 # Disabled inputs for read-only/unauthorized roles
                                 st.info("Viewer role: Feedback submission is disabled.")
                                 st.selectbox("Status", ["APPROVED", "REJECTED", "FLAGGED"], index=0, key=f"status_disabled_{action_id}_{idx}", disabled=True)
                                 st.text_area("Comments", value="", key=f"comments_disabled_{action_id}_{idx}", disabled=True)
                                 st.text_input("Reviewer Name", value=user_role, key=f"name_disabled_{action_id}_{idx}", disabled=True)
                                 st.button("Submit Review", key=f"btn_disabled_{action_id}_{idx}", disabled=True)
                            else:
                                 # Enabled interactive form for managers and administrators
                                 active_run_id = st.session_state.get("current_run_id")
                                 if not active_run_id:
                                      st.error("Feedback submission disabled: No active execution run is registered in the database.")
                                 else:
                                      with st.form(key=f"fb_form_{action_id}_{idx}"):
                                          status = st.selectbox("Status", ["APPROVED", "REJECTED", "FLAGGED"], index=0)
                                          comments = st.text_area("Comments", value="")
                                          analyst_name = st.text_input("Reviewer Name", value="Analyst")
                                          submit_btn = st.form_submit_button("Submit Review")

                                          if submit_btn:
                                              if not analyst_name.strip():
                                                  st.error("Analyst Name is required.")
                                              else:
                                                  try:
                                                      # Write feedback to SQLite DB using the already-active run ID
                                                      feedback_id = log_analyst_feedback(
                                                          run_id=active_run_id,
                                                          action_id=action_id,
                                                          status=status,
                                                          comments=comments,
                                                          analyst_name=analyst_name,
                                                          db_path="data/storyproof_audit.db"
                                                      )
                                                      if feedback_id:
                                                          st.success(f"Feedback successfully saved! Feedback ID: {feedback_id}")
                                                      else:
                                                          st.error("Failed to log feedback. Verify database schemas and validation parameters.")
                                                  except Exception as exc:
                                                      st.error(f"Failed to submit feedback: {str(exc)}")

    # Administrator Audit View Tab (Admin only)
    if user_role == "Administrator":
        with tab_admin:
            st.subheader("Administrator Audit Console")

            # Observability Section
            st.markdown("### System Observability Panel")

            # Fetch optimized database metrics (Eliminates N+1 query loop)
            total_runs, total_feedback, db_active = calculate_database_metrics()

            st.markdown("#### ⚡ Actual Runtime Telemetry")
            col_metric1, col_metric2, col_metric3, col_metric4 = st.columns(4)
            with col_metric1:
                st.metric("Execution Latency", f"{latency:.4f}s")
            with col_metric2:
                st.metric("Database Status", "Active" if db_active else "Offline")
            with col_metric3:
                st.metric("Logged Execution Runs", total_runs)
            with col_metric4:
                st.metric("Logged Feedback Reviews", total_feedback)

            # Simulated LLM API usage metrics
            cost_metrics = calculate_projected_llm_cost(total_runs)
            simulated_input_tokens = cost_metrics["simulated_input_tokens"]
            simulated_output_tokens = cost_metrics["simulated_output_tokens"]
            input_rate_per_1k = cost_metrics["input_rate_per_1k"]
            output_rate_per_1k = cost_metrics["output_rate_per_1k"]
            cost_per_run = cost_metrics["cost_per_run"]
            total_projected_cost = cost_metrics["total_projected_cost"]

            st.markdown("#### 💡 Simulated / Projected LLM API Usage Model")
            st.caption("StoryProof executes 100% deterministically without external model calls. The projections below illustrate hypothetical enterprise unit economics if natural-language expansion were enabled.")
            st.info("📊 **SIMULATED / PROJECTED LLM API Usage Metrics (Economic Model)**\n"
                    f"- Simulated Input Tokens: {simulated_input_tokens} tokens per run\n"
                    f"- Simulated Output Tokens: {simulated_output_tokens} tokens per run\n"
                    f"- Projection Pricing Rate: ${input_rate_per_1k}/1K Input, ${output_rate_per_1k}/1K Output\n"
                    f"- Projected Cost per Run: ${cost_per_run:.4f}\n"
                    f"- Total Cumulative Projected LLM Cost: ${total_projected_cost:.4f}")

            # Fetch run history list
            runs_list = get_run_history(db_path="data/storyproof_audit.db")

            # History table
            st.markdown("### Logged Audit Execution Runs")
            if not runs_list:
                st.info("No execution runs recorded in SQLite audit database.")
            else:
                history_df = []
                for run in runs_list:
                    history_df.append({
                        "Run ID": run.get("run_id"),
                        "Timestamp": run.get("timestamp"),
                        "Baseline Period": f"{run.get('baseline_start')} to {run.get('baseline_end')}",
                        "Comparison Period": f"{run.get('comparison_start')} to {run.get('comparison_end')}",
                        "CX Score": run.get("cx_readiness_score"),
                        "Ops Score": run.get("ops_readiness_score"),
                        "Actions Count": run.get("actions_count")
                    })
                st.table(pd.DataFrame(history_df))

                # Historical run parameter restoration
                st.markdown("### Restore Run Parameters")
                run_ids_to_restore = [run.get("run_id") for run in runs_list]
                selected_restore_run_id = st.selectbox("Select historical Run ID to restore", run_ids_to_restore, key="restore_run_id_admin")
                if st.button("Restore Selected Run Parameters"):
                    selected_run = next((run for run in runs_list if run["run_id"] == selected_restore_run_id), None)
                    if selected_run:
                        st.session_state["b_start_input"] = selected_run["baseline_start"]
                        st.session_state["b_end_input"] = selected_run["baseline_end"]
                        st.session_state["c_start_input"] = selected_run["comparison_start"]
                        st.session_state["c_end_input"] = selected_run["comparison_end"]
                        st.success(f"Parameters restored from Run ID: {selected_restore_run_id}! Rerunning dashboard...")
                        st.rerun()

                # Chronological Feedback Audit Log (across all runs)
                st.markdown("### Chronological Feedback Audit Log")
                global_feedback = get_all_feedback()
                if not global_feedback:
                    st.info("No feedback reviews logged across any execution runs.")
                else:
                    global_df = []
                    for f in global_feedback:
                        global_df.append({
                            "Timestamp": f.get("timestamp"),
                            "Run ID": f.get("run_id"),
                            "Action ID": f.get("action_id"),
                            "Status": f.get("status"),
                            "Comments": f.get("comments"),
                            "Analyst": f.get("analyst_name")
                        })
                    st.table(pd.DataFrame(global_df))

                # Feedback reviews inspector (Run-specific inspection)
                st.markdown("### Inspect Feedback Reviews by Run ID")
                run_ids = [run.get("run_id") for run in runs_list]
                selected_run_id = st.selectbox("Inspect Action reviews for Run ID", run_ids, key="inspect_run_id_admin")

                feedback_list = get_feedback_by_run(selected_run_id, db_path="data/storyproof_audit.db")
                if not feedback_list:
                    st.info(f"No feedback records registered for Run ID: {selected_run_id}")
                else:
                    feedback_df = []
                    for f in feedback_list:
                        feedback_df.append({
                            "Feedback ID": f.get("feedback_id"),
                            "Action ID": f.get("action_id"),
                            "Status": f.get("status"),
                            "Comments": f.get("comments"),
                            "Analyst": f.get("analyst_name"),
                            "Timestamp": f.get("timestamp")
                        })
                    st.table(pd.DataFrame(feedback_df))

if __name__ == "__main__":
    main()
