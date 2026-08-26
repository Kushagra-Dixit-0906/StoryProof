import os
import tempfile
import pytest
import pandas as pd
from src.engine.materiality import analyze_kpi_change, load_yaml

# Constants for test periods
BASELINE_PERIOD = ("2026-01-01", "2026-03-31")
COMPARISON_PERIOD = ("2026-06-01", "2026-06-30")
CONFIG_PATH = "config/kpi_definitions.yaml"
DATA_DIR = "data"

@pytest.fixture
def kpi_defs():
    return load_yaml(CONFIG_PATH)

def test_aht_q1_to_june(kpi_defs):
    # TEST 1: AHT Q1 -> June
    # Expected: material change, large negative relative change
    res = analyze_kpi_change("AHT", kpi_defs, DATA_DIR, BASELINE_PERIOD, COMPARISON_PERIOD)
    
    assert res["status"] == "MATERIAL"
    assert res["change"]["direction"] == "DECREASE"
    assert res["change"]["relative_percent"] < -30.0  # Large negative relative change (around -43.2%)
    assert res["materiality"]["crossed"] is True
    assert res["statistical_signal"]["unusual"] is True  # Z-score around -52

def test_fcr_q1_to_june(kpi_defs):
    # TEST 2: FCR Q1 -> June
    # Expected: approximately flat, below materiality threshold of 2 percentage points
    res = analyze_kpi_change("FCR", kpi_defs, DATA_DIR, BASELINE_PERIOD, COMPARISON_PERIOD)
    
    assert res["status"] == "NOT_MATERIAL"
    assert res["change"]["direction"] == "NO_MATERIAL_DIRECTION"
    assert abs(res["change"]["absolute"]) < 0.02  # less than 2 percentage points (around 0.0086)
    assert res["materiality"]["crossed"] is False

def test_csat_q1_to_june(kpi_defs):
    # TEST 3: CSAT Q1 -> June
    # Expected: material change, large negative absolute change
    res = analyze_kpi_change("CSAT", kpi_defs, DATA_DIR, BASELINE_PERIOD, COMPARISON_PERIOD)
    
    assert res["status"] == "MATERIAL"
    assert res["change"]["direction"] == "DECREASE"
    assert res["change"]["absolute"] < -5.0  # Large negative absolute change (around -9.2 weighted or -9.4 simple)
    assert res["materiality"]["crossed"] is True

def test_repeat_contact_rate_q1_to_june(kpi_defs):
    # TEST 4: Repeat Contact Rate Q1 -> June
    # Expected: material increase, materiality crossed (threshold 3 percentage points)
    res = analyze_kpi_change("Repeat_Contact_Rate", kpi_defs, DATA_DIR, BASELINE_PERIOD, COMPARISON_PERIOD)
    
    assert res["status"] == "MATERIAL"
    assert res["change"]["direction"] == "INCREASE"
    assert res["change"]["absolute"] > 0.05  # Large increase (around 14.0 percentage points)
    assert res["materiality"]["crossed"] is True

def test_retention_q1_to_june(kpi_defs):
    # TEST 5: Retention Q1 -> June
    # Expected: material decline according to configured threshold (0.5 percentage points)
    res = analyze_kpi_change("Retention_Rate", kpi_defs, DATA_DIR, BASELINE_PERIOD, COMPARISON_PERIOD)
    
    assert res["status"] == "MATERIAL"
    assert res["change"]["direction"] == "DECREASE"
    assert res["change"]["absolute"] < -0.005  # More than 0.5 percentage points decline (around -1.1 percentage points)
    assert res["materiality"]["crossed"] is True

def test_ai_resolution_rate_insufficient_history(kpi_defs):
    # TEST 6: AI Resolution Rate
    # Expected: INSUFFICIENT_HISTORY (only 21 days of history, 60 required)
    res = analyze_kpi_change("AI_Resolution_Rate", kpi_defs, DATA_DIR, BASELINE_PERIOD, COMPARISON_PERIOD)
    
    assert res["status"] == "INSUFFICIENT_HISTORY"
    assert res["history"]["sufficient"] is False
    assert res["history"]["available_days"] == 21
    assert "Only 21 days of observations are available" in res["warnings"][0] or "Insufficient historical data" in res["warnings"][0]

def test_zero_denominator_handling(kpi_defs):
    # TEST 7: Zero denominator
    # Expected: safe failure / explicit invalid state (ValueError)
    
    # Create temp CSV with 0 contacts
    temp_dir = tempfile.mkdtemp()
    temp_file = os.path.join(temp_dir, "zero_denominator.csv")
    
    # Support CSV structure
    data = {
        "date": ["2026-01-01", "2026-06-01"],
        "contacts": [0, 0],
        "first_contact_resolutions": [0, 0]
    }
    pd.DataFrame(data).to_csv(temp_file, index=False)
    
    # Create custom KPI def referring to this file
    custom_defs = {
        "Zero_KPI": {
            "source": temp_file,
            "source_grain": "daily",
            "aggregation_method": "weighted_average",
            "numerator_field": "first_contact_resolutions",
            "denominator_field": "contacts",
            "materiality_threshold": 0.02,
            "threshold_type": "absolute_percentage_points",
            "minimum_history_days": 1
        }
    }
    
    # Verify that calling engine raises ValueError due to zero division
    with pytest.raises(ValueError) as excinfo:
        analyze_kpi_change("Zero_KPI", custom_defs, temp_dir, ("2026-01-01", "2026-01-01"), ("2026-06-01", "2026-06-01"))
    
    assert "Zero denominator" in str(excinfo.value)

def test_empty_comparison_period(kpi_defs):
    # TEST 8: Empty comparison period
    # Expected: explicit error / empty period state
    res = analyze_kpi_change("AHT", kpi_defs, DATA_DIR, BASELINE_PERIOD, ("2026-07-01", "2026-07-31"))
    
    assert res["status"] == "NOT_MATERIAL"
    assert res["change"]["absolute"] is None
    assert any("empty" in w.lower() for w in res["warnings"])

def test_synthetic_stable_dataset():
    # TEST 9: Small synthetic stable dataset
    # Expected: NOT_MATERIAL
    temp_dir = tempfile.mkdtemp()
    temp_file = os.path.join(temp_dir, "stable_kpi.csv")
    
    # Baseline has 5 identical values, comparison has same value
    data = {
        "date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05", "2026-06-01"],
        "num": [10, 10, 10, 10, 10, 10],
        "den": [100, 100, 100, 100, 100, 100]
    }
    pd.DataFrame(data).to_csv(temp_file, index=False)
    
    custom_defs = {
        "Stable_KPI": {
            "source": temp_file,
            "source_grain": "daily",
            "aggregation_method": "weighted_average",
            "numerator_field": "num",
            "denominator_field": "den",
            "materiality_threshold": 0.05,
            "threshold_type": "relative",
            "minimum_history_days": 2
        }
    }
    
    res = analyze_kpi_change("Stable_KPI", custom_defs, temp_dir, ("2026-01-01", "2026-01-05"), ("2026-06-01", "2026-06-01"))
    
    assert res["status"] == "NOT_MATERIAL"
    assert res["change"]["absolute"] == 0.0
    assert res["change"]["relative_percent"] == 0.0
    assert res["materiality"]["crossed"] is False
    assert res["statistical_signal"]["z_score"] is None or res["statistical_signal"]["z_score"] == 0.0

def test_synthetic_volatile_vs_material():
    # TEST 10: Synthetic large but volatile movement
    # Demonstrates that business materiality and statistical unusualness remain separate concepts.
    temp_dir = tempfile.mkdtemp()
    temp_file = os.path.join(temp_dir, "volatile_kpi.csv")
    
    # Baseline is highly volatile: values are 10, 30, 20, 40 (mean=25, std=12.9)
    # Comparison is 28. Business threshold is 10% relative.
    # Change is (28 - 25)/25 = +12.0% (crosses 10% relative threshold) -> Business Materiality = YES
    # Z-score is (28 - 25)/12.9 = +0.23 -> Statistical Unusualness = NO
    data = {
        "date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-06-01"],
        "val": [10.0, 30.0, 20.0, 40.0, 28.0]
    }
    pd.DataFrame(data).to_csv(temp_file, index=False)
    
    custom_defs_1 = {
        "Volatile_KPI": {
            "source": temp_file,
            "source_grain": "daily",
            "materiality_threshold": 0.10,
            "threshold_type": "relative",
            "minimum_history_days": 2
        }
    }
    
    res_1 = analyze_kpi_change("Volatile_KPI", custom_defs_1, temp_dir, ("2026-01-01", "2026-01-04"), ("2026-06-01", "2026-06-01"))
    
    assert res_1["materiality"]["crossed"] is True  # Material (12% change >= 10%)
    assert res_1["statistical_signal"]["unusual"] is False  # Not unusual (z-score around 0.23 < 2.0)
    
    # Scenario B: Highly stable dataset, small change
    # Baseline is extremely stable: 10.0, 10.1, 9.9, 10.0 (mean=10.0, std=0.0816)
    # Comparison is 10.3. Business threshold is 10% relative.
    # Change is (10.3 - 10.0)/10.0 = +3.0% (does not cross 10% threshold) -> Business Materiality = NO
    # Z-score is (10.3 - 10.0)/0.0816 = +3.67 -> Statistical Unusualness = YES
    data_stable = {
        "date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-06-01"],
        "val": [10.0, 10.1, 9.9, 10.0, 10.3]
    }
    pd.DataFrame(data_stable).to_csv(temp_file, index=True)
    
    custom_defs_2 = {
        "Volatile_KPI": {
            "source": temp_file,
            "source_grain": "daily",
            "materiality_threshold": 0.10,
            "threshold_type": "relative",
            "minimum_history_days": 2
        }
    }
    
    res_2 = analyze_kpi_change("Volatile_KPI", custom_defs_2, temp_dir, ("2026-01-01", "2026-01-04"), ("2026-06-01", "2026-06-01"))
    
    assert res_2["materiality"]["crossed"] is False  # Not material (3% change < 10%)
    assert res_2["statistical_signal"]["unusual"] is True  # Statistically unusual (z-score around 3.67 >= 2.0)
