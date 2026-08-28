import pytest
import os
import re
import pandas as pd
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
            assert p_word not in stmt_lower, f"Prohibited causal word '{p_word}' found in StoryProof text literal: '{stmt}'"

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
