import os
import pandas as pd
import numpy as np
from src.engine.drivers import profile_driver, compare_ai_assisted, get_numerator_and_denominator
from src.engine.materiality import get_date_column_and_grain

def analyze_ai_rollout(kpi_name, data_dir, config):
    """
    Evaluates Hypothesis 1: Whether the rollout is associated with KPI changes.
    Reuses compare_ai_assisted operational outputs.
    """
    normalized_name = kpi_name.replace(" ", "_")
    
    # Delegate and capture Q1 Baseline behavior
    ai_comp = compare_ai_assisted(kpi_name, data_dir, config)
    if ai_comp["status"] != "SUCCESS":
        return {
            "status": "NOT_AVAILABLE",
            "evidence_strength": "NOT_AVAILABLE",
            "reason": ai_comp.get("reason", "KPI not supported for AI comparison."),
            "direction_consistency": "NO_DATA",
            "avg_relative_difference": None,
            "supporting_signals": [],
            "limiting_signals": ["CSAT/Retention cannot be directly split by AI because the datasets lack ai_assisted dimension."],
            "limitations": [
                "Observational comparison only (no randomized assignment).",
                "AI and manual contacts may differ in case complexity or customer mix.",
                "CSAT and Retention lack ai_assisted dimension."
            ]
        }

    phases = ai_comp["phases"]
    q1_data = phases.get("Q1 Baseline", {})
    
    # Collect successful rollout phases (April, May, June)
    rollout_phases = ["April", "May", "June"]
    diffs = []
    rel_diffs = []
    
    for phase in rollout_phases:
        p_data = phases.get(phase, {})
        if p_data.get("status") == "SUCCESS":
            diffs.append(p_data["comparison"]["absolute_difference"])
            rel_diffs.append(p_data["comparison"]["relative_difference"])

    if not diffs:
        return {
            "status": "NOT_AVAILABLE",
            "evidence_strength": "NOT_AVAILABLE",
            "reason": "No successful rollout phases available.",
            "direction_consistency": "NO_DATA",
            "avg_relative_difference": None,
            "supporting_signals": [],
            "limiting_signals": [],
            "limitations": []
        }

    # Determine direction consistency
    all_positive = all(d > 0 for d in diffs)
    all_negative = all(d < 0 for d in diffs)
    
    if all_positive:
        consistency = "CONSISTENT_INCREASE"
    elif all_negative:
        consistency = "CONSISTENT_REDUCTION"
    else:
        consistency = "INCONSISTENT"

    avg_rel_diff = float(np.mean(rel_diffs))
    
    # Determine evidence strength
    if consistency == "INCONSISTENT":
        strength = "INCONCLUSIVE"
    else:
        abs_avg_rel = abs(avg_rel_diff)
        if abs_avg_rel >= 0.20:
            strength = "STRONG_ASSOCIATION"
        elif abs_avg_rel >= 0.05:
            strength = "MODERATE_ASSOCIATION"
        else:
            strength = "WEAK_ASSOCIATION"

    # Narrative signals matching Causality Policy
    if consistency == "INCONSISTENT":
        supporting = [
            f"AI-assisted contacts showed mixed directional differences across rollout months."
        ]
    else:
        direction_word = "lower" if consistency == "CONSISTENT_REDUCTION" else "higher"
        supporting = [
            f"AI-assisted contacts were consistently associated with {direction_word} {kpi_name} during rollout months.",
            f"Consistent direction of difference observed across all rollout months ({', '.join(rollout_phases)})."
        ]
    limiting = [
        "Observational comparison only (no randomized assignment).",
        "AI and manual contacts may differ in case complexity or customer mix.",
        "CSAT/Retention outcomes cannot be directly attributed due to schema limitation."
    ]

    return {
        "status": "SUCCESS",
        "kpi": kpi_name,
        "direction_consistency": consistency,
        "avg_relative_difference": avg_rel_diff,
        "evidence_strength": strength,
        "supporting_signals": supporting,
        "limiting_signals": limiting,
        "limitations": limiting,
        "phases": phases
    }

def analyze_crm_patch(kpi_name, data_dir, config):
    """
    Evaluates Hypothesis 2: Whether the CRM Cloud patch on May 4 is associated with unusual concentration.
    Uses support_daily.csv.
    """
    normalized_name = kpi_name.replace(" ", "_")
    kpi_def = config.get(normalized_name) or config.get(kpi_name)

    if not kpi_def:
        return {
            "status": "NOT_AVAILABLE",
            "evidence_strength": "NOT_AVAILABLE",
            "reason": f"KPI '{kpi_name}' is not defined."
        }

    # Strict operational dimension check
    if normalized_name not in ["AHT", "FCR", "Repeat_Contact_Rate"]:
        return {
            "status": "NOT_AVAILABLE",
            "evidence_strength": "NOT_AVAILABLE",
            "reason": "CRM patch hypothesis only valid for operational metrics AHT, FCR, Repeat Contact Rate.",
            "limitations": ["CSAT and Retention lack product-grain daily alignment for pre/post patch comparison."]
        }

    source_file = kpi_def.get("source")
    file_path = os.path.join(data_dir, source_file)
    if not os.path.exists(file_path):
        return {
            "status": "NOT_AVAILABLE",
            "evidence_strength": "NOT_AVAILABLE",
            "reason": f"Source file '{source_file}' does not exist."
        }

    df = pd.read_csv(file_path)

    # Date column check
    date_col, grain = get_date_column_and_grain(kpi_def)
    if date_col not in df.columns or "product" not in df.columns:
        return {
            "status": "NOT_AVAILABLE",
            "evidence_strength": "NOT_AVAILABLE",
            "reason": "Required columns ('date', 'product') missing from dataset."
        }

    df['date_parsed'] = pd.to_datetime(df[date_col])

    pre_start, pre_end = pd.to_datetime("2026-04-01"), pd.to_datetime("2026-05-03")
    post_start, post_end = pd.to_datetime("2026-05-04"), pd.to_datetime("2026-06-30")

    pre_df = df[(df['date_parsed'] >= pre_start) & (df['date_parsed'] <= pre_end)]
    post_df = df[(df['date_parsed'] >= post_start) & (df['date_parsed'] <= post_end)]

    if pre_df.empty or post_df.empty:
        return {
            "status": "NOT_AVAILABLE",
            "evidence_strength": "NOT_AVAILABLE",
            "reason": "Pre-patch or post-patch period contains no observations."
        }

    # Isolate CRM Cloud
    crm_pre = pre_df[pre_df["product"] == "CRM Cloud"]
    crm_post = post_df[post_df["product"] == "CRM Cloud"]
    
    # Isolate Control (Core ERP & Analytics Suite combined)
    ctrl_pre = pre_df[pre_df["product"].isin(["Core ERP", "Analytics Suite"])]
    ctrl_post = post_df[post_df["product"].isin(["Core ERP", "Analytics Suite"])]

    if ctrl_pre.empty or ctrl_post.empty:
        return {
            "status": "NOT_AVAILABLE",
            "evidence_strength": "NOT_AVAILABLE",
            "reason": "Control group (Core ERP / Analytics Suite) has no observations."
        }

    try:
        num_pre_crm, denom_pre_crm = get_numerator_and_denominator(crm_pre, kpi_name, kpi_def)
        num_post_crm, denom_post_crm = get_numerator_and_denominator(crm_post, kpi_name, kpi_def)
        
        num_pre_ctrl, denom_pre_ctrl = get_numerator_and_denominator(ctrl_pre, kpi_name, kpi_def)
        num_post_ctrl, denom_post_ctrl = get_numerator_and_denominator(ctrl_post, kpi_name, kpi_def)
    except Exception as e:
        return {
            "status": "NOT_AVAILABLE",
            "evidence_strength": "NOT_AVAILABLE",
            "reason": f"Calculation error: {e}"
        }

    if denom_pre_crm == 0 or denom_post_crm == 0 or denom_pre_ctrl == 0 or denom_post_ctrl == 0:
        return {
            "status": "NOT_AVAILABLE",
            "evidence_strength": "NOT_AVAILABLE",
            "reason": "Denominator is zero in one of the patch comparison segments."
        }

    val_pre_crm = num_pre_crm / denom_pre_crm
    val_post_crm = num_post_crm / denom_post_crm
    crm_change = val_post_crm - val_pre_crm

    val_pre_ctrl = num_pre_ctrl / denom_pre_ctrl
    val_post_ctrl = num_post_ctrl / denom_post_ctrl
    ctrl_change = val_post_ctrl - val_pre_ctrl

    crm_differential = crm_change - ctrl_change

    # Determine deterioration flag and differential signal
    # AHT: increase is deterioration
    # FCR: decrease is deterioration
    # Repeat Contact: increase is deterioration
    deteriorated = False
    crm_diff = 0.0
    threshold = 0.0
    
    # AHT: values are minute-normalized by get_numerator_and_denominator()
    # FCR & Repeat Contact: fractional values on 0-1 scale
    if normalized_name == "AHT":
        deteriorated = (crm_change > 0)
        crm_diff = crm_differential  # positive is more deterioration
        # AHT threshold = 0.10 minutes (AHT values are minute-normalized)
        threshold = 0.1
    elif normalized_name == "FCR":
        deteriorated = (crm_change < 0)
        crm_diff = -crm_differential  # positive is more deterioration (greater drop)
        # FCR threshold = 0.01 on 0-1 scale
        threshold = 0.01
    elif normalized_name == "Repeat_Contact_Rate":
        deteriorated = (crm_change > 0)
        crm_diff = crm_differential  # positive is more deterioration
        # Repeat Contact Rate threshold = 0.01 on 0-1 scale
        threshold = 0.01

    # Concentration rules
    classification = "NOT_CONCENTRATED"
    if deteriorated:
        if crm_diff > threshold:
            # Check if CRM change was at least double the control deterioration (or if control actually improved/remained stable)
            ctrl_deteriorated = (ctrl_change > 0) if normalized_name in ["AHT", "Repeat_Contact_Rate"] else (ctrl_change < 0)
            if not ctrl_deteriorated or abs(crm_change) > 2 * abs(ctrl_change):
                classification = "CONCENTRATED"
            else:
                classification = "PARTIALLY_CONCENTRATED"
        elif crm_diff > 0:
            classification = "INCONCLUSIVE"

    # Strength mapping
    strength_map = {
        "CONCENTRATED": "STRONG_ASSOCIATION",
        "PARTIALLY_CONCENTRATED": "MODERATE_ASSOCIATION",
        "INCONCLUSIVE": "INCONCLUSIVE",
        "NOT_CONCENTRATED": "WEAK_ASSOCIATION"
    }
    evidence_strength = strength_map[classification]

    supporting = [
        f"Pre/post differential association signal is {crm_differential:+.6f}.",
        f"Patch date alignment post-patch observed change classified as {classification}."
    ]
    limiting = [
        "Observational pre/post comparison (no randomized group assignment).",
        "Control group also exhibits temporal shifts, suggesting other global factors (like AI rollout)."
    ]

    return {
        "status": "SUCCESS",
        "kpi": kpi_name,
        "crm_pre": val_pre_crm,
        "crm_post": val_post_crm,
        "crm_change": crm_change,
        "control_pre": val_pre_ctrl,
        "control_post": val_post_ctrl,
        "control_change": ctrl_change,
        "differential_signal": crm_differential,
        "classification": classification,
        "evidence_strength": evidence_strength,
        "supporting_signals": supporting,
        "limiting_signals": limiting,
        "limitations": limiting
    }

def analyze_mix_shift(kpi_name, dimension, baseline_period, comparison_period, data_dir, config):
    """
    Evaluates Hypothesis 3: Volume mix shift contribution relative to overall change.
    Reuses profile_driver from drivers.py.
    """
    res = profile_driver(kpi_name, dimension, baseline_period, comparison_period, data_dir, config)
    if res["status"] != "SUCCESS":
        return {
            "status": "NOT_AVAILABLE",
            "evidence_strength": "NOT_AVAILABLE",
            "reason": res.get("reason", "KPI/dimension not supported.")
        }

    overall_change = res["overall_change"]
    if overall_change == 0.0:
        return {
            "status": "NOT_AVAILABLE",
            "evidence_strength": "NOT_AVAILABLE",
            "reason": "Overall change is zero; mix contribution share cannot be calculated."
        }

    total_mix = sum(d["mix_effect"] for d in res["drivers"])
    total_rate = sum(d["rate_effect"] for d in res["drivers"])
    
    mix_share = abs(total_mix) / abs(overall_change)

    if mix_share < 0.20:
        classification = "LOW"
        evidence_strength = "WEAK_ASSOCIATION"
    elif mix_share < 0.50:
        classification = "MODERATE"
        evidence_strength = "MODERATE_ASSOCIATION"
    else:
        classification = "HIGH"
        evidence_strength = "STRONG_ASSOCIATION"

    supporting = [
        f"Reconciled mix share is {mix_share:.2%}.",
        f"Total mix effect is {total_mix:+.6f} compared to rate effect of {total_rate:+.6f}."
    ]
    limiting = [
        "Shapley decomposition is a mathematical attribution of variance, not a proof of physical mix behavior."
    ]

    return {
        "status": "SUCCESS",
        "kpi": kpi_name,
        "dimension": dimension,
        "overall_change": overall_change,
        "total_mix_effect": total_mix,
        "total_rate_effect": total_rate,
        "reconciliation_error": res["reconciliation_error"],
        "mix_share": mix_share,
        "classification": classification,
        "evidence_strength": evidence_strength,
        "supporting_signals": supporting,
        "limiting_signals": limiting,
        "limitations": limiting
    }

def synthesize_hypotheses(kpi_name, data_dir, config, baseline_period, comparison_period, mix_dimension):
    """
    Synthesizes H1 (AI Rollout), H2 (CRM Patch), and H3 (Mix Shift) results and
    determines the overall evidence state.
    """
    h1 = analyze_ai_rollout(kpi_name, data_dir, config)
    h2 = analyze_crm_patch(kpi_name, data_dir, config)
    h3 = analyze_mix_shift(kpi_name, mix_dimension, baseline_period, comparison_period, data_dir, config)

    # Deterministic overall evidence state logic.
    # Note: These represent deterministic rules specifically designed to model and synthesize
    # the evidence-state for the simulated StoryProof investigation scenario.
    overall_state = "NOT_JUSTIFIED"
    reason = "No strong evidence was identified in the source datasets."

    # Current StoryProof scenario logic:
    # 1. AI rollout shows strong association with operational shifts (AHT drops, Repeat Contacts rise)
    # 2. But CRM Cloud patch also happened, creating a confounder
    # 3. CSAT/Retention cannot be split by AI, creating a severe data limitation
    # 4. If both AI rollout and CRM patch are active, or if data limitations are present, overall state is INVESTIGATION_REQUIRED
    
    strengths = [h1["evidence_strength"], h2["evidence_strength"]]
    active_associations = [s for s in strengths if s in ["STRONG_ASSOCIATION", "MODERATE_ASSOCIATION"]]
    
    if len(active_associations) >= 2:
        overall_state = "INVESTIGATION_REQUIRED"
        reason = "Multiple competing explanations (AI rollout and CRM Cloud patch) exhibit moderate-to-strong operational associations in the same period, creating a confounding scenario."
    elif h1["evidence_strength"] == "NOT_AVAILABLE" and h2["evidence_strength"] == "NOT_AVAILABLE":
        # CSAT/Retention case
        overall_state = "INVESTIGATION_REQUIRED"
        reason = "Outcome metrics cannot be directly attributed to AI-assistance or the patch due to data schema limitations (lack of ai_assisted column in CSAT and Retention logs)."
    elif h1["evidence_strength"] == "STRONG_ASSOCIATION" and h3.get("evidence_strength") == "STRONG_ASSOCIATION":
        overall_state = "INVESTIGATION_REQUIRED"
        reason = "AI rollout has a strong operational association, but the mix contribution is also classified as HIGH, indicating that volume shifts represent a significant competing explanation."
    elif h1["evidence_strength"] == "STRONG_ASSOCIATION" or h2["evidence_strength"] == "STRONG_ASSOCIATION":
        # Even if one is strong, if there are known confounding events or limitations, we require investigation
        overall_state = "INVESTIGATION_REQUIRED"
        reason = "Operational metrics show a strong association with the rollout, but overall outcome metrics (CSAT/Retention) cannot be split, requiring qualitative evidence checks (Milestone 3C) to rule out an AHT efficiency trap."
    elif all(s in ["WEAK_ASSOCIATION", "NOT_AVAILABLE", "INCONCLUSIVE"] for s in strengths):
        overall_state = "NOT_JUSTIFIED"
        reason = "Observed KPI movements do not show strong operational associations with the rollout or patch."

    return {
        "kpi": kpi_name,
        "hypotheses": {
            "ai_rollout": h1,
            "crm_patch": h2,
            "mix_shift": h3
        },
        "overall_evidence_state": overall_state,
        "reason": reason
    }
