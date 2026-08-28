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
    get_feedback_by_run
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

def load_kpi_time_series(kpi_name, kpi_definitions, data_dir):
    """
    Loads raw CSV data for a KPI and formats it to ['date', 'value'] columns,
    following the authoritative configuration mapping. Returns None on missing/malformed inputs.
    Does not mutate input arguments.
    """
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

    df_copy = df.copy()
    try:
        df_copy['date_parsed'] = pd.to_datetime(df_copy[date_col])
    except (ValueError, TypeError, KeyError):
        return None

    # Calculate row-wise values based on contract
    agg_method = kpi_def.get("aggregation_method", "weighted_average")
    num_field = kpi_def.get("numerator_field")
    den_field = kpi_def.get("denominator_field")

    # 1. Special Case: CSAT
    if kpi_name == "CSAT" and agg_method == "weighted_average":
        if "csat_score" not in df_copy.columns:
            return None
        df_copy['value'] = df_copy["csat_score"]
    # 2. General Weighted Average / Ratio-based KPIs
    elif agg_method == "weighted_average" and num_field in df_copy.columns and den_field in df_copy.columns:
        # Compute row-wise ratio
        df_copy['value'] = df_copy[num_field] / df_copy[den_field]
        df_copy['value'] = df_copy['value'].fillna(0.0)

        # Unit Conversions
        raw_unit = kpi_def.get("raw_unit")
        display_unit = kpi_def.get("display_unit")
        if raw_unit == "seconds" and display_unit == "minutes":
            df_copy['value'] /= 60.0
    else:
        # Simple column fallback
        val_col = kpi_def.get("value_column", kpi_name)
        col_to_use = None
        col_candidates = [val_col, kpi_name, kpi_name.lower(), "val", "value", "score", "rate", "resolution_rate"]
        for candidate in col_candidates:
            if candidate and candidate in df_copy.columns:
                col_to_use = candidate
                break
        if col_to_use is None:
            # Look for any numeric col
            for col in df_copy.columns:
                if col not in ["date", "date_parsed", "week_start", "month"] and pd.api.types.is_numeric_dtype(df_copy[col]):
                    col_to_use = col
                    break
        if col_to_use is None:
            return None

        df_copy['value'] = df_copy[col_to_use]
        # Scale resolution_rate
        if kpi_def.get("display_unit") == "percentage" and df_copy['value'].mean() > 1.0:
            df_copy['value'] /= 100.0

    # Clean output DataFrame
    try:
        res_df = df_copy[['date_parsed', 'value']].copy()
        res_df.columns = ['date', 'value']
        res_df = res_df.dropna().sort_values('date')
        return res_df
    except (KeyError, ValueError, TypeError):
        return None

def build_trend_chart(kpi_name, kpi_df, baseline_period, comparison_period, show_shading=True):
    """
    Builds a Plotly trend chart for the KPI.
    Shades baseline and comparison ranges in gray if show_shading is True.
    """
    if kpi_df is None or kpi_df.empty:
        return None

    fig = px.line(kpi_df, x="date", y="value", title=f"{kpi_name} Over Time")

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
    - 'submit_feedback': CX Manager, Operations Manager
    - 'view_observability': Administrator
    - 'view_history': Administrator
    """
    if permission_type == "view_cx":
        return role in ["CX Manager", "Guest", "Administrator"]
    if permission_type == "view_ops":
        return role in ["Operations Manager", "Guest", "Administrator"]
    if permission_type == "submit_feedback":
        return role in ["CX Manager", "Operations Manager"]
    if permission_type == "view_observability":
        return role in ["Administrator"]
    if permission_type == "view_history":
        return role in ["Administrator"]
    return False

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

def main():
    st.title("StoryProof")
    st.subheader("Evidence-first KPI Intelligence")
    st.caption("Prototype v0.1")

    # 1. Sidebar Configurations
    st.sidebar.header("Configuration")
    data_dir = st.sidebar.text_input("Data Directory", "data")

    st.sidebar.subheader("Baseline Period")
    b_start = st.sidebar.text_input("Baseline Start", "2026-01-01")
    b_end = st.sidebar.text_input("Baseline End", "2026-03-31")

    st.sidebar.subheader("Comparison Period")
    c_start = st.sidebar.text_input("Comparison Start", "2026-06-01")
    c_end = st.sidebar.text_input("Comparison End", "2026-06-30")

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

    # 2. Authoritative KPI Calculations (Scorecards data)
    kpis = ["AHT", "FCR", "CSAT", "Repeat_Contact_Rate", "Retention_Rate", "AI_Resolution_Rate"]
    kpi_stats = {}

    for k in kpis:
        try:
            res = analyze_kpi_change(k, kpi_definitions, data_dir, baseline_period, comparison_period)
            kpi_stats[k] = res
        except Exception as e:
            kpi_stats[k] = {"status": "ERROR", "reason": str(e)}

    # Render Scorecard Grid
    cols = st.columns(3)
    for idx, k in enumerate(kpis[:3]):
        stats = kpi_stats.get(k, {})
        with cols[idx]:
            if stats.get("status") == "ERROR" or "baseline" not in stats:
                st.metric(k, "N/A", delta="No data")
            else:
                val_base = stats["baseline"]["value"]
                val_comp = stats["comparison"]["value"]
                if val_comp is None or val_base is None:
                    st.metric(k, "N/A", delta="No data")
                else:
                    # Unit formatting
                    unit = kpi_definitions[k].get("display_unit", "")
                    if unit == "percentage":
                        val_show = f"{val_comp * 100:.1f}%" if k != "CSAT" else f"{val_comp:.1f}%"
                        diff = val_comp - val_base
                        diff_show = f"{diff * 100:+.1f}%" if k != "CSAT" else f"{diff:+.1f}%"
                    else:
                        val_show = f"{val_comp:.2f}"
                        diff = val_comp - val_base
                        diff_show = f"{diff:+.2f}"

                    st.metric(k, val_show, delta=diff_show)

    cols2 = st.columns(3)
    for idx, k in enumerate(kpis[3:]):
        stats = kpi_stats.get(k, {})
        with cols2[idx]:
            if stats.get("status") == "ERROR" or "baseline" not in stats:
                st.metric(k, "N/A", delta="No data")
            else:
                val_base = stats["baseline"]["value"]
                val_comp = stats["comparison"]["value"]
                if val_comp is None or val_base is None:
                    st.metric(k, "N/A", delta="No data")
                else:
                    unit = kpi_definitions[k].get("display_unit", "")
                    if unit == "percentage":
                        val_show = f"{val_comp * 100:.1f}%"
                        diff = val_comp - val_base
                        diff_show = f"{diff * 100:+.1f}%"
                    else:
                        val_show = f"{val_comp:.2f}"
                        diff = val_comp - val_base
                        diff_show = f"{diff:+.2f}"

                    st.metric(k, val_show, delta=diff_show)

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
        selected_kpi_bi = st.selectbox("Select KPI to view (Traditional BI)", kpis, key="bi_kpi")
        ts_df_bi = load_kpi_time_series(selected_kpi_bi, kpi_definitions, data_dir)

        if ts_df_bi is not None and not ts_df_bi.empty:
            # Unshaded simple chart
            fig_bi = build_trend_chart(selected_kpi_bi, ts_df_bi, baseline_period, comparison_period, show_shading=False)
            if fig_bi:
                st.plotly_chart(fig_bi, use_container_width=True)
        else:
            st.info("No time-series data available for the selected KPI.")

    with tab_proof:
        st.subheader("StoryProof Verification View")

        # Exact Mandatory Disclaimer
        st.info("The available evidence does not establish causality; observed changes represent associations and candidate explanations only.")

        # Shaded trend chart
        st.write("#### Shaded Trend & Period Distinction")
        selected_kpi_proof = st.selectbox("Select KPI to view (StoryProof)", kpis, key="proof_kpi")
        ts_df_proof = load_kpi_time_series(selected_kpi_proof, kpi_definitions, data_dir)

        if ts_df_proof is not None and not ts_df_proof.empty:
            fig_proof = build_trend_chart(selected_kpi_proof, ts_df_proof, baseline_period, comparison_period, show_shading=True)
            if fig_proof:
                st.plotly_chart(fig_proof, use_container_width=True)
        else:
            st.info("No time-series data available for the selected KPI.")

        # Materiality details from authoritative engine
        st.write("#### Materiality & Statistical Signals")
        materiality_rows = []
        for k in kpis:
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

        # Determine persona key based on selected role
        p_key = None
        if user_role == "CX Manager":
            p_key = "CX_MANAGER"
        elif user_role == "Operations Manager":
            p_key = "OPERATIONS_MANAGER"
        elif user_role in ["Guest", "Administrator"]:
            # Dropdown/Selector inside the StoryProof Tab to inspect different persona viewpoints
            persona_choice = st.radio("Select View Profile Perspective", ["CX Manager Perspective", "Operations Manager Perspective"], key="persona_view_profile_choice")
            if persona_choice == "CX Manager Perspective":
                p_key = "CX_MANAGER"
            else:
                p_key = "OPERATIONS_MANAGER"

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
                            st.write(f"- **[{cls}]** {text} *{ref_str}*")

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
                            st.write(f"- **[{cls}]** {text} *{ref_str}*")

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
                            st.write(f"**Type**: {action.get('action_type', 'N/A')}")
                            st.write(f"**Description**: {action.get('description', 'N/A')}")
                            st.write(f"**Observed Finding**: {action.get('observed_finding', 'N/A')}")
                            st.write(f"**Justification**: {action.get('justification', 'N/A')}")

                            s_refs = action.get("structured_refs", [])
                            e_refs = action.get("evidence_refs", [])
                            if s_refs:
                                 st.write(f"**Structured References**: {', '.join(s_refs)}")
                            if e_refs:
                                 st.write(f"**Evidence References**: {', '.join(e_refs)}")

                            # Analyst review form
                            st.write("---")
                            st.write("**Analyst Review**")

                            if not check_role_permission(user_role, "submit_feedback"):
                                 # Disabled inputs for read-only/unauthorized roles
                                 st.selectbox("Status", ["APPROVED", "REJECTED", "FLAGGED"], index=0, key=f"status_disabled_{action_id}_{idx}", disabled=True)
                                 st.text_input("Comments", value="", key=f"comments_disabled_{action_id}_{idx}", disabled=True)
                                 st.text_input("Reviewer Name", value=user_role, key=f"name_disabled_{action_id}_{idx}", disabled=True)
                                 st.button("Submit Feedback", key=f"btn_disabled_{action_id}_{idx}", disabled=True)
                            else:
                                 # Enabled interactive form for managers
                                 with st.form(key=f"fb_form_{action_id}_{idx}"):
                                     status = st.selectbox("Status", ["APPROVED", "REJECTED", "FLAGGED"], index=0)
                                     comments = st.text_input("Comments", value="")
                                     analyst_name = st.text_input("Reviewer Name", value="Analyst")
                                     submit_btn = st.form_submit_button("Submit Feedback")

                                     if submit_btn:
                                         if not analyst_name.strip():
                                             st.error("Analyst Name is required.")
                                         else:
                                             try:
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

                                                 if logged_new and resolved_run_id:
                                                     st.session_state["current_run_id"] = resolved_run_id
                                                     st.session_state["run_key"] = new_key
                                                 elif not resolved_run_id and not cached_run_id:
                                                     st.error("Failed to register execution run in audit database.")

                                                 cached_run_id = resolved_run_id

                                                 if cached_run_id:
                                                     # Write feedback to SQLite DB
                                                     feedback_id = log_analyst_feedback(
                                                         run_id=cached_run_id,
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
            st.write(f"**Execution Latency**: {latency:.4f} seconds")

            # Database stats
            runs_list = get_run_history(db_path="data/storyproof_audit.db")
            total_runs = len(runs_list)
            total_feedback = 0
            for r in runs_list:
                try:
                    f_list = get_feedback_by_run(r["run_id"], db_path="data/storyproof_audit.db")
                    total_feedback += len(f_list)
                except:
                    pass

            st.write(f"**Database Status**: {'Initialized' if db_initialized else 'Initialization Failed'}")
            st.write(f"**Logged Execution Runs**: {total_runs}")
            st.write(f"**Logged Feedback Reviews**: {total_feedback}")

            # Simulated LLM API usage metrics
            cost_metrics = calculate_projected_llm_cost(total_runs)
            simulated_input_tokens = cost_metrics["simulated_input_tokens"]
            simulated_output_tokens = cost_metrics["simulated_output_tokens"]
            input_rate_per_1k = cost_metrics["input_rate_per_1k"]
            output_rate_per_1k = cost_metrics["output_rate_per_1k"]
            cost_per_run = cost_metrics["cost_per_run"]
            total_projected_cost = cost_metrics["total_projected_cost"]

            st.info("💡 **SIMULATED / PROJECTED LLM API Usage Metrics**\n"
                    f"- Simulated Input Tokens: {simulated_input_tokens} tokens per run\n"
                    f"- Simulated Output Tokens: {simulated_output_tokens} tokens per run\n"
                    f"- Projection Pricing Rate: ${input_rate_per_1k}/1K Input, ${output_rate_per_1k}/1K Output\n"
                    f"- Projected Cost per Run: ${cost_per_run:.4f}\n"
                    f"- Total Cumulative Projected LLM Cost: ${total_projected_cost:.4f}")

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

                # Feedback reviews inspector
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
