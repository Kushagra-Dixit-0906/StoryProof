import os
import pandas as pd
import numpy as np
import yaml
from src.engine.materiality import get_date_column_and_grain

def get_numerator_and_denominator(sub_df, kpi_name, kpi_def):
    """
    Computes the raw numerator and denominator for a KPI on the given dataframe subset.
    Ensures unit conversions (like AHT seconds to minutes) are applied.
    """
    if sub_df.empty:
        return 0.0, 0.0

    normalized_name = kpi_name.replace(" ", "_")

    if normalized_name == "CSAT":
        # CSAT is naturally on a 0-100 scale.
        # Numerator: sum(csat_score * survey_responses)
        # Denominator: sum(survey_responses)
        num = (sub_df["csat_score"] * sub_df["survey_responses"]).sum()
        den = sub_df["survey_responses"].sum()
        return float(num), float(den)

    num_field = kpi_def.get("numerator_field")
    den_field = kpi_def.get("denominator_field")

    if not num_field or not den_field:
        raise ValueError(f"Numerator or denominator field configuration is missing for KPI '{kpi_name}'.")

    if num_field not in sub_df.columns or den_field not in sub_df.columns:
        raise ValueError(
            f"Numerator field '{num_field}' or denominator field '{den_field}' missing from dataset."
        )

    num = sub_df[num_field].sum()
    den = sub_df[den_field].sum()

    # Unit Conversion: AHT raw handling time is seconds, display is minutes
    raw_unit = kpi_def.get("raw_unit")
    display_unit = kpi_def.get("display_unit")
    if normalized_name == "AHT" and raw_unit == "seconds" and display_unit == "minutes":
        # Convert Handling Seconds to Handling Minutes
        num = num / 60.0

    return float(num), float(den)

def profile_driver(kpi_name, dimension, baseline_period, comparison_period, data_dir, config):
    """
    Profiles KPI performance across a valid dimension using mix-rate decomposition.
    
    Parameters:
      kpi_name: Name of the KPI to analyze (e.g. 'AHT', 'CSAT')
      dimension: Column name to slice the data by (e.g. 'product', 'customer_segment')
      baseline_period: Tuple of (start_date, end_date) as strings
      comparison_period: Tuple of (start_date, end_date) as strings
      data_dir: Directory containing the data CSV files
      config: Loaded dict containing KPI YAML definitions
      
    Returns:
      A structured dictionary representing driver contributions and ranking.
    """
    normalized_name = kpi_name.replace(" ", "_")
    kpi_def = config.get(normalized_name) or config.get(kpi_name)

    if not kpi_def:
        return {
            "status": "NOT_AVAILABLE",
            "reason": f"KPI '{kpi_name}' is not defined in KPI definitions.",
            "provenance": {
                "source_dataset": None,
                "kpi": kpi_name,
                "dimension": dimension,
                "baseline_period": baseline_period,
                "comparison_period": comparison_period,
                "aggregation_method": None
            }
        }

    source_file = kpi_def.get("source")
    provenance = {
        "source_dataset": source_file,
        "kpi": kpi_name,
        "dimension": dimension,
        "baseline_period": baseline_period,
        "comparison_period": comparison_period,
        "aggregation_method": kpi_def.get("aggregation_method")
    }

    if not source_file:
        return {
            "status": "NOT_AVAILABLE",
            "reason": f"KPI '{kpi_name}' does not specify a source file.",
            "provenance": provenance
        }

    file_path = os.path.join(data_dir, source_file)
    if not os.path.exists(file_path):
        return {
            "status": "NOT_AVAILABLE",
            "reason": f"Source file '{source_file}' does not exist.",
            "provenance": provenance
        }

    # Load dataset
    df = pd.read_csv(file_path)

    # Check if dimension column exists in the dataset
    if dimension not in df.columns:
        return {
            "status": "NOT_AVAILABLE",
            "reason": f"Dimension '{dimension}' does not exist in the source dataset.",
            "provenance": provenance
        }

    # Determine date column and grain
    date_col, grain = get_date_column_and_grain(kpi_def)
    if date_col not in df.columns:
        return {
            "status": "NOT_AVAILABLE",
            "reason": f"Date column '{date_col}' missing from data file '{source_file}'.",
            "provenance": provenance
        }

    # Parse dates and filter periods
    df['date_parsed'] = pd.to_datetime(df[date_col])
    b_start, b_end = pd.to_datetime(baseline_period[0]), pd.to_datetime(baseline_period[1])
    c_start, c_end = pd.to_datetime(comparison_period[0]), pd.to_datetime(comparison_period[1])

    baseline_df = df[(df['date_parsed'] >= b_start) & (df['date_parsed'] <= b_end)]
    comparison_df = df[(df['date_parsed'] >= c_start) & (df['date_parsed'] <= c_end)]

    if baseline_df.empty or comparison_df.empty:
        return {
            "status": "NOT_AVAILABLE",
            "reason": "Baseline or comparison period contains no observations.",
            "provenance": provenance
        }

    # Calculate global numerators/denominators
    try:
        global_num0, global_denom0 = get_numerator_and_denominator(baseline_df, kpi_name, kpi_def)
        global_num1, global_denom1 = get_numerator_and_denominator(comparison_df, kpi_name, kpi_def)
    except Exception as e:
        return {
            "status": "NOT_AVAILABLE",
            "reason": f"Error computing baseline/comparison values: {e}",
            "provenance": provenance
        }

    if global_denom0 == 0 or global_denom1 == 0:
        return {
            "status": "NOT_AVAILABLE",
            "reason": "Denominator is zero in baseline or comparison period.",
            "provenance": provenance
        }

    # Global KPI rates
    r0_global = global_num0 / global_denom0
    r1_global = global_num1 / global_denom1
    overall_change = r1_global - r0_global

    # Identify all segment values across both periods
    unique_vals = sorted(list(set(baseline_df[dimension].dropna().unique()) | set(comparison_df[dimension].dropna().unique())))
    
    segments_data = []

    for val in unique_vals:
        b_sub = baseline_df[baseline_df[dimension] == val]
        c_sub = comparison_df[comparison_df[dimension] == val]

        num0_i, denom0_i = get_numerator_and_denominator(b_sub, kpi_name, kpi_def)
        num1_i, denom1_i = get_numerator_and_denominator(c_sub, kpi_name, kpi_def)

        # Denominator share (exposure)
        w0_i = denom0_i / global_denom0
        w1_i = denom1_i / global_denom1

        # Rates calculation with safe zero-volume category handling
        if denom0_i > 0:
            r0_i = num0_i / denom0_i
        else:
            r0_i = None

        if denom1_i > 0:
            r1_i = num1_i / denom1_i
        else:
            r1_i = None

        # Resolve undefined rate cases:
        if denom0_i == 0 and denom1_i == 0:
            r0_i = 0.0
            r1_i = 0.0
        elif denom0_i == 0 and denom1_i > 0:
            r0_i = r1_i
        elif denom1_i == 0 and denom0_i > 0:
            r1_i = r0_i

        rate_change_i = r1_i - r0_i
        exposure_change_i = w1_i - w0_i

        # Midpoint/Shapley-style decomposition:
        rate_effect_i = ((w0_i + w1_i) / 2.0) * rate_change_i
        mix_effect_i = ((r0_i + r1_i) / 2.0) * exposure_change_i
        total_contribution_i = rate_effect_i + mix_effect_i

        # Safe relative change
        rel_change_i = rate_change_i / r0_i if r0_i != 0.0 else 0.0

        segments_data.append({
            "dimension_value": val,
            "baseline_value": r0_i,
            "comparison_value": r1_i,
            "absolute_change": rate_change_i,
            "relative_change": rel_change_i,
            "baseline_exposure": w0_i,
            "comparison_exposure": w1_i,
            "rate_effect": rate_effect_i,
            "mix_effect": mix_effect_i,
            "total_contribution": total_contribution_i,
            "baseline_denominator": denom0_i,
            "comparison_denominator": denom1_i
        })

    # Reconciliation and contribution shares
    sum_contributions = sum(s["total_contribution"] for s in segments_data)
    reconciliation_error = float(overall_change - sum_contributions)

    for s in segments_data:
        if overall_change != 0.0:
            s["contribution_share"] = float(s["total_contribution"] / overall_change)
        else:
            s["contribution_share"] = 0.0

    # Rank dimensions by contribution_magnitude (abs of total contribution)
    segments_data_sorted = sorted(segments_data, key=lambda x: abs(x["total_contribution"]), reverse=True)

    for rank, s in enumerate(segments_data_sorted, 1):
        s["rank"] = rank

    reconciliation_info = {
        "overall_change": overall_change,
        "sum_contributions": sum_contributions,
        "reconciliation_error": reconciliation_error,
        "is_reconciled": bool(abs(reconciliation_error) <= 1e-9)
    }

    return {
        "status": "SUCCESS",
        "provenance": provenance,
        "global_baseline": r0_global,
        "global_comparison": r1_global,
        "overall_change": overall_change,
        "reconciliation_error": reconciliation_error,
        "reconciliation_info": reconciliation_info,
        "drivers": segments_data_sorted
    }

def compare_ai_assisted(kpi_name, data_dir, config):
    """
    Compares metrics for AI-assisted vs non-AI-assisted support contacts.
    Only valid for: AHT, FCR, and Repeat Contact Rate.
    Evaluates across rollout phases: Q1 Baseline, April, May, and June.
    """
    normalized_name = kpi_name.replace(" ", "_")
    kpi_def = config.get(normalized_name) or config.get(kpi_name)

    if not kpi_def:
        return {
            "status": "NOT_AVAILABLE",
            "reason": f"KPI '{kpi_name}' is not defined in KPI definitions."
        }

    # Strict operational dimension check
    if normalized_name not in ["AHT", "FCR", "Repeat_Contact_Rate"]:
        return {
            "status": "NOT_AVAILABLE",
            "reason": "Source dataset does not contain ai_assisted dimension."
        }

    source_file = kpi_def.get("source")
    file_path = os.path.join(data_dir, source_file)
    if not os.path.exists(file_path):
        return {
            "status": "NOT_AVAILABLE",
            "reason": f"Source file '{source_file}' does not exist."
        }

    df = pd.read_csv(file_path)

    if "ai_assisted" not in df.columns:
        return {
            "status": "NOT_AVAILABLE",
            "reason": "Source dataset does not contain ai_assisted dimension."
        }

    # Parse dates
    date_col, grain = get_date_column_and_grain(kpi_def)
    df['date_parsed'] = pd.to_datetime(df[date_col])

    phases = {
        "Q1 Baseline": ("2026-01-01", "2026-03-31"),
        "April": ("2026-04-01", "2026-04-30"),
        "May": ("2026-05-01", "2026-05-31"),
        "June": ("2026-06-01", "2026-06-30")
    }

    results = {}

    for phase_name, (start_dt, end_dt) in phases.items():
        phase_df = df[(df['date_parsed'] >= pd.to_datetime(start_dt)) & (df['date_parsed'] <= pd.to_datetime(end_dt))]
        
        if phase_df.empty:
            results[phase_name] = {
                "status": "NO_OBSERVATIONS",
                "reason": f"No observations in phase {phase_name}"
            }
            continue

        ai_df = phase_df[phase_df["ai_assisted"] == True]
        non_ai_df = phase_df[phase_df["ai_assisted"] == False]

        den_field = kpi_def.get("denominator_field")
        total_denom = phase_df[den_field].sum() if den_field in phase_df.columns else 0
        total_contacts = phase_df["contacts"].sum() if "contacts" in phase_df.columns else 0

        if total_denom == 0 or total_contacts == 0:
            results[phase_name] = {
                "status": "ZERO_DENOMINATOR",
                "reason": f"Denominator or contacts is zero in phase {phase_name}"
            }
            continue

        try:
            num_ai, denom_ai = get_numerator_and_denominator(ai_df, kpi_name, kpi_def)
            num_non_ai, denom_non_ai = get_numerator_and_denominator(non_ai_df, kpi_name, kpi_def)
        except Exception as e:
            results[phase_name] = {
                "status": "ERROR",
                "reason": f"Error calculating values: {e}"
            }
            continue

        contacts_ai = ai_df["contacts"].sum() if "contacts" in ai_df.columns else 0

        # Safe guard for zero AI observations
        if len(ai_df) == 0 or denom_ai == 0 or contacts_ai == 0:
            kpi_non_ai = num_non_ai / denom_non_ai if denom_non_ai > 0 else 0.0
            denom_exposure_non_ai = denom_non_ai / total_denom
            contacts_non_ai = non_ai_df["contacts"].sum() if "contacts" in non_ai_df.columns else 0
            contact_share_non_ai = contacts_non_ai / total_contacts
            
            results[phase_name] = {
                "status": "NO_AI_BASELINE",
                "ai_assisted": {
                    "kpi": None,
                    "denominator_exposure": 0.0,
                    "contact_share": 0.0,
                    "denominator": 0.0,
                    "contacts": 0
                },
                "non_ai_assisted": {
                    "kpi": kpi_non_ai,
                    "denominator_exposure": denom_exposure_non_ai,
                    "contact_share": contact_share_non_ai,
                    "denominator": denom_non_ai,
                    "contacts": int(contacts_non_ai)
                },
                "comparison": {
                    "absolute_difference": None,
                    "relative_difference": None
                }
            }
            continue

        kpi_ai = num_ai / denom_ai if denom_ai > 0 else 0.0
        kpi_non_ai = num_non_ai / denom_non_ai if denom_non_ai > 0 else 0.0

        denom_exposure_ai = denom_ai / total_denom
        denom_exposure_non_ai = denom_non_ai / total_denom

        contacts_non_ai = non_ai_df["contacts"].sum() if "contacts" in non_ai_df.columns else 0

        contact_share_ai = contacts_ai / total_contacts
        contact_share_non_ai = contacts_non_ai / total_contacts

        abs_diff = kpi_ai - kpi_non_ai
        rel_diff = abs_diff / kpi_non_ai if kpi_non_ai != 0.0 else 0.0

        results[phase_name] = {
            "status": "SUCCESS",
            "ai_assisted": {
                "kpi": kpi_ai,
                "denominator_exposure": denom_exposure_ai,
                "contact_share": contact_share_ai,
                "denominator": denom_ai,
                "contacts": int(contacts_ai)
            },
            "non_ai_assisted": {
                "kpi": kpi_non_ai,
                "denominator_exposure": denom_exposure_non_ai,
                "contact_share": contact_share_non_ai,
                "denominator": denom_non_ai,
                "contacts": int(contacts_non_ai)
            },
            "comparison": {
                "absolute_difference": abs_diff,
                "relative_difference": rel_diff
            }
        }

    return {
        "status": "SUCCESS",
        "kpi": kpi_name,
        "phases": results
    }
