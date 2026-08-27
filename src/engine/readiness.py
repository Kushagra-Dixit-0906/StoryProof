import os
import re

def calculate_readiness_score(flags):
    """
    Computes the numeric readiness score (0 to 100) based on active penalty flags.
    """
    score = 100
    if flags.get("insufficient_history"):
        score -= 30
    if flags.get("high_ambiguity"):
        score -= 30
    if flags.get("unverified_material_change"):
        score -= 20
    if flags.get("metric_tension_detected"):
        score -= 20
    return max(0, min(100, score))

def evaluate_decision_readiness(synthesis_result, persona=None):
    """
    Performs a deterministic, auditable quality gate analysis on the synthesis report
    to determine if the findings are ready for executive decision-making.
    
    Evaluates evidence sufficiency under observational/associational evidence only,
    never describing causality as established or "sound".
    
    Parameters:
      synthesis_result: Dict returned by generate_synthesis_report.
      persona: Optional string ('CX_MANAGER' or 'OPERATIONS_MANAGER') to filter metrics.
      
    Returns:
      A structured dictionary containing readiness state, score, flags, details, and recommendation.
    """
    causality_disclaimer = "The available evidence does not establish causality; observed changes represent associations and candidate explanations only."

    if synthesis_result is None or not isinstance(synthesis_result, dict):
        return {
            "status": "NOT_AVAILABLE",
            "reason": "Synthesis report is missing or invalid.",
            "decision_readiness": {}
        }

    if synthesis_result.get("status") != "SUCCESS" or "report" not in synthesis_result:
        return {
            "status": "NOT_AVAILABLE",
            "reason": "Synthesis report has failed or has no valid report section.",
            "decision_readiness": {}
        }

    report = synthesis_result.get("report", [])
    
    # 1. Determine evaluation KPI scope based on persona
    # Primary KPIs in StoryProof:
    # AHT, FCR, Repeat_Contact_Rate, CSAT, Retention_Rate, AI_Resolution_Rate
    all_kpis = ["AHT", "FCR", "CSAT", "Repeat_Contact_Rate", "Retention_Rate", "AI_Resolution_Rate"]
    
    if persona == "CX_MANAGER":
        kpi_scope = ["CSAT", "Retention_Rate", "FCR", "Repeat_Contact_Rate"]
    elif persona == "OPERATIONS_MANAGER":
        kpi_scope = ["AHT", "FCR", "Repeat_Contact_Rate", "AI_Resolution_Rate"]
    else:
        kpi_scope = all_kpis

    # 2. Extract statements and analyze across sections
    all_statements = []
    for section in report:
        title = section.get("title", "")
        statements = section.get("statements", [])
        for stmt in statements:
            all_statements.append({
                "text": stmt.get("text", ""),
                "classification": stmt.get("classification", "ASSOCIATION"),
                "structured_refs": stmt.get("structured_refs", []),
                "evidence_refs": stmt.get("evidence_refs", []),
                "section_title": title
            })

    # Flags to populate
    insufficient_history = False
    high_ambiguity = False
    unverified_material_change = False
    metric_tension_detected = False

    insufficient_history_metrics = []
    confounding_explanations = []
    tensions = []
    unverified_metrics = []

    # Rule 1: Insufficient History Check
    # Scan for LIMITATION statements in "KPI Movement" or "Data Limitations" containing "insufficient history"
    for stmt in all_statements:
        text_lower = stmt["text"].lower()
        if stmt["classification"] == "LIMITATION" and ("insufficient history" in text_lower or "insufficient historical data" in text_lower):
            # Check which KPI this belongs to
            for kpi in kpi_scope:
                # Support match for underscores or spaces (e.g. AI_Resolution_Rate vs AI Resolution Rate)
                kpi_pat = kpi.replace("_", " ").lower()
                kpi_pat_alt = kpi.lower()
                if kpi_pat in text_lower or kpi_pat_alt in text_lower:
                    if kpi not in insufficient_history_metrics:
                        insufficient_history_metrics.append(kpi)
                        insufficient_history = True

    # Rule 2: Confounding & Ambiguity Check
    # Scan "Competing Hypotheses" section. For any KPI in scope, check if multiple hypotheses show moderate/strong association.
    kpi_associations = {kpi: [] for kpi in kpi_scope}
    for stmt in all_statements:
        if stmt["section_title"] == "Competing Hypotheses":
            text_lower = stmt["text"].lower()
            # Identify which KPI
            matched_kpi = None
            for kpi in kpi_scope:
                kpi_pat = kpi.replace("_", " ").lower()
                kpi_pat_alt = kpi.lower()
                # Special checks for Repeat Contact Rate mapping
                if kpi == "Repeat_Contact_Rate" and ("repeat contact" in text_lower or "repeat_contact" in text_lower):
                    matched_kpi = kpi
                    break
                elif kpi_pat in text_lower or kpi_pat_alt in text_lower:
                    matched_kpi = kpi
                    break
            
            if matched_kpi:
                # Check strength
                strength = None
                if "strong_association" in text_lower or "strong association" in text_lower:
                    strength = "STRONG_ASSOCIATION"
                elif "moderate_association" in text_lower or "moderate association" in text_lower:
                    strength = "MODERATE_ASSOCIATION"
                
                if strength:
                    # Identify the hypothesis
                    hyp_name = "unknown"
                    if "ai rollout" in text_lower or "assistant" in text_lower:
                        hyp_name = "AI Rollout"
                    elif "crm patch" in text_lower or "crm cloud" in text_lower:
                        hyp_name = "CRM Patch"
                    elif "mix shift" in text_lower or "mix_shift" in text_lower:
                        hyp_name = "Mix Shift"
                    
                    kpi_associations[matched_kpi].append(f"{hyp_name} ({strength})")

    # If any KPI has >= 2 strong/moderate associations, or if the report explicitly mentions "does not determine the primary explanation"
    for kpi, assocs in kpi_associations.items():
        if len(assocs) >= 2:
            high_ambiguity = True
            confounding_explanations.append(
                f"KPI '{kpi}' has multiple competing explanations: {', '.join(assocs)}."
            )

    # General check for "Investigation Conclusion" or similar sections asserting ambiguity
    for stmt in all_statements:
        text_lower = stmt["text"].lower()
        if "does not determine the primary explanation" in text_lower or "investigation required" in text_lower:
            high_ambiguity = True
            if "primary explanation remains undetermined" not in confounding_explanations:
                confounding_explanations.append("The primary explanation remains undetermined from current observational logs.")

    # Rule 3: Qualitative Verification Check
    # Apply ONLY to MATERIAL quantitative changes in scope.
    # First, find which KPIs in scope had a MATERIAL change.
    material_kpis = []
    for stmt in all_statements:
        if stmt["section_title"] in ["Materiality & Statistical Signal", "KPI Movement"]:
            text_lower = stmt["text"].lower()
            if "material" in text_lower and "non-material" not in text_lower:
                for kpi in kpi_scope:
                    kpi_pat = kpi.replace("_", " ").lower()
                    kpi_pat_alt = kpi.lower()
                    # Special check for Repeat Contact Rate
                    if kpi == "Repeat_Contact_Rate" and ("repeat contact" in text_lower or "repeat_contact" in text_lower):
                        if kpi not in material_kpis:
                            material_kpis.append(kpi)
                    elif kpi_pat in text_lower or kpi_pat_alt in text_lower:
                        if kpi not in material_kpis:
                            material_kpis.append(kpi)

    # For each material KPI, verify that there is at least one statement in the report
    # mentioning that KPI and containing non-empty evidence_refs.
    for kpi in material_kpis:
        kpi_has_evidence = False
        for stmt in all_statements:
            text_lower = stmt["text"].lower()
            kpi_pat = kpi.replace("_", " ").lower()
            kpi_pat_alt = kpi.lower()
            # If statement contains KPI name and has evidence references
            is_match = False
            if kpi == "Repeat_Contact_Rate" and ("repeat contact" in text_lower or "repeat_contact" in text_lower):
                is_match = True
            elif kpi_pat in text_lower or kpi_pat_alt in text_lower:
                is_match = True
            
            if is_match and len(stmt["evidence_refs"]) > 0:
                kpi_has_evidence = True
                break
        
        if not kpi_has_evidence:
            unverified_material_change = True
            unverified_metrics.append(kpi)

    # Rule 4: Metric Tension & Contradiction Check
    # Scan "Contradictory / Tension Evidence" section.
    for stmt in all_statements:
        if stmt["section_title"] == "Contradictory / Tension Evidence":
            # Exclude fallback texts
            if "no matching qualitative" not in stmt["text"].lower() and stmt["classification"] != "LIMITATION":
                metric_tension_detected = True
                if stmt["text"] not in tensions:
                    tensions.append(stmt["text"])

    # 3. Calculate numeric score
    flags = {
        "insufficient_history": insufficient_history,
        "high_ambiguity": high_ambiguity,
        "unverified_material_change": unverified_material_change,
        "metric_tension_detected": metric_tension_detected
    }
    
    readiness_score = calculate_readiness_score(flags)

    # 4. State Assignment
    if insufficient_history:
        overall_state = "NOT_READY_INSUFFICIENT_DATA"
    elif high_ambiguity:
        overall_state = "NOT_READY_AMBIGUITY"
    elif readiness_score >= 80:
        overall_state = "READY"
    else:
        overall_state = "READY_WITH_RESERVATIONS"

    # 5. Formulate recommendations dynamically (observational, strictly non-causal)
    recommendation_parts = []
    if insufficient_history:
        recommendation_parts.append(
            "Strategic decisions should be deferred because some KPIs exhibit insufficient history to establish reliable baselines. Collect more data to satisfy history requirements."
        )
    if high_ambiguity:
        recommendation_parts.append(
            "Strategic action is not recommended at this time. Multiple competing factors, such as the AI assistant rollout and the CRM Cloud software patch, exhibit overlapping operational associations, creating significant ambiguity."
        )
    if metric_tension_detected:
        recommendation_parts.append(
            "Proceed with caution. Efficiency gains in some operational metrics coincide with negative qualitative feedback regarding interaction resolution, indicating potential customer experience risks."
        )
    if unverified_material_change:
        recommendation_parts.append(
            "Further verification is recommended. Certain material quantitative changes lack corresponding qualitative evidence links. Validate these shifts against transcripts before proceeding."
        )
    
    if not recommendation_parts:
        recommendation_parts.append(
            "Operational metrics show consistent associations and are verified by qualitative evidence. The analysis is ready for strategic review."
        )

    recommendation = " ".join(recommendation_parts)

    return {
        "status": "SUCCESS",
        "decision_readiness": {
            "overall_state": overall_state,
            "readiness_score": int(readiness_score),
            "flags": flags,
            "details": {
                "insufficient_history_metrics": sorted(insufficient_history_metrics),
                "confounding_explanations": sorted(confounding_explanations),
                "tensions": sorted(tensions),
                "unverified_metrics": sorted(unverified_metrics)
            },
            "recommendation": recommendation,
            "causality_disclaimer": causality_disclaimer
        }
    }
