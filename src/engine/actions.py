import re

def generate_action_recommendations(synthesis_result, persona_views):
    """
    Deterministic Action Recommendation Engine that translates verified KPI insights,
    drivers, and readiness evaluations into actionable, persona-specific recommendations.
    
    Frames recommendations using strictly observational/associational terms, 
    preserving the strict causality-policy safeguards and disclaimers.
    
    Parameters:
      synthesis_result: Dict returned by generate_synthesis_report.
      persona_views: Dict returned by generate_persona_views.
      
    Returns:
      A structured dictionary containing recommended actions for CX and Operations personas.
    """
    causality_disclaimer = "The available evidence does not establish causality; observed changes represent associations and candidate explanations only."

    if (synthesis_result is None or not isinstance(synthesis_result, dict) or
        synthesis_result.get("status") != "SUCCESS" or "report" not in synthesis_result):
        return {
            "status": "NOT_AVAILABLE",
            "persona_actions": {}
        }

    if (persona_views is None or not isinstance(persona_views, dict) or
        persona_views.get("status") != "SUCCESS" or "personas" not in persona_views):
        return {
            "status": "NOT_AVAILABLE",
            "persona_actions": {}
        }

    report = synthesis_result.get("report", [])
    
    # Extract all report statements for deep parsing
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

    # Collect material KPIs dynamically from Materiality & Statistical Signal or KPI Movement
    material_kpis = []
    # Direction mappings
    # positive changes: AHT decrease, CSAT increase, FCR increase, Repeat_Contact_Rate decrease, Retention_Rate increase, AI_Resolution_Rate increase
    kpi_directions = {}
    
    kpis_of_interest = ["AHT", "FCR", "CSAT", "Repeat_Contact_Rate", "Retention_Rate", "AI_Resolution_Rate"]
    
    # Parse KPI movement details
    for stmt in all_statements:
        text_lower = stmt["text"].lower()
        
        # Parse material flags
        if stmt["section_title"] in ["Materiality & Statistical Signal", "KPI Movement"]:
            if "material" in text_lower and "non-material" not in text_lower:
                for kpi in kpis_of_interest:
                    kpi_pat = kpi.replace("_", " ").lower()
                    kpi_pat_alt = kpi.lower()
                    if kpi == "Repeat_Contact_Rate" and ("repeat contact" in text_lower or "repeat_contact" in text_lower):
                        if kpi not in material_kpis:
                            material_kpis.append(kpi)
                    elif kpi_pat in text_lower or kpi_pat_alt in text_lower:
                        if kpi not in material_kpis:
                            material_kpis.append(kpi)
                            
        # Parse direction
        if stmt["section_title"] == "KPI Movement":
            # Example text: "AHT changed from 10.16 to 5.77 minutes (absolute change: -4.39 minutes, relative change: -43.2%)."
            for kpi in kpis_of_interest:
                kpi_pat = kpi.replace("_", " ").lower()
                kpi_pat_alt = kpi.lower()
                matched = False
                if kpi == "Repeat_Contact_Rate" and ("repeat contact" in text_lower or "repeat_contact" in text_lower):
                    matched = True
                elif kpi_pat in text_lower or kpi_pat_alt in text_lower:
                    matched = True
                
                if matched:
                    # Find numbers or direction keywords
                    direction = "STABLE"
                    if "decrease" in text_lower or "drop" in text_lower or "declined" in text_lower or "fell" in text_lower:
                        direction = "DECREASE"
                    elif "increase" in text_lower or "rose" in text_lower or "improved" in text_lower:
                        direction = "INCREASE"
                    kpi_directions[kpi] = direction

    # Generate actions per persona
    persona_actions = {}
    
    for persona_name in ["CX_MANAGER", "OPERATIONS_MANAGER"]:
        if persona_name not in persona_views["personas"]:
            continue
            
        persona_payload = persona_views["personas"][persona_name]
        dr = persona_payload.get("decision_readiness", {})
        flags = dr.get("flags", {})
        
        insufficient_history = flags.get("insufficient_history", False)
        high_ambiguity = flags.get("high_ambiguity", False)
        unverified_material_change = flags.get("unverified_material_change", False)
        metric_tension_detected = flags.get("metric_tension_detected", False)
        overall_state = dr.get("overall_state", "READY")
        
        # Define persona scope
        if persona_name == "CX_MANAGER":
            kpi_scope = ["CSAT", "Retention_Rate", "FCR", "Repeat_Contact_Rate"]
        else:
            kpi_scope = ["AHT", "FCR", "Repeat_Contact_Rate", "AI_Resolution_Rate"]
            
        actions_list = []
        
        # ----------------------------------------------------------------------
        # RULE 1: STABILIZE_BASELINE
        # ----------------------------------------------------------------------
        if insufficient_history:
            insufficient_history_metrics = dr.get("details", {}).get("insufficient_history_metrics", [])
            # Fallback scan synthesis statements if details is empty
            if not insufficient_history_metrics:
                for kpi in kpi_scope:
                    for stmt in all_statements:
                        text_lower = stmt["text"].lower()
                        kpi_pat = kpi.replace("_", " ").lower()
                        kpi_pat_alt = kpi.lower()
                        if stmt["classification"] == "LIMITATION" and ("insufficient history" in text_lower or "insufficient historical data" in text_lower):
                            if kpi_pat in text_lower or kpi_pat_alt in text_lower:
                                if kpi not in insufficient_history_metrics:
                                    insufficient_history_metrics.append(kpi)
            
            for metric in insufficient_history_metrics:
                if metric in kpi_scope:
                    # Dynamically extract available/required days from statements
                    avail_days = None
                    req_days = None
                    metric_pat = metric.replace("_", " ").lower()
                    metric_pat_alt = metric.lower()
                    
                    for stmt in all_statements:
                        text_lower = stmt["text"].lower()
                        if "insufficient history" in text_lower or "insufficient historical data" in text_lower:
                            if metric_pat in text_lower or metric_pat_alt in text_lower:
                                # regex match: insufficient history (X days available, Y days required)
                                match = re.search(r"(\d+)\s+days\s+available,\s+(\d+)\s+days\s+required", text_lower)
                                if match:
                                    avail_days = match.group(1)
                                    req_days = match.group(2)
                                    break
                    
                    # Priority is HIGH for a primary blocking KPI
                    is_primary = metric in ["AHT", "FCR", "CSAT", "Repeat_Contact_Rate", "Retention_Rate"]
                    priority = "HIGH" if is_primary else "MEDIUM"
                    
                    metric_name_clean = metric.replace("_", " ")
                    justification = f"{metric_name_clean} has insufficient history relative to configured baseline requirements."
                    if avail_days and req_days:
                        justification = f"{metric_name_clean} has insufficient history ({avail_days} days available, {req_days} days required)."
                        
                    # Structured references
                    struct_refs = [f"{metric}_materiality"]
                    
                    owner_val = "Support Operations Manager" if persona_name == "OPERATIONS_MANAGER" else "CX Manager"
                    actions_list.append({
                        "id": f"ACT_{persona_name}_STABILIZE_{metric}",
                        "action_type": "STABILIZE_BASELINE",
                        "title": f"Establish {metric_name_clean} baseline",
                        "description": "Defer scaling and monitor baseline volume until configured history requirements are satisfied.",
                        "priority": priority,
                        "observed_finding": f"{metric_name_clean} exhibits an insufficient historical baseline.",
                        "driver": f"{metric_name_clean} exhibits an insufficient historical baseline.",
                        "controllable_lever": "Data Ingestion & Baseline Monitoring Window",
                        "action": f"Establish {metric_name_clean} baseline before scaling",
                        "expected_impact": "Prevents false-positive automation scaling on unverified baseline statistics.",
                        "owner": owner_val,
                        "confidence": "LOW_BASELINE_CONFIDENCE",
                        "monitoring_plan": f"Track {metric_name_clean} daily ingestion volume until minimum history requirements are satisfied.",
                        "trigger": f"insufficient_history on {metric}",
                        "reason": "The metric fails the configured history requirements, preventing standard baseline comparison.",
                        "justification": justification,
                        "structured_refs": struct_refs,
                        "evidence_refs": [],
                        "trigger_info": {
                          "source_flag": "insufficient_history",
                          "trigger_kpi": metric,
                          "details": "Fails baseline requirement check."
                        }
                    })

        # ----------------------------------------------------------------------
        # RULE 2: SYSTEM_PATCH (Confounding)
        # ----------------------------------------------------------------------
        # Triggered if high_ambiguity or when patch/confounder is associated in upstream report
        # Collect KPIs in scope that are associated with confounding patch or have high ambiguity
        confounded_kpis = []
        for kpi in kpi_scope:
            kpi_pat = kpi.replace("_", " ").lower()
            kpi_pat_alt = kpi.lower()
            
            # Check for strong/moderate patch association in statements
            is_confounded = False
            kpi_stmt_refs = []
            kpi_evidence_refs = []
            
            for stmt in all_statements:
                text_lower = stmt["text"].lower()
                matched = False
                if kpi == "Repeat_Contact_Rate" and ("repeat contact" in text_lower or "repeat_contact" in text_lower):
                    matched = True
                elif kpi_pat in text_lower or kpi_pat_alt in text_lower:
                    matched = True
                    
                if matched:
                    is_patch_related = "crm patch" in text_lower or "crm cloud" in text_lower or "confound" in text_lower
                    is_ambiguous = "does not determine the primary explanation" in text_lower or "competing" in text_lower or "investigation required" in text_lower
                    
                    if is_patch_related or is_ambiguous:
                        is_confounded = True
                        for ref in stmt["structured_refs"]:
                            if ref not in kpi_stmt_refs:
                                kpi_stmt_refs.append(ref)
                        for ref in stmt["evidence_refs"]:
                            if ref not in kpi_evidence_refs:
                                kpi_evidence_refs.append(ref)
            
            if is_confounded or (high_ambiguity and kpi in material_kpis):
                confounded_kpis.append((kpi, kpi_stmt_refs, kpi_evidence_refs))

        for kpi, s_refs, e_refs in confounded_kpis:
            # Priority: HIGH if the KPI change is material, else MEDIUM
            priority = "HIGH" if kpi in material_kpis else "MEDIUM"
            kpi_name_clean = kpi.replace("_", " ")
            owner_val = "Support Operations Manager" if persona_name == "OPERATIONS_MANAGER" else "CX Manager"
            
            actions_list.append({
                "id": f"ACT_{persona_name}_PATCH_{kpi}",
                "action_type": "SYSTEM_PATCH",
                "title": f"Isolate CRM patch association for {kpi_name_clean}",
                "description": "Isolate affected segment logs and verify patch stability to identify potential system-level overlap.",
                "priority": priority,
                "observed_finding": f"{kpi_name_clean} shifts coincide with both the automated assistant rollout and the CRM Cloud patch.",
                "driver": f"{kpi_name_clean} shifts coincide with both the automated assistant rollout and the CRM Cloud patch.",
                "controllable_lever": "Software Release Isolation & Segment Patch Deployment",
                "action": f"Isolate CRM patch association for {kpi_name_clean}",
                "expected_impact": "Disentangles concurrent system update noise from core workflow trends.",
                "owner": owner_val,
                "confidence": "MODERATE_ASSOCIATION",
                "monitoring_plan": "Monitor pre/post patch error telemetry and ticket volume across CRM Cloud vs. control product segments.",
                "trigger": f"high_ambiguity on {kpi}",
                "reason": "Multiple concurrent events (AI assistant rollout and CRM Cloud patch) exhibit overlapping associations, creating significant ambiguity.",
                "justification": f"Both the rollout and the CRM Cloud patch show moderate-to-strong operational associations in the same period.",
                "structured_refs": sorted(s_refs) if s_refs else [f"{kpi}_crm_hypothesis"],
                "evidence_refs": sorted(e_refs),
                "trigger_info": {
                  "source_flag": "high_ambiguity",
                  "trigger_kpi": kpi,
                  "details": "Coinciding CRM patch confounder detected."
                }
            })

        # ----------------------------------------------------------------------
        # RULE 3: RESOLUTION_GUARDRAIL (Tensions)
        # ----------------------------------------------------------------------
        if metric_tension_detected:
            # Find tension statements in Contradictory / Tension Evidence section
            for stmt in all_statements:
                if stmt["section_title"] == "Contradictory / Tension Evidence":
                    if "no matching qualitative" in stmt["text"].lower() or stmt["classification"] == "LIMITATION":
                        continue
                        
                    # Check if tension statement belongs to the persona's KPI scope
                    # Either the text mentions the KPI, or the structured_refs contains the KPI name
                    is_relevant = False
                    for kpi in kpi_scope:
                        kpi_pat = kpi.replace("_", " ").lower()
                        kpi_pat_alt = kpi.lower()
                        
                        text_lower = stmt["text"].lower()
                        ref_match = any(kpi_pat in r.lower() or kpi_pat_alt in r.lower() for r in stmt["structured_refs"])
                        text_match = (kpi == "Repeat_Contact_Rate" and ("repeat contact" in text_lower or "repeat_contact" in text_lower)) or (kpi_pat in text_lower or kpi_pat_alt in text_lower)
                        
                        if ref_match or text_match:
                            is_relevant = True
                            break
                            
                    if is_relevant:
                        # Priority: HIGH if any material KPI is present in the statement references/text, else MEDIUM
                        has_material = any(mk in stmt["text"] or any(mk in r for r in stmt["structured_refs"]) for mk in material_kpis)
                        priority = "HIGH" if has_material else "MEDIUM"
                        owner_val = "Support Operations Manager" if persona_name == "OPERATIONS_MANAGER" else "CX Manager"
                        
                        stmt_ref_clean = stmt["structured_refs"][0] if stmt["structured_refs"] else "general"
                        
                        actions_list.append({
                            "id": f"ACT_{persona_name}_TENSION_{stmt_ref_clean.upper()}",
                            "action_type": "RESOLUTION_GUARDRAIL",
                            "title": "Implement resolution quality guardrails",
                            "description": "Add auto-closure checks and revise routing rules to prevent premature ticket closure.",
                            "priority": priority,
                            "observed_finding": stmt["text"],
                            "driver": stmt["text"],
                            "controllable_lever": "Bot Routing Rules & Ticket Auto-Closure Thresholds",
                            "action": "Implement resolution quality guardrails",
                            "expected_impact": "Reduces premature contact closures and curtails repeat contact loops.",
                            "owner": owner_val,
                            "confidence": "HIGH_TENSION_RISK",
                            "monitoring_plan": "Track 48-hour Repeat Contact Rate and customer survey sentiment post-interaction.",
                            "trigger": "metric_tension_detected",
                            "reason": "Efficiency gains in operational speed metrics coincide with unresolved customer feedback or repeat contacts.",
                            "justification": "Qualitative logs contain complaints regarding premature ticket closure or unresolved issues despite quantitative speedups.",
                            "structured_refs": sorted(stmt["structured_refs"]),
                            "evidence_refs": sorted(stmt["evidence_refs"]),
                            "trigger_info": {
                              "source_flag": "metric_tension_detected",
                              "details": stmt["text"]
                            }
                        })

        # ----------------------------------------------------------------------
        # RULE 4: OPERATIONAL_OPTIMIZATION
        # ----------------------------------------------------------------------
        # ONLY under clean READY / READY_WITH_RESERVATIONS and no risk flags
        is_ready = overall_state in ["READY", "READY_WITH_RESERVATIONS"]
        no_risks = not insufficient_history and not high_ambiguity and not unverified_material_change and not metric_tension_detected
        
        if is_ready and no_risks:
            for kpi in kpi_scope:
                if kpi in material_kpis:
                    # Check if direction is improved
                    # csat/fcr/retention/ai_resolution increase is better; aht/repeat_contact decrease is better
                    direction = kpi_directions.get(kpi, "STABLE")
                    improved = False
                    if kpi in ["CSAT", "FCR", "Retention_Rate", "AI_Resolution_Rate"] and direction == "INCREASE":
                        improved = True
                    elif kpi in ["AHT", "Repeat_Contact_Rate"] and direction == "DECREASE":
                        improved = True
                        
                    if improved:
                        # Collect qualitative evidence refs for this KPI
                        kpi_ev_refs = []
                        kpi_struct_refs = [f"{kpi}_materiality"]
                        
                        kpi_pat = kpi.replace("_", " ").lower()
                        kpi_pat_alt = kpi.lower()
                        
                        for stmt in all_statements:
                            text_lower = stmt["text"].lower()
                            matched = False
                            if kpi == "Repeat_Contact_Rate" and ("repeat contact" in text_lower or "repeat_contact" in text_lower):
                                matched = True
                            elif kpi_pat in text_lower or kpi_pat_alt in text_lower:
                                matched = True
                            
                            if matched:
                                for ref in stmt["evidence_refs"]:
                                    if ref not in kpi_ev_refs:
                                        kpi_ev_refs.append(ref)
                                for ref in stmt["structured_refs"]:
                                    if ref not in kpi_struct_refs:
                                        kpi_struct_refs.append(ref)
                                        
                        kpi_name_clean = kpi.replace("_", " ")
                        owner_val = "Support Operations Manager" if persona_name == "OPERATIONS_MANAGER" else "CX Manager"
                        
                        actions_list.append({
                            "id": f"ACT_{persona_name}_OPTIMIZE_{kpi}",
                            "action_type": "OPERATIONAL_OPTIMIZATION",
                            "title": f"Optimize and expand {kpi_name_clean} processes",
                            "description": "Monitor expansion of the automated channel under the current segment mix, verifying CSAT stability.",
                            "priority": "LOW",
                            "observed_finding": f"{kpi_name_clean} has registered a material positive shift.",
                            "driver": f"{kpi_name_clean} has registered a material positive shift.",
                            "controllable_lever": "Workflow Automation Rollout & Channel Allocation",
                            "action": f"Optimize and expand {kpi_name_clean} processes",
                            "expected_impact": "Safely scales automated support capacity while preserving customer experience quality.",
                            "owner": owner_val,
                            "confidence": "VERIFIED_READY",
                            "monitoring_plan": "Continuously track CSAT and FCR alongside AHT to guard against resolution quality degradation.",
                            "trigger": "ready_for_optimization",
                            "reason": f"The material improvement in {kpi_name_clean} is verified by qualitative evidence with no unresolved tensions.",
                            "justification": f"The quantitative shift is verified by qualitative feedback and meets all decision readiness criteria.",
                            "structured_refs": sorted(kpi_struct_refs),
                            "evidence_refs": sorted(kpi_ev_refs),
                            "trigger_info": {
                              "source_flag": "ready_for_optimization",
                              "trigger_kpi": kpi,
                              "details": "Material improvement verified with no active risks."
                            }
                        })

        # ----------------------------------------------------------------------
        # SORTING ACTIONS DETERMINISTICALLY
        # ----------------------------------------------------------------------
        # Sort key: priority (HIGH=0, MEDIUM=1, LOW=2), then action_type alphabetically, then id alphabetically
        def get_sort_key(action):
            p_map = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
            priority_val = p_map.get(action.get("priority", "LOW"), 2)
            type_val = action.get("action_type", "")
            id_val = action.get("id", "")
            return (priority_val, type_val, id_val)
            
        sorted_actions = sorted(actions_list, key=get_sort_key)
        
        # De-duplicate actions by ID (keeping the first one, though our generation makes them unique)
        seen_ids = set()
        final_actions = []
        for act in sorted_actions:
            if act["id"] not in seen_ids:
                seen_ids.add(act["id"])
                final_actions.append(act)
                
        persona_actions[persona_name] = final_actions

    return {
        "status": "SUCCESS",
        "persona_actions": persona_actions
    }
