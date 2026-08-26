import os
import pytest
import pandas as pd
import numpy as np
from src.engine.hypotheses import (
    analyze_ai_rollout,
    analyze_crm_patch,
    analyze_mix_shift,
    synthesize_hypotheses
)
from src.engine.drivers import profile_driver, compare_ai_assisted
from src.engine.materiality import load_yaml, analyze_kpi_change

CONFIG_PATH = "config/kpi_definitions.yaml"
DATA_DIR = "data"

@pytest.fixture
def real_config():
    return load_yaml(CONFIG_PATH)

# Test 1: AI hypothesis recognizes NO_AI_BASELINE for Q1
def test_ai_rollout_q1(real_config):
    res = analyze_ai_rollout("AHT", DATA_DIR, real_config)
    assert res["status"] == "SUCCESS"
    q1 = res["phases"]["Q1 Baseline"]
    assert q1["status"] == "NO_AI_BASELINE"
    assert q1["ai_assisted"]["kpi"] is None
    assert q1["ai_assisted"]["contacts"] == 0

# Test 2: AI hypothesis calculates April correctly
def test_ai_rollout_april(real_config):
    res = analyze_ai_rollout("AHT", DATA_DIR, real_config)
    assert res["status"] == "SUCCESS"
    april = res["phases"]["April"]
    assert april["status"] == "SUCCESS"
    assert april["ai_assisted"]["kpi"] > 0
    assert april["non_ai_assisted"]["kpi"] > 0
    assert april["comparison"]["absolute_difference"] is not None

# Test 3: AI hypothesis calculates May correctly
def test_ai_rollout_may(real_config):
    res = analyze_ai_rollout("AHT", DATA_DIR, real_config)
    assert res["status"] == "SUCCESS"
    may = res["phases"]["May"]
    assert may["status"] == "SUCCESS"
    assert may["ai_assisted"]["kpi"] > 0
    assert may["comparison"]["absolute_difference"] is not None

# Test 4: AI hypothesis calculates June correctly
def test_ai_rollout_june(real_config):
    res = analyze_ai_rollout("AHT", DATA_DIR, real_config)
    assert res["status"] == "SUCCESS"
    june = res["phases"]["June"]
    assert june["status"] == "SUCCESS"
    assert june["ai_assisted"]["kpi"] > 0
    assert june["comparison"]["absolute_difference"] is not None

# Test 5: AI direction consistency works
def test_ai_direction_consistency(real_config):
    res = analyze_ai_rollout("AHT", DATA_DIR, real_config)
    assert res["status"] == "SUCCESS"
    assert res["direction_consistency"] in ["CONSISTENT_REDUCTION", "CONSISTENT_INCREASE", "INCONSISTENT"]
    # Real AHT is consistently lower for AI
    assert res["direction_consistency"] == "CONSISTENT_REDUCTION"

# Test 6: AI hypothesis does not produce causal language
def test_ai_no_causal_language(real_config):
    res = analyze_ai_rollout("AHT", DATA_DIR, real_config)
    
    causal_words = ["caused", "causes", "proves", "resulted in", "the reason is"]
    text_content = " ".join(res["supporting_signals"] + res["limiting_signals"] + res["limitations"]).lower()
    
    for word in causal_words:
        assert word not in text_content

# Test 7: CRM patch pre/post boundaries are exactly correct
def test_crm_patch_boundaries(tmp_path):
    # Create mock daily support data
    data = [
        # Pre-patch (April 1 to May 3)
        {"date": "2026-04-01", "product": "CRM Cloud", "total_handling_seconds": 600, "resolved_contacts": 1, "contacts": 1},
        {"date": "2026-05-03", "product": "CRM Cloud", "total_handling_seconds": 600, "resolved_contacts": 1, "contacts": 1},
        # Post-patch (May 4 to June 30)
        {"date": "2026-05-04", "product": "CRM Cloud", "total_handling_seconds": 1200, "resolved_contacts": 1, "contacts": 1},
        {"date": "2026-06-30", "product": "CRM Cloud", "total_handling_seconds": 1200, "resolved_contacts": 1, "contacts": 1},
        # Control Product
        {"date": "2026-04-15", "product": "Core ERP", "total_handling_seconds": 600, "resolved_contacts": 1, "contacts": 1},
        {"date": "2026-05-15", "product": "Core ERP", "total_handling_seconds": 600, "resolved_contacts": 1, "contacts": 1},
    ]
    df = pd.DataFrame(data)
    df.to_csv(tmp_path / "support_daily.csv", index=False)

    synthetic_config = {
        "AHT": {
            "source": "support_daily.csv",
            "aggregation_method": "weighted_average",
            "numerator_field": "total_handling_seconds",
            "denominator_field": "resolved_contacts",
            "source_grain": "daily",
            "raw_unit": "seconds",
            "display_unit": "minutes"
        }
    }
    # Handled inside evaluate patch
    res = analyze_crm_patch("AHT", str(tmp_path), synthetic_config)
    assert res["status"] == "SUCCESS"
    # Pre-patch CRM KPI = (600 + 600) / 2 / 60 = 10 minutes
    assert abs(res["crm_pre"] - 10.0) <= 1e-9
    # Post-patch CRM KPI = (1200 + 1200) / 2 / 60 = 20 minutes
    assert abs(res["crm_post"] - 20.0) <= 1e-9

# Test 8: CRM vs control differential calculation works
def test_crm_vs_control_differential(tmp_path):
    data = [
        # CRM Cloud Pre: 10 mins (600s), Post: 20 mins (1200s) -> change = +10.0 mins
        {"date": "2026-04-15", "product": "CRM Cloud", "total_handling_seconds": 600, "resolved_contacts": 1, "contacts": 1},
        {"date": "2026-05-15", "product": "CRM Cloud", "total_handling_seconds": 1200, "resolved_contacts": 1, "contacts": 1},
        # Control Pre: 10 mins (600s), Post: 12 mins (720s) -> change = +2.0 mins
        {"date": "2026-04-15", "product": "Core ERP", "total_handling_seconds": 600, "resolved_contacts": 1, "contacts": 1},
        {"date": "2026-05-15", "product": "Core ERP", "total_handling_seconds": 720, "resolved_contacts": 1, "contacts": 1},
    ]
    df = pd.DataFrame(data)
    df.to_csv(tmp_path / "support_daily.csv", index=False)

    synthetic_config = {
        "AHT": {
            "source": "support_daily.csv",
            "aggregation_method": "weighted_average",
            "numerator_field": "total_handling_seconds",
            "denominator_field": "resolved_contacts",
            "source_grain": "daily",
            "raw_unit": "seconds",
            "display_unit": "minutes"
        }
    }
    res = analyze_crm_patch("AHT", str(tmp_path), synthetic_config)
    assert res["status"] == "SUCCESS"
    assert abs(res["crm_change"] - 10.0) <= 1e-9
    assert abs(res["control_change"] - 2.0) <= 1e-9
    # Differential = 10.0 - 2.0 = +8.0 mins
    assert abs(res["differential_signal"] - 8.0) <= 1e-9
    assert res["classification"] == "CONCENTRATED"

# Test 9: CRM hypothesis does not claim causality
def test_crm_no_causal_claims(real_config):
    res = analyze_crm_patch("AHT", DATA_DIR, real_config)
    assert res["status"] == "SUCCESS"
    
    causal_words = ["caused", "causes", "proves", "resulted in", "the reason is"]
    text_content = " ".join(res["supporting_signals"] + res["limiting_signals"] + res["limitations"]).lower()
    for word in causal_words:
        assert word not in text_content

# Test 10: Mix LOW classification works
def test_mix_low_classification(tmp_path):
    # Total change = 10.0, mix effect = 1.0 -> mix share = 10% (LOW)
    synthetic_config = {
        "TEST_KPI": {
            "source": "data.csv",
            "aggregation_method": "weighted_average",
            "numerator_field": "num",
            "denominator_field": "denom",
            "source_grain": "daily"
        }
    }
    # Segment A: base = 100 denom, 10 num. comp = 100 denom, 20 num. (Rate change only, no share change)
    # Segment B: base = 100 denom, 10 num. comp = 110 denom, 11 num. (Share change but rate is stable)
    df = pd.DataFrame([
        {"date": "2026-01-15", "segment": "A", "num": 10, "denom": 100},
        {"date": "2026-01-15", "segment": "B", "num": 10, "denom": 100},
        {"date": "2026-06-15", "segment": "A", "num": 20, "denom": 100},
        {"date": "2026-06-15", "segment": "B", "num": 11, "denom": 110},
    ])
    df.to_csv(tmp_path / "data.csv", index=False)

    res = analyze_mix_shift(
        kpi_name="TEST_KPI",
        dimension="segment",
        baseline_period=("2026-01-01", "2026-01-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir=str(tmp_path),
        config=synthetic_config
    )
    assert res["status"] == "SUCCESS"
    assert res["classification"] == "LOW"
    assert res["evidence_strength"] == "WEAK_ASSOCIATION"

# Test 11: Mix MODERATE classification works
def test_mix_moderate_classification(tmp_path):
    synthetic_config = {
        "TEST_KPI": {
            "source": "data.csv",
            "aggregation_method": "weighted_average",
            "numerator_field": "num",
            "denominator_field": "denom",
            "source_grain": "daily"
        }
    }
    # Setup values to yield mix share of ~30%
    # Segment A: base = 100 denom, 10 num (rate 0.1). comp = 50 denom, 10 num (rate 0.2)
    # Segment B: base = 100 denom, 30 num (rate 0.3). comp = 150 denom, 45 num (rate 0.3)
    # Base overall = 40 / 200 = 0.20
    # Comp overall = 55 / 200 = 0.275
    # Overall change = +0.075
    df = pd.DataFrame([
        {"date": "2026-01-15", "segment": "A", "num": 10, "denom": 100},
        {"date": "2026-01-15", "segment": "B", "num": 30, "denom": 100},
        {"date": "2026-06-15", "segment": "A", "num": 10, "denom": 50},
        {"date": "2026-06-15", "segment": "B", "num": 45, "denom": 150},
    ])
    df.to_csv(tmp_path / "data.csv", index=False)

    res = analyze_mix_shift(
        kpi_name="TEST_KPI",
        dimension="segment",
        baseline_period=("2026-01-01", "2026-01-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir=str(tmp_path),
        config=synthetic_config
    )
    assert res["status"] == "SUCCESS"
    assert res["classification"] == "MODERATE"
    assert res["evidence_strength"] == "MODERATE_ASSOCIATION"

# Test 12: Mix HIGH classification works
def test_mix_high_classification(tmp_path):
    synthetic_config = {
        "TEST_KPI": {
            "source": "data.csv",
            "aggregation_method": "weighted_average",
            "numerator_field": "num",
            "denominator_field": "denom",
            "source_grain": "daily"
        }
    }
    # Base: A=100 (denom, rate=0.1), B=100 (denom, rate=0.5) -> global=0.3
    # Comp: A=10 (denom, rate=0.1), B=190 (denom, rate=0.5) -> global=0.48
    # Rates did not change, so rate effect is exactly 0. Mix effect = 100% of change (HIGH)
    df = pd.DataFrame([
        {"date": "2026-01-15", "segment": "A", "num": 10, "denom": 100},
        {"date": "2026-01-15", "segment": "B", "num": 50, "denom": 100},
        {"date": "2026-06-15", "segment": "A", "num": 1, "denom": 10},
        {"date": "2026-06-15", "segment": "B", "num": 95, "denom": 190},
    ])
    df.to_csv(tmp_path / "data.csv", index=False)

    res = analyze_mix_shift(
        kpi_name="TEST_KPI",
        dimension="segment",
        baseline_period=("2026-01-01", "2026-01-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir=str(tmp_path),
        config=synthetic_config
    )
    assert res["status"] == "SUCCESS"
    assert res["classification"] == "HIGH"
    assert res["evidence_strength"] == "STRONG_ASSOCIATION"

# Test 13: Zero total-change safety
def test_mix_zero_change_safety(tmp_path):
    synthetic_config = {
        "TEST_KPI": {
            "source": "data.csv",
            "aggregation_method": "weighted_average",
            "numerator_field": "num",
            "denominator_field": "denom",
            "source_grain": "daily"
        }
    }
    # No change at all
    df = pd.DataFrame([
        {"date": "2026-01-15", "segment": "A", "num": 10, "denom": 100},
        {"date": "2026-06-15", "segment": "A", "num": 10, "denom": 100},
    ])
    df.to_csv(tmp_path / "data.csv", index=False)

    res = analyze_mix_shift(
        kpi_name="TEST_KPI",
        dimension="segment",
        baseline_period=("2026-01-01", "2026-01-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir=str(tmp_path),
        config=synthetic_config
    )
    assert res["status"] == "NOT_AVAILABLE"

# Test 14: Missing control group abstention
def test_crm_missing_control_abstention(tmp_path):
    # Only CRM Cloud is present, no controls
    data = [
        {"date": "2026-04-15", "product": "CRM Cloud", "total_handling_seconds": 600, "resolved_contacts": 1, "contacts": 1},
        {"date": "2026-05-15", "product": "CRM Cloud", "total_handling_seconds": 1200, "resolved_contacts": 1, "contacts": 1},
    ]
    df = pd.DataFrame(data)
    df.to_csv(tmp_path / "support_daily.csv", index=False)

    synthetic_config = {
        "AHT": {
            "source": "support_daily.csv",
            "aggregation_method": "weighted_average",
            "numerator_field": "total_handling_seconds",
            "denominator_field": "resolved_contacts",
            "source_grain": "daily"
        }
    }
    res = analyze_crm_patch("AHT", str(tmp_path), synthetic_config)
    assert res["status"] == "NOT_AVAILABLE"
    assert "Control group" in res["reason"]

# Test 15: Missing dimension abstention
def test_missing_dimension_abstention(real_config):
    res = analyze_mix_shift("AHT", "missing_col", ("2026-01-01", "2026-03-31"), ("2026-06-01", "2026-06-30"), DATA_DIR, real_config)
    assert res["status"] == "NOT_AVAILABLE"

# Test 16: Overall evidence synthesis returns INVESTIGATION_REQUIRED for AHT in the real scenario
def test_synthesis_investigation_required(real_config):
    res = synthesize_hypotheses(
        kpi_name="AHT",
        data_dir=DATA_DIR,
        config=real_config,
        baseline_period=("2026-01-01", "2026-03-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        mix_dimension="product"
    )
    assert res["overall_evidence_state"] == "INVESTIGATION_REQUIRED"
    assert "confounding" in res["reason"] or "efficiency trap" in res["reason"]

# Test 17: Existing 3A and 3B.1 behaviors remain unaffected (Regression Test)
def test_regression_compatibility(real_config):
    # Verify 3A materiality engine
    mat_res = analyze_kpi_change("AHT", real_config, DATA_DIR, ("2026-01-01", "2026-03-31"), ("2026-06-01", "2026-06-30"))
    assert mat_res["status"] == "MATERIAL"
    assert mat_res["change"]["direction"] == "DECREASE"
    
    mat_csat = analyze_kpi_change("CSAT", real_config, DATA_DIR, ("2026-01-01", "2026-03-31"), ("2026-06-01", "2026-06-30"))
    assert mat_csat["status"] == "MATERIAL"

    # Verify 3B.1 driver engine profile_driver
    drv_res = profile_driver("AHT", "product", ("2026-01-01", "2026-03-31"), ("2026-06-01", "2026-06-30"), DATA_DIR, real_config)
    assert drv_res["status"] == "SUCCESS"
    assert abs(drv_res["reconciliation_error"]) <= 1e-9

    # Verify 3B.1 compare_ai_assisted
    ai_comp = compare_ai_assisted("AHT", DATA_DIR, real_config)
    assert ai_comp["status"] == "SUCCESS"
    assert ai_comp["phases"]["Q1 Baseline"]["status"] == "NO_AI_BASELINE"

# Hardening Test 18: Inconsistent AI direction does not produce false consistency narrative
def test_inconsistent_ai_direction_narrative_neutrality(monkeypatch, real_config):
    # Mock compare_ai_assisted to return inconsistent directions
    def mock_compare(kpi_name, data_dir, config):
        return {
            "status": "SUCCESS",
            "phases": {
                "April": {
                    "status": "SUCCESS",
                    "comparison": {"absolute_difference": 5.0, "relative_difference": 0.10}
                },
                "May": {
                    "status": "SUCCESS",
                    "comparison": {"absolute_difference": -5.0, "relative_difference": -0.10}
                },
                "June": {
                    "status": "SUCCESS",
                    "comparison": {"absolute_difference": 5.0, "relative_difference": 0.10}
                }
            }
        }
    monkeypatch.setattr("src.engine.hypotheses.compare_ai_assisted", mock_compare)
    res = analyze_ai_rollout("AHT", DATA_DIR, real_config)
    assert res["status"] == "SUCCESS"
    assert res["direction_consistency"] == "INCONSISTENT"
    assert res["evidence_strength"] == "INCONCLUSIVE"
    supporting_text = " ".join(res["supporting_signals"])
    assert "consistently" not in supporting_text.lower()
    assert "mixed directional differences" in supporting_text

# Hardening Test 19: Verify AHT patch calculations are in minutes (not seconds)
def test_crm_patch_aht_minutes_normalization(real_config):
    res = analyze_crm_patch("AHT", DATA_DIR, real_config)
    assert res["status"] == "SUCCESS"
    # Verification that calculated values are minute-normalized
    # Expected AHT on real support logs is around 8-10 mins (pre) and 5-6 mins (post)
    assert 1.0 <= res["crm_pre"] <= 20.0
    assert 1.0 <= res["crm_post"] <= 20.0
    assert 1.0 <= res["control_pre"] <= 20.0
    assert 1.0 <= res["control_post"] <= 20.0
    assert abs(res["crm_change"]) <= 10.0
    assert abs(res["differential_signal"]) <= 5.0
