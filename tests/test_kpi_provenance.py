import os
import tempfile
import pytest
import pandas as pd
import numpy as np

from src.engine.materiality import analyze_kpi_change, calculate_kpi_value, load_yaml, get_date_column_and_grain
from src.engine.synthesis import generate_synthesis_report
from src.engine.personas import generate_persona_views
from app import load_kpi_time_series, load_kpi_definitions

BASELINE_PERIOD = ("2026-01-01", "2026-03-31")
COMPARISON_PERIOD = ("2026-06-01", "2026-06-30")
CONFIG_PATH = "config/kpi_definitions.yaml"
DATA_DIR = "data"

@pytest.fixture
def kpi_defs():
    return load_kpi_definitions(CONFIG_PATH)

# ==============================================================================
# 1. End-to-End Mathematical Provenance from Actual CSVs
# ==============================================================================

def test_aht_exact_csv_provenance(kpi_defs):
    """
    Verifies that AHT baseline, comparison, and delta values in engine and time series
    strictly derive from data/support_daily.csv via weighted volume calculation.
    """
    df = pd.read_csv("data/support_daily.csv")
    df["dt"] = pd.to_datetime(df["date"])
    
    b_df = df[(df["dt"] >= BASELINE_PERIOD[0]) & (df["dt"] <= BASELINE_PERIOD[1])]
    c_df = df[(df["dt"] >= COMPARISON_PERIOD[0]) & (df["dt"] <= COMPARISON_PERIOD[1])]
    
    expected_b = (b_df["total_handling_seconds"].sum() / b_df["resolved_contacts"].sum()) / 60.0
    expected_c = (c_df["total_handling_seconds"].sum() / c_df["resolved_contacts"].sum()) / 60.0
    expected_abs = expected_c - expected_b
    expected_rel = (expected_abs / expected_b) * 100.0
    
    res = analyze_kpi_change("AHT", kpi_defs, DATA_DIR, BASELINE_PERIOD, COMPARISON_PERIOD)
    
    assert np.isclose(res["baseline"]["value"], expected_b)
    assert np.isclose(res["comparison"]["value"], expected_c)
    assert np.isclose(res["change"]["absolute"], expected_abs)
    assert np.isclose(res["change"]["relative_percent"], expected_rel)
    assert res["status"] == "MATERIAL"
    assert res["materiality"]["crossed"] is True

    # Check time series provenance
    ts = load_kpi_time_series("AHT", kpi_defs, DATA_DIR)
    assert ts is not None
    ts_june = ts[(ts["date"] >= COMPARISON_PERIOD[0]) & (ts["date"] <= COMPARISON_PERIOD[1])]
    # Daily time-series points in June should center around the true June volume-weighted AHT (~5.77 min)
    assert 5.5 < ts_june["value"].mean() < 6.0

def test_fcr_exact_csv_provenance(kpi_defs):
    """
    Verifies that FCR values strictly derive from data/support_daily.csv.
    """
    df = pd.read_csv("data/support_daily.csv")
    df["dt"] = pd.to_datetime(df["date"])
    
    b_df = df[(df["dt"] >= BASELINE_PERIOD[0]) & (df["dt"] <= BASELINE_PERIOD[1])]
    c_df = df[(df["dt"] >= COMPARISON_PERIOD[0]) & (df["dt"] <= COMPARISON_PERIOD[1])]
    
    expected_b = b_df["first_contact_resolutions"].sum() / b_df["contacts"].sum()
    expected_c = c_df["first_contact_resolutions"].sum() / c_df["contacts"].sum()
    expected_abs = expected_c - expected_b
    
    res = analyze_kpi_change("FCR", kpi_defs, DATA_DIR, BASELINE_PERIOD, COMPARISON_PERIOD)
    
    assert np.isclose(res["baseline"]["value"], expected_b)
    assert np.isclose(res["comparison"]["value"], expected_c)
    assert np.isclose(res["change"]["absolute"], expected_abs)
    assert res["status"] == "NOT_MATERIAL"
    assert res["materiality"]["crossed"] is False

def test_csat_exact_csv_provenance(kpi_defs):
    """
    Verifies that CSAT values strictly derive from data/cx_weekly.csv.
    """
    df = pd.read_csv("data/cx_weekly.csv")
    df["dt"] = pd.to_datetime(df["week_start"])
    
    b_df = df[(df["dt"] >= BASELINE_PERIOD[0]) & (df["dt"] <= BASELINE_PERIOD[1])]
    c_df = df[(df["dt"] >= COMPARISON_PERIOD[0]) & (df["dt"] <= COMPARISON_PERIOD[1])]
    
    expected_b = (b_df["csat_score"] * b_df["survey_responses"]).sum() / b_df["survey_responses"].sum()
    expected_c = (c_df["csat_score"] * c_df["survey_responses"]).sum() / c_df["survey_responses"].sum()
    expected_abs = expected_c - expected_b
    
    res = analyze_kpi_change("CSAT", kpi_defs, DATA_DIR, BASELINE_PERIOD, COMPARISON_PERIOD)
    
    assert np.isclose(res["baseline"]["value"], expected_b)
    assert np.isclose(res["comparison"]["value"], expected_c)
    assert np.isclose(res["change"]["absolute"], expected_abs)
    assert res["status"] == "MATERIAL"
    assert res["materiality"]["crossed"] is True

def test_repeat_contact_exact_csv_provenance(kpi_defs):
    """
    Verifies that Repeat Contact Rate strictly derives from data/support_daily.csv.
    """
    df = pd.read_csv("data/support_daily.csv")
    df["dt"] = pd.to_datetime(df["date"])
    
    b_df = df[(df["dt"] >= BASELINE_PERIOD[0]) & (df["dt"] <= BASELINE_PERIOD[1])]
    c_df = df[(df["dt"] >= COMPARISON_PERIOD[0]) & (df["dt"] <= COMPARISON_PERIOD[1])]
    
    expected_b = b_df["repeat_contacts"].sum() / b_df["contacts"].sum()
    expected_c = c_df["repeat_contacts"].sum() / c_df["contacts"].sum()
    expected_abs = expected_c - expected_b
    
    res = analyze_kpi_change("Repeat_Contact_Rate", kpi_defs, DATA_DIR, BASELINE_PERIOD, COMPARISON_PERIOD)
    
    assert np.isclose(res["baseline"]["value"], expected_b)
    assert np.isclose(res["comparison"]["value"], expected_c)
    assert np.isclose(res["change"]["absolute"], expected_abs)
    assert res["status"] == "MATERIAL"
    assert res["materiality"]["crossed"] is True

def test_retention_exact_csv_provenance(kpi_defs):
    """
    Verifies that Retention Rate strictly derives from data/crm_monthly.csv.
    """
    df = pd.read_csv("data/crm_monthly.csv")
    df["dt"] = pd.to_datetime(df["month"])
    
    b_df = df[(df["dt"] >= BASELINE_PERIOD[0]) & (df["dt"] <= BASELINE_PERIOD[1])]
    c_df = df[(df["dt"] >= COMPARISON_PERIOD[0]) & (df["dt"] <= COMPARISON_PERIOD[1])]
    
    expected_b = b_df["retained_customers"].sum() / b_df["active_customers"].sum()
    expected_c = c_df["retained_customers"].sum() / c_df["active_customers"].sum()
    expected_abs = expected_c - expected_b
    
    res = analyze_kpi_change("Retention_Rate", kpi_defs, DATA_DIR, BASELINE_PERIOD, COMPARISON_PERIOD)
    
    assert np.isclose(res["baseline"]["value"], expected_b)
    assert np.isclose(res["comparison"]["value"], expected_c)
    assert np.isclose(res["change"]["absolute"], expected_abs)
    assert res["status"] == "MATERIAL"
    assert res["materiality"]["crossed"] is True

def test_ai_resolution_sparse_provenance(kpi_defs):
    """
    Verifies that AI Resolution Rate strictly reflects the 21 unique calendar days
    in data/ai_resolution_rate.csv and triggers INSUFFICIENT_HISTORY abstention.
    """
    df = pd.read_csv("data/ai_resolution_rate.csv")
    unique_days = df["date"].nunique()
    assert unique_days == 21
    
    res = analyze_kpi_change("AI_Resolution_Rate", kpi_defs, DATA_DIR, BASELINE_PERIOD, COMPARISON_PERIOD)
    assert res["status"] == "INSUFFICIENT_HISTORY"
    assert res["history"]["available_days"] == 21
    assert res["history"]["required_days"] == 60
    assert res["history"]["sufficient"] is False

# ==============================================================================
# 2. Dynamic Data Mutation Sensitivity (No Hardcoded Fallbacks)
# ==============================================================================

def test_engine_recalculates_on_data_mutation(tmp_path, kpi_defs):
    """
    Proves the engine dynamically recalculates metrics when underlying CSV data changes,
    ruling out hardcoded returns.
    """
    # Create a copy of support_daily.csv with doubled handling seconds
    orig_df = pd.read_csv("data/support_daily.csv")
    mutated_df = orig_df.copy()
    mutated_df["total_handling_seconds"] = mutated_df["total_handling_seconds"] * 2.0
    mutated_df.to_csv(tmp_path / "support_daily.csv", index=False)
    
    orig_res = analyze_kpi_change("AHT", kpi_defs, DATA_DIR, BASELINE_PERIOD, COMPARISON_PERIOD)
    mutated_res = analyze_kpi_change("AHT", kpi_defs, str(tmp_path), BASELINE_PERIOD, COMPARISON_PERIOD)
    
    assert np.isclose(mutated_res["baseline"]["value"], orig_res["baseline"]["value"] * 2.0)
    assert np.isclose(mutated_res["comparison"]["value"], orig_res["comparison"]["value"] * 2.0)

def test_time_series_recalculates_on_data_mutation(tmp_path, kpi_defs):
    """
    Proves load_kpi_time_series dynamically recalculates time-series points when CSV changes.
    """
    orig_df = pd.read_csv("data/cx_weekly.csv")
    mutated_df = orig_df.copy()
    mutated_df["csat_score"] = mutated_df["csat_score"] * 0.5
    mutated_df.to_csv(tmp_path / "cx_weekly.csv", index=False)
    
    orig_ts = load_kpi_time_series("CSAT", kpi_defs, DATA_DIR)
    mutated_ts = load_kpi_time_series("CSAT", kpi_defs, str(tmp_path))
    
    assert np.isclose(mutated_ts["value"].mean(), orig_ts["value"].mean() * 0.5)
