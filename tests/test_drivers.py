import os
import pytest
import pandas as pd
import math
from src.engine.drivers import profile_driver, compare_ai_assisted
from src.engine.materiality import load_yaml

CONFIG_PATH = "config/kpi_definitions.yaml"
DATA_DIR = "data"

@pytest.fixture
def real_config():
    return load_yaml(CONFIG_PATH)

# Test 1: Valid AHT driver profiling by product
def test_aht_by_product(real_config):
    res = profile_driver(
        kpi_name="AHT",
        dimension="product",
        baseline_period=("2026-01-01", "2026-03-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir=DATA_DIR,
        config=real_config
    )
    assert res["status"] == "SUCCESS"
    assert res["provenance"]["kpi"] == "AHT"
    assert res["provenance"]["dimension"] == "product"
    assert len(res["drivers"]) > 0
    # Reconciliation error check
    assert abs(res["reconciliation_error"]) <= 1e-9

# Test 2: Valid FCR profiling by customer_segment
def test_fcr_by_customer_segment(real_config):
    res = profile_driver(
        kpi_name="FCR",
        dimension="customer_segment",
        baseline_period=("2026-01-01", "2026-03-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir=DATA_DIR,
        config=real_config
    )
    assert res["status"] == "SUCCESS"
    assert res["provenance"]["dimension"] == "customer_segment"
    assert abs(res["reconciliation_error"]) <= 1e-9

# Test 3: Valid Repeat Contact profiling by region
def test_repeat_contact_by_region(real_config):
    res = profile_driver(
        kpi_name="Repeat_Contact_Rate",
        dimension="region",
        baseline_period=("2026-01-01", "2026-03-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir=DATA_DIR,
        config=real_config
    )
    assert res["status"] == "SUCCESS"
    assert res["provenance"]["dimension"] == "region"
    assert abs(res["reconciliation_error"]) <= 1e-9

# Test 4: Valid CSAT profiling by product
def test_csat_by_product(real_config):
    res = profile_driver(
        kpi_name="CSAT",
        dimension="product",
        baseline_period=("2026-01-01", "2026-03-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir=DATA_DIR,
        config=real_config
    )
    assert res["status"] == "SUCCESS"
    assert res["provenance"]["dimension"] == "product"
    assert abs(res["reconciliation_error"]) <= 1e-9

# Test 5: Valid Retention profiling by customer_segment
def test_retention_by_customer_segment(real_config):
    res = profile_driver(
        kpi_name="Retention_Rate",
        dimension="customer_segment",
        baseline_period=("2026-01-01", "2026-03-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir=DATA_DIR,
        config=real_config
    )
    assert res["status"] == "SUCCESS"
    assert res["provenance"]["dimension"] == "customer_segment"
    assert abs(res["reconciliation_error"]) <= 1e-9

# Test 6: Invalid CSAT by ai_assisted -> ABSTAINED / NOT_AVAILABLE
def test_csat_invalid_dimension(real_config):
    res = profile_driver(
        kpi_name="CSAT",
        dimension="ai_assisted",
        baseline_period=("2026-01-01", "2026-03-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir=DATA_DIR,
        config=real_config
    )
    assert res["status"] == "NOT_AVAILABLE"
    assert "ai_assisted" in res["reason"]

# Test 7: Invalid Retention by ai_assisted -> ABSTAINED / NOT_AVAILABLE
def test_retention_invalid_dimension(real_config):
    res = profile_driver(
        kpi_name="Retention_Rate",
        dimension="ai_assisted",
        baseline_period=("2026-01-01", "2026-03-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir=DATA_DIR,
        config=real_config
    )
    assert res["status"] == "NOT_AVAILABLE"
    assert "ai_assisted" in res["reason"]

# Test 8: Zero denominator safety
def test_zero_denominator_safety(tmp_path):
    # Create synthetic config
    synthetic_config = {
        "TEST_KPI": {
            "source": "synthetic_zero_denom.csv",
            "aggregation_method": "weighted_average",
            "numerator_field": "num",
            "denominator_field": "denom",
            "source_grain": "daily"
        }
    }
    # Create data with zero denominator
    df = pd.DataFrame([
        {"date": "2026-01-15", "segment": "A", "num": 0, "denom": 0},
        {"date": "2026-06-15", "segment": "A", "num": 0, "denom": 0}
    ])
    df.to_csv(tmp_path / "synthetic_zero_denom.csv", index=False)
    
    res = profile_driver(
        kpi_name="TEST_KPI",
        dimension="segment",
        baseline_period=("2026-01-01", "2026-01-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir=str(tmp_path),
        config=synthetic_config
    )
    assert res["status"] == "NOT_AVAILABLE"
    assert "Denominator is zero" in res["reason"]

# Test 9: Empty comparison period
def test_empty_comparison_period(tmp_path):
    synthetic_config = {
        "TEST_KPI": {
            "source": "synthetic_empty.csv",
            "aggregation_method": "weighted_average",
            "numerator_field": "num",
            "denominator_field": "denom",
            "source_grain": "daily"
        }
    }
    # Create data with observations only in baseline period
    df = pd.DataFrame([
        {"date": "2026-01-15", "segment": "A", "num": 10, "denom": 100}
    ])
    df.to_csv(tmp_path / "synthetic_empty.csv", index=False)
    
    res = profile_driver(
        kpi_name="TEST_KPI",
        dimension="segment",
        baseline_period=("2026-01-01", "2026-01-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir=str(tmp_path),
        config=synthetic_config
    )
    assert res["status"] == "NOT_AVAILABLE"
    assert "contains no observations" in res["reason"]

# Test 10: Synthetic exact decomposition reconciliation
def test_synthetic_exact_reconciliation(tmp_path):
    synthetic_config = {
        "TEST_KPI": {
            "source": "synthetic_reconciled.csv",
            "aggregation_method": "weighted_average",
            "numerator_field": "num",
            "denominator_field": "denom",
            "source_grain": "daily"
        }
    }
    df = pd.DataFrame([
        {"date": "2026-01-15", "segment": "A", "num": 15, "denom": 100},
        {"date": "2026-01-15", "segment": "B", "num": 40, "denom": 200},
        {"date": "2026-06-15", "segment": "A", "num": 30, "denom": 150},
        {"date": "2026-06-15", "segment": "B", "num": 60, "denom": 150}
    ])
    df.to_csv(tmp_path / "synthetic_reconciled.csv", index=False)
    
    res = profile_driver(
        kpi_name="TEST_KPI",
        dimension="segment",
        baseline_period=("2026-01-01", "2026-01-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir=str(tmp_path),
        config=synthetic_config
    )
    assert res["status"] == "SUCCESS"
    assert abs(res["reconciliation_error"]) <= 1e-9
    assert res["reconciliation_info"]["is_reconciled"] is True

# Test 11: Synthetic pure-rate-change case
def test_synthetic_pure_rate_change(tmp_path):
    synthetic_config = {
        "TEST_KPI": {
            "source": "synthetic_rate.csv",
            "aggregation_method": "weighted_average",
            "numerator_field": "num",
            "denominator_field": "denom",
            "source_grain": "daily"
        }
    }
    # Exposure (denom share) remains exactly B: 200/300 = 2/3, A: 100/300 = 1/3
    df = pd.DataFrame([
        {"date": "2026-01-15", "segment": "A", "num": 10, "denom": 100},
        {"date": "2026-01-15", "segment": "B", "num": 40, "denom": 200},
        {"date": "2026-06-15", "segment": "A", "num": 20, "denom": 100},
        {"date": "2026-06-15", "segment": "B", "num": 60, "denom": 200}
    ])
    df.to_csv(tmp_path / "synthetic_rate.csv", index=False)
    
    res = profile_driver(
        kpi_name="TEST_KPI",
        dimension="segment",
        baseline_period=("2026-01-01", "2026-01-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir=str(tmp_path),
        config=synthetic_config
    )
    assert res["status"] == "SUCCESS"
    for driver in res["drivers"]:
        # Exposure should not change
        assert driver["baseline_exposure"] == driver["comparison_exposure"]
        # Mix effect must be exactly zero
        assert abs(driver["mix_effect"]) <= 1e-9
        # Total contribution must equal rate effect
        assert abs(driver["total_contribution"] - driver["rate_effect"]) <= 1e-9
    assert abs(res["reconciliation_error"]) <= 1e-9

# Test 12: Synthetic pure-mix-change case
def test_synthetic_pure_mix_change(tmp_path):
    synthetic_config = {
        "TEST_KPI": {
            "source": "synthetic_mix.csv",
            "aggregation_method": "weighted_average",
            "numerator_field": "num",
            "denominator_field": "denom",
            "source_grain": "daily"
        }
    }
    # Segment rates are exactly A: 10/100 = 0.1, B: 40/200 = 0.2
    # Baseline: A=100 (denom), B=200 (denom)
    # Comparison: A=200 (denom, num=20), B=100 (denom, num=20)
    df = pd.DataFrame([
        {"date": "2026-01-15", "segment": "A", "num": 10, "denom": 100},
        {"date": "2026-01-15", "segment": "B", "num": 40, "denom": 200},
        {"date": "2026-06-15", "segment": "A", "num": 20, "denom": 200},
        {"date": "2026-06-15", "segment": "B", "num": 20, "denom": 100}
    ])
    df.to_csv(tmp_path / "synthetic_mix.csv", index=False)
    
    res = profile_driver(
        kpi_name="TEST_KPI",
        dimension="segment",
        baseline_period=("2026-01-01", "2026-01-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir=str(tmp_path),
        config=synthetic_config
    )
    assert res["status"] == "SUCCESS"
    for driver in res["drivers"]:
        # Rate should not change
        assert abs(driver["baseline_value"] - driver["comparison_value"]) <= 1e-9
        # Rate effect must be exactly zero
        assert abs(driver["rate_effect"]) <= 1e-9
        # Total contribution must equal mix effect
        assert abs(driver["total_contribution"] - driver["mix_effect"]) <= 1e-9
    assert abs(res["reconciliation_error"]) <= 1e-9

# Test 13: AI-assisted vs non-AI-assisted operational comparison
def test_ai_assisted_comparison(real_config):
    # Valid operational KPI
    res = compare_ai_assisted(
        kpi_name="AHT",
        data_dir=DATA_DIR,
        config=real_config
    )
    assert res["status"] == "SUCCESS"
    assert res["kpi"] == "AHT"
    # Verify phases are returned
    assert "Q1 Baseline" in res["phases"]
    assert "June" in res["phases"]
    
    # Verify Q1 Baseline behavior when there are zero AI assisted contacts
    q1_res = res["phases"]["Q1 Baseline"]
    assert q1_res["status"] == "NO_AI_BASELINE"
    assert q1_res["ai_assisted"]["kpi"] is None
    assert q1_res["ai_assisted"]["contacts"] == 0
    assert q1_res["comparison"]["absolute_difference"] is None
    assert q1_res["comparison"]["relative_difference"] is None
    
    # In June phase, AI-assisted results should have success status
    june_res = res["phases"]["June"]
    assert june_res["status"] == "SUCCESS"
    assert "ai_assisted" in june_res
    assert "non_ai_assisted" in june_res
    assert "comparison" in june_res
    assert june_res["comparison"]["absolute_difference"] is not None

    # Invalid outcome KPI CSAT should return NOT_AVAILABLE
    res_csat = compare_ai_assisted(
        kpi_name="CSAT",
        data_dir=DATA_DIR,
        config=real_config
    )
    assert res_csat["status"] == "NOT_AVAILABLE"
    assert "ai_assisted dimension" in res_csat["reason"]

# Test 14: Missing dimension safety
def test_missing_dimension_safety(real_config):
    res = profile_driver(
        kpi_name="AHT",
        dimension="invalid_column_name",
        baseline_period=("2026-01-01", "2026-03-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir=DATA_DIR,
        config=real_config
    )
    assert res["status"] == "NOT_AVAILABLE"
    assert "invalid_column_name" in res["reason"]
