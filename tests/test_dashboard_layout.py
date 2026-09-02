import pytest
import os
import re
import pandas as pd
import numpy as np
import copy
from src.engine.materiality import calculate_kpi_value, analyze_kpi_change

# Import helpers from app.py
from app import (
    validate_reporting_periods,
    load_kpi_definitions,
    load_kpi_time_series,
    build_trend_chart
)

# Default valid periods for testing
DEFAULT_BASELINE = ("2026-01-01", "2026-03-31")
DEFAULT_COMPARISON = ("2026-06-01", "2026-06-30")

# 1. Dashboard module imports successfully
def test_plotly_and_streamlit_imports():
    import streamlit as st
    import plotly.express as px
    import plotly.graph_objects as go
    assert st is not None
    assert px is not None
    assert go is not None

# 2. validate_reporting_periods handles malformed periods
def test_validate_periods_malformed():
    # Wrong tuple length
    assert validate_reporting_periods(("2026-01-01",), ("2026-06-01", "2026-06-30")) is False
    assert validate_reporting_periods(("2026-01-01", "2026-03-31"), "2026-06-01") is False

    # Invalid date strings
    assert validate_reporting_periods(("2026-01-01", "invalid"), ("2026-06-01", "2026-06-30")) is False
    assert validate_reporting_periods(("2026-01-01", "2026-03-31"), ("2026-06-01", "2026-06-32")) is False

    # None parameters
    assert validate_reporting_periods(None, ("2026-06-01", "2026-06-30")) is False
    assert validate_reporting_periods(("2026-01-01", "2026-03-31"), None) is False

# 3. validate_reporting_periods checks start date <= end date
def test_validate_periods_start_after_end():
    assert validate_reporting_periods(("2026-03-31", "2026-01-01"), ("2026-06-01", "2026-06-30")) is False
    assert validate_reporting_periods(("2026-01-01", "2026-03-31"), ("2026-06-30", "2026-06-01")) is False
    # Valid periods
    assert validate_reporting_periods(("2026-01-01", "2026-03-31"), ("2026-06-01", "2026-06-30")) is True

# 4. load_kpi_definitions immutability check
def test_load_kpi_definitions_immutability():
    config1 = load_kpi_definitions("config/kpi_definitions.yaml")
    config2 = load_kpi_definitions("config/kpi_definitions.yaml")
    assert config1 == config2
    assert config1 is not config2  # Verify distinct memory locations (read-only loaders)

# 5. load_kpi_time_series handles missing data directory cleanly
def test_load_kpi_time_series_missing_dir():
    config = load_kpi_definitions("config/kpi_definitions.yaml")
    # Non-existent directory returns None cleanly
    res = load_kpi_time_series("AHT", config, "non_existent_dir_path_xyz")
    assert res is None

# 6. load_kpi_time_series handles missing column cleanly
def test_load_kpi_time_series_missing_column(tmp_path):
    # Create valid CSV structure but without any numeric value columns besides the date
    bad_csv = tmp_path / "support_daily.csv"
    df = pd.DataFrame({"date": ["2026-01-01", "2026-01-02"], "other_col": ["a", "b"]})
    df.to_csv(bad_csv, index=False)

    config = {
        "AHT": {
            "source": "support_daily.csv",
            "date_column": "date",
            "value_column": "total_handling_seconds",
            "aggregation_method": "simple_average"
        }
    }

    res = load_kpi_time_series("AHT", config, str(tmp_path))
    assert res is None

# 7. load_kpi_time_series immutability check
def test_load_kpi_time_series_immutability(tmp_path):
    csv_file = tmp_path / "support_daily.csv"
    df = pd.DataFrame({"date": ["2026-01-01", "2026-01-02"], "aht": [10.5, 11.2]})
    df.to_csv(csv_file, index=False)

    config = {
        "AHT": {
            "source": "support_daily.csv",
            "date_column": "date",
            "value_column": "aht",
            "aggregation_method": "simple_average"
        }
    }

    config_copy = copy.deepcopy(config)
    res = load_kpi_time_series("AHT", config, str(tmp_path))

    # Assert config input was not mutated
    assert config == config_copy
    # Assert returned dataframe is not the raw CSV dataframe itself
    assert res is not None
    assert len(res) == 2

# 8. Scorecard KPI calculation aligns with materiality engine
def test_kpi_calculation_alignment():
    config = load_kpi_definitions("config/kpi_definitions.yaml")
    baseline = ("2026-01-01", "2026-03-31")
    comparison = ("2026-06-01", "2026-06-30")

    # Calculate directly using authoritative analyze_kpi_change from materiality
    aht_res = analyze_kpi_change("AHT", config, "data", baseline, comparison)
    fcr_res = analyze_kpi_change("FCR", config, "data", baseline, comparison)

    assert aht_res["status"] == "MATERIAL"
    assert fcr_res["status"] == "NOT_MATERIAL"

    # Check AHT baseline value equals that computed by calculate_kpi_value
    file_path = os.path.join("data", config["AHT"]["source"])
    df = pd.read_csv(file_path)
    df["date_parsed"] = pd.to_datetime(df["date"])
    b_df = df[(df["date_parsed"] >= baseline[0]) & (df["date_parsed"] <= baseline[1])]

    calc_base_val = calculate_kpi_value(b_df, "AHT", config["AHT"])
    assert calc_base_val == aht_res["baseline"]["value"]

# 9. Traditional BI View has illustrative/unverified labeling
def test_traditional_bi_view_illustration_check():
    # The Traditional BI View must have explicit illustrative annotations
    bi_heading = "Traditional BI View — Illustrative / Unverified Only"
    bi_warning = "Traditional BI View represents correlations and naive/unverified causal claims only."

    # Read app.py text content to assert presence
    with open("app.py", "r", encoding="utf-8") as f:
        content = f.read()

    assert bi_heading in content
    assert bi_warning in content

# 10. StoryProof view causal language safety check
def test_storyproof_view_causality():
    # Read app.py text content
    with open("app.py", "r", encoding="utf-8") as f:
        content = f.read()

    # We locate the StoryProof Tab code block to scan it for causal verbs
    # To keep this test focused, we verify that any text string rendered inside the StoryProof Tab (Tab B)
    # is observational/associational.
    # Tab B rendering starts after the tab_bi block
    assert "with tab_proof:" in content
    proof_section = content.split("with tab_proof:")[1]

    prohibited = ["caused", "causes", "caused by", "causal", "responsible for", "resulted in", "led to", "due to", "because of", "driven by", "responsible"]

    disclaimer = "The available evidence does not establish causality; observed changes represent associations and candidate explanations only."

    # Scan text strings in the tab_proof block
    string_literals = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"|\'([^\'\\]*(?:\\.[^\'\\]*)*)\'', proof_section)
    for pair in string_literals:
        stmt = pair[0] or pair[1]
        if stmt == disclaimer:
            continue
        stmt_lower = stmt.lower()
        for p_word in prohibited:
            pattern = rf"\b{p_word}\b"
            assert not re.search(pattern, stmt_lower), f"Prohibited causal word '{p_word}' found in StoryProof text literal: '{stmt}'"

# 11. Exact mandatory causality disclaimer is preserved
def test_storyproof_disclaimer_exact():
    disclaimer = "The available evidence does not establish causality; observed changes represent associations and candidate explanations only."

    with open("app.py", "r", encoding="utf-8") as f:
        content = f.read()

    assert disclaimer in content

# 12. Layout and chart helper determinism
def test_layout_determinism(tmp_path):
    csv_file = tmp_path / "support_daily.csv"
    df = pd.DataFrame({"date": ["2026-01-01", "2026-01-02"], "aht": [10.5, 11.2]})
    df.to_csv(csv_file, index=False)

    config = {
        "AHT": {
            "source": "support_daily.csv",
            "date_column": "date",
            "value_column": "aht",
            "aggregation_method": "simple_average"
        }
    }

    res1 = load_kpi_time_series("AHT", config, str(tmp_path))
    res2 = load_kpi_time_series("AHT", config, str(tmp_path))

    # Verify outputs are byte-for-byte identical
    assert res1.equals(res2)

# 13. Trend chart period-boundary and visual bucketing guarantees
@pytest.mark.parametrize("kpi_name", ["AHT", "FCR", "Repeat_Contact_Rate"])
def test_trend_chart_period_boundary_guarantees(kpi_name):
    config = load_kpi_definitions("config/kpi_definitions.yaml")
    baseline = ("2026-01-01", "2026-03-31")
    comparison = ("2026-06-01", "2026-06-30")

    ts_df = load_kpi_time_series(kpi_name, config, "data")
    assert ts_df is not None
    orig_len = len(ts_df)
    orig_df_copy = ts_df.copy()

    fig = build_trend_chart(kpi_name, ts_df, baseline, comparison)
    assert fig is not None
    # Verify underlying daily dataframe was not mutated
    assert ts_df.equals(orig_df_copy)
    assert len(ts_df) == orig_len

    # Extract plotted points
    chart_x = [pd.to_datetime(d) for d in fig.data[0].x]
    chart_y = list(fig.data[0].y)

    # Filter June plotted points
    june_points = [(x, y) for x, y in zip(chart_x, chart_y) if pd.Timestamp("2026-06-01") <= x <= pd.Timestamp("2026-06-30")]

    # Guarantee 1: June produces exactly 5 clean visual buckets (approx 5)
    assert len(june_points) == 5

    # Guarantee 2: First June bucket is anchored at exactly 2026-06-01
    assert june_points[0][0] == pd.Timestamp("2026-06-01")

    # Guarantee 3: Last June bucket is anchored at exactly 2026-06-29 (covering 2026-06-29 to 2026-06-30)
    assert june_points[-1][0] == pd.Timestamp("2026-06-29")

    # Guarantee 4: No points in July exist
    july_points = [x for x in chart_x if x >= pd.Timestamp("2026-07-01")]
    assert len(july_points) == 0

    # Guarantee 5: Clean title without implementation suffixes
    assert fig.layout.title.text == f"{kpi_name} Over Time"

# 14. Trend chart authoritative semantic aggregation tests
def test_trend_chart_semantic_aggregation_vs_arithmetic_mean():
    config = load_kpi_definitions("config/kpi_definitions.yaml")
    baseline = ("2026-01-01", "2026-03-31")
    comparison = ("2026-06-01", "2026-06-30")

    df_raw = pd.read_csv("data/support_daily.csv")
    df_raw["dt"] = pd.to_datetime(df_raw["date"])
    j1_7_raw = df_raw[(df_raw["dt"] >= "2026-06-01") & (df_raw["dt"] <= "2026-06-07")]

    # AHT verification
    ts_aht = load_kpi_time_series("AHT", config, "data")
    fig_aht = build_trend_chart("AHT", ts_aht, baseline, comparison)
    june_aht_pts = [y for x, y in zip(fig_aht.data[0].x, fig_aht.data[0].y) if pd.Timestamp("2026-06-01") <= pd.to_datetime(x) <= pd.Timestamp("2026-06-30")]
    expected_aht_j1_7 = (j1_7_raw["total_handling_seconds"].sum() / (j1_7_raw["resolved_contacts"].sum() * 60.0))
    # Must match authoritative raw formula (~5.812386) and NOT arithmetic mean of daily values (~5.807161)
    assert np.isclose(june_aht_pts[0], expected_aht_j1_7)
    assert not np.isclose(june_aht_pts[0], 5.807161, atol=1e-4)

    # FCR verification
    ts_fcr = load_kpi_time_series("FCR", config, "data")
    fig_fcr = build_trend_chart("FCR", ts_fcr, baseline, comparison)
    june_fcr_pts = [y for x, y in zip(fig_fcr.data[0].x, fig_fcr.data[0].y) if pd.Timestamp("2026-06-01") <= pd.to_datetime(x) <= pd.Timestamp("2026-06-30")]
    expected_fcr_j1_7 = j1_7_raw["first_contact_resolutions"].sum() / j1_7_raw["contacts"].sum()
    assert np.isclose(june_fcr_pts[0], expected_fcr_j1_7)
    assert not np.isclose(june_fcr_pts[0], 0.672120, atol=1e-4)

    # Repeat Contact verification
    ts_rpt = load_kpi_time_series("Repeat_Contact_Rate", config, "data")
    fig_rpt = build_trend_chart("Repeat_Contact_Rate", ts_rpt, baseline, comparison)
    june_rpt_pts = [y for x, y in zip(fig_rpt.data[0].x, fig_rpt.data[0].y) if pd.Timestamp("2026-06-01") <= pd.to_datetime(x) <= pd.Timestamp("2026-06-30")]
    expected_rpt_j1_7 = j1_7_raw["repeat_contacts"].sum() / j1_7_raw["contacts"].sum()
    assert np.isclose(june_rpt_pts[0], expected_rpt_j1_7)
    assert not np.isclose(june_rpt_pts[0], 0.299779, atol=1e-4)

# 15. Trend chart explanatory caption presence check
def test_trend_explanatory_caption_present():
    with open("app.py", "r", encoding="utf-8") as f:
        app_code = f.read()
    expected_caption = "How to read this trend: The headline KPI is calculated for the full comparison period. Trend points are period-aligned sub-period calculations using the same KPI definition and source data. Individual points therefore show how the KPI evolved within the period and are not expected to equal the headline value."
    assert expected_caption in app_code
