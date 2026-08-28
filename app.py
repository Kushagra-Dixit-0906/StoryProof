import streamlit as st
import os
import re
import datetime
import pandas as pd
import yaml
from src.engine.materiality import calculate_kpi_value, analyze_kpi_change, load_yaml
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

if __name__ == "__main__":
    main()
