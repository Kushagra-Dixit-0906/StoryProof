from src.engine.readiness import evaluate_decision_readiness
from src.engine.actions import generate_action_recommendations

def generate_persona_views(synthesis_result):
    """
    Transforms the verified deterministic synthesis result into persona-specific narrative views.
    Consumes outputs from generate_synthesis_report() without recalculating metrics upstream.
    Enforces Causality Policy and preserves provenance.
    """
    if synthesis_result is None:
        return {
            "status": "NOT_AVAILABLE",
            "reason": "Synthesis result is not available.",
            "personas": {}
        }

    if not isinstance(synthesis_result, dict) or synthesis_result.get("status") != "SUCCESS" or "report" not in synthesis_result:
        return {
            "status": "NOT_AVAILABLE",
            "reason": "Synthesis result is not available.",
            "personas": {}
        }

    report = synthesis_result.get("report", [])
    
    # Extract all statements from the report sections
    all_statements = []
    for section in report:
        title = section.get("title", "")
        statements = section.get("statements", [])
        for stmt in statements:
            # We store a reference to the statement and keep track of which section it came from
            # to help with risk vs key finding classification
            all_statements.append({
                "text": stmt.get("text", ""),
                "classification": stmt.get("classification", "ASSOCIATION"),
                "structured_refs": stmt.get("structured_refs", []),
                "evidence_refs": stmt.get("evidence_refs", []),
                "source_section": title
            })

    # 1. Define CX Manager views
    cx_priority = [
        "CSAT",
        "FCR",
        "Repeat Contact Rate",
        "Retention",
        "Customer complaints / qualitative evidence",
        "AI Resolution Rate limitations",
        "Customer-impacting tensions"
    ]

    # 2. Define Operations Manager views
    ops_priority = [
        "AHT",
        "FCR",
        "Repeat Contact Rate",
        "AI-assisted operational performance",
        "Driver contribution",
        "CRM Cloud patch/confounder",
        "Efficiency vs resolution-quality tension"
    ]

    # Classification logic helper
    def categorize_statement(stmt):
        cls = stmt["classification"]
        sec = stmt["source_section"]
        txt_lower = stmt["text"].lower()
        
        is_risk_sec = sec in ["Contradictory / Tension Evidence", "Confounding Factors", "Data Limitations", "Causality Disclaimer"]
        is_risk_cls = cls in ["LIMITATION", "HYPOTHESIS", "CONTEXT"]
        is_risk_kw = any(kw in txt_lower for kw in ["unresolved", "tension", "confound", "insufficient", "complaint", "decline", "limit"])
        
        if is_risk_sec or is_risk_cls or is_risk_kw:
            return "risk"
        return "key_finding"

    # Matcher for CX Manager
    def is_cx_relevant(stmt):
        txt_lower = stmt["text"].lower()
        refs_lower = [ref.lower() for ref in stmt["structured_refs"]]
        
        cx_kpis = ["csat", "fcr", "repeat_contact", "retention", "ai_resolution"]
        if any(any(kpi in ref for kpi in cx_kpis) for ref in refs_lower):
            return True
            
        cx_keywords = ["csat", "fcr", "repeat contact", "repeat_contact", "retention", "customer", "satisfaction", "complaint", "feedback", "unresolved", "tension"]
        if any(kw in txt_lower for kw in cx_keywords):
            return True
            
        if "does not establish causality" in txt_lower:
            return True
            
        return False

    # Matcher for Operations Manager
    def is_ops_relevant(stmt):
        txt_lower = stmt["text"].lower()
        refs_lower = [ref.lower() for ref in stmt["structured_refs"]]
        
        ops_kpis = ["aht", "fcr", "repeat_contact", "ai_resolution", "crm", "mix"]
        if any(any(kpi in ref for kpi in ops_kpis) for ref in refs_lower):
            return True
            
        ops_keywords = ["aht", "handling time", "fcr", "repeat contact", "repeat_contact", "ai", "chatbot", "assistant", "crm", "patch", "confound", "driver", "mix shift", "efficiency", "throughput", "unresolved"]
        if any(kw in txt_lower for kw in ops_keywords):
            return True
            
        if "does not establish causality" in txt_lower:
            return True
            
        return False

    # Priority sorting key for CX Manager
    def cx_sort_key(stmt):
        txt_lower = stmt["text"].lower()
        refs_lower = [ref.lower() for ref in stmt["structured_refs"]]
        
        # Priority 1: CSAT
        if "csat" in txt_lower or any("csat" in ref for ref in refs_lower):
            return (1, stmt["text"])
        # Priority 2: FCR
        if "fcr" in txt_lower or any("fcr" in ref for ref in refs_lower):
            return (2, stmt["text"])
        # Priority 3: Repeat Contact Rate
        if "repeat_contact" in txt_lower or "repeat contact" in txt_lower or any("repeat_contact" in ref for ref in refs_lower):
            return (3, stmt["text"])
        # Priority 4: Retention
        if "retention" in txt_lower or any("retention" in ref for ref in refs_lower):
            return (4, stmt["text"])
        # Priority 5: Customer complaints / qualitative evidence
        if "customer" in txt_lower or "complaint" in txt_lower or "feedback" in txt_lower or "review" in txt_lower or "transcript" in txt_lower:
            return (5, stmt["text"])
        # Priority 6: AI Resolution Rate limitations
        if "ai_resolution" in txt_lower or "ai resolution" in txt_lower or any("ai_resolution" in ref for ref in refs_lower):
            return (6, stmt["text"])
        # Priority 7: Customer-impacting tensions / limitations / causality disclaimer
        if "tension" in txt_lower or "unresolved" in txt_lower or "causality" in txt_lower:
            return (7, stmt["text"])
        return (8, stmt["text"])

    # Priority sorting key for Operations Manager
    def ops_sort_key(stmt):
        txt_lower = stmt["text"].lower()
        refs_lower = [ref.lower() for ref in stmt["structured_refs"]]
        
        # Priority 1: AHT
        if "aht" in txt_lower or "handling time" in txt_lower or any("aht" in ref for ref in refs_lower):
            return (1, stmt["text"])
        # Priority 2: FCR
        if "fcr" in txt_lower or any("fcr" in ref for ref in refs_lower):
            return (2, stmt["text"])
        # Priority 3: Repeat Contact Rate
        if "repeat_contact" in txt_lower or "repeat contact" in txt_lower or any("repeat_contact" in ref for ref in refs_lower):
            return (3, stmt["text"])
        # Priority 4: AI rollout / assistant
        if "ai" in txt_lower or "chatbot" in txt_lower or "assistant" in txt_lower:
            return (4, stmt["text"])
        # Priority 5: Driver contribution
        if "driver" in txt_lower or "contributor" in txt_lower or "contribution" in txt_lower:
            return (5, stmt["text"])
        # Priority 6: CRM Cloud patch
        if "crm" in txt_lower or "patch" in txt_lower or any("crm" in ref for ref in refs_lower):
            return (6, stmt["text"])
        # Priority 7: tensions / unresolved / contradictory / causality disclaimer
        if "tension" in txt_lower or "unresolved" in txt_lower or "causality" in txt_lower:
            return (7, stmt["text"])
        return (8, stmt["text"])

    # Filter and categorize findings for CX Manager
    cx_key_findings_raw = []
    cx_risks_raw = []
    cx_seen_texts = set()
    
    for stmt in all_statements:
        if is_cx_relevant(stmt):
            # De-duplicate statements based on text
            if stmt["text"] not in cx_seen_texts:
                cx_seen_texts.add(stmt["text"])
                clean_stmt = {
                    "text": stmt["text"],
                    "classification": stmt["classification"],
                    "structured_refs": stmt["structured_refs"],
                    "evidence_refs": stmt["evidence_refs"]
                }
                category = categorize_statement(stmt)
                if category == "risk":
                    cx_risks_raw.append(clean_stmt)
                else:
                    cx_key_findings_raw.append(clean_stmt)

    # Sort based on CX priorities
    cx_key_findings = sorted(cx_key_findings_raw, key=cx_sort_key)
    cx_risks = sorted(cx_risks_raw, key=cx_sort_key)

    # Aggregate references for CX Manager
    cx_evidence_set = set()
    cx_structured_set = set()
    for f in cx_key_findings + cx_risks:
        for ref in f["evidence_refs"]:
            cx_evidence_set.add(ref)
        for ref in f["structured_refs"]:
            cx_structured_set.add(ref)
            
    cx_evidence_refs = sorted(list(cx_evidence_set))
    cx_structured_refs = sorted(list(cx_structured_set))

    # Filter and categorize findings for Operations Manager
    ops_key_findings_raw = []
    ops_risks_raw = []
    ops_seen_texts = set()
    
    for stmt in all_statements:
        if is_ops_relevant(stmt):
            # De-duplicate statements based on text
            if stmt["text"] not in ops_seen_texts:
                ops_seen_texts.add(stmt["text"])
                clean_stmt = {
                    "text": stmt["text"],
                    "classification": stmt["classification"],
                    "structured_refs": stmt["structured_refs"],
                    "evidence_refs": stmt["evidence_refs"]
                }
                category = categorize_statement(stmt)
                if category == "risk":
                    ops_risks_raw.append(clean_stmt)
                else:
                    ops_key_findings_raw.append(clean_stmt)

    # Sort based on Operations priorities
    ops_key_findings = sorted(ops_key_findings_raw, key=ops_sort_key)
    ops_risks = sorted(ops_risks_raw, key=ops_sort_key)

    # Aggregate references for Operations Manager
    ops_evidence_set = set()
    ops_structured_set = set()
    for f in ops_key_findings + ops_risks:
        for ref in f["evidence_refs"]:
            ops_evidence_set.add(ref)
        for ref in f["structured_refs"]:
            ops_structured_set.add(ref)
            
    ops_evidence_refs = sorted(list(ops_evidence_set))
    ops_structured_refs = sorted(list(ops_structured_set))

    # Priority matchers definitions for dynamic summaries
    cx_priority_matchers = [
        ("CSAT", lambda s: "csat" in s["text"].lower() or any("csat" in ref.lower() for ref in s["structured_refs"])),
        ("FCR", lambda s: "fcr" in s["text"].lower() or any("fcr" in ref.lower() for ref in s["structured_refs"])),
        ("Repeat Contact Rate", lambda s: "repeat_contact" in s["text"].lower() or "repeat contact" in s["text"].lower() or any("repeat_contact" in ref.lower() for ref in s["structured_refs"])),
        ("Retention", lambda s: "retention" in s["text"].lower() or any("retention" in ref.lower() for ref in s["structured_refs"])),
        ("Qualitative Evidence", lambda s: "customer" in s["text"].lower() or "feedback" in s["text"].lower() or "complaint" in s["text"].lower() or "review" in s["text"].lower() or "transcript" in s["text"].lower()),
        ("AI Resolution Rate", lambda s: "ai_resolution" in s["text"].lower() or "ai resolution" in s["text"].lower() or any("ai_resolution" in ref.lower() for ref in s["structured_refs"])),
        ("Tensions", lambda s: "tension" in s["text"].lower() or "unresolved" in s["text"].lower())
    ]

    ops_priority_matchers = [
        ("AHT", lambda s: "aht" in s["text"].lower() or "handling time" in s["text"].lower() or any("aht" in ref.lower() for ref in s["structured_refs"])),
        ("FCR", lambda s: "fcr" in s["text"].lower() or any("fcr" in ref.lower() for ref in s["structured_refs"])),
        ("Repeat Contact Rate", lambda s: "repeat_contact" in s["text"].lower() or "repeat contact" in s["text"].lower() or any("repeat_contact" in ref.lower() for ref in s["structured_refs"])),
        ("AI Rollout", lambda s: "ai" in s["text"].lower() or "chatbot" in s["text"].lower() or "assistant" in s["text"].lower()),
        ("Driver Contribution", lambda s: "driver" in s["text"].lower() or "contributor" in s["text"].lower() or "contribution" in s["text"].lower()),
        ("CRM Cloud Patch", lambda s: "crm" in s["text"].lower() or "patch" in s["text"].lower() or any("crm" in ref.lower() for ref in s["structured_refs"])),
        ("Tensions", lambda s: "tension" in s["text"].lower() or "unresolved" in s["text"].lower())
    ]

    # Helper function to build dynamic summary
    def build_summary(matchers, key_findings, risks):
        summary_sentences = []
        all_stmts = key_findings + risks
        for matcher_name, matcher_fn in matchers:
            for stmt in all_stmts:
                # Skip the disclaimer when gathering summary sentences
                if "does not establish causality" in stmt["text"].lower():
                    continue
                if matcher_fn(stmt):
                    summary_sentences.append(stmt["text"])
                    break
        if not summary_sentences:
            summary_sentences.append("No additional finding is available for this priority.")
        
        disclaimer = "The available evidence does not establish causality; observed changes represent associations and candidate explanations only."
        if disclaimer not in " ".join(summary_sentences):
            summary_sentences.append(disclaimer)
        return " ".join(summary_sentences)

    # Helper function to build dynamic decision context
    def build_decision_context(risks):
        context_sentences = []
        for r in risks:
            if "does not establish causality" in r["text"].lower():
                continue
            if len(context_sentences) < 2:
                context_sentences.append(r["text"])
        if not context_sentences:
            return "Focus on operational review of available findings."
        return "Focus on addressing observed areas of concern: " + " ".join(context_sentences)

    cx_summary = build_summary(cx_priority_matchers, cx_key_findings, cx_risks)
    cx_decision_context = build_decision_context(cx_risks)

    ops_summary = build_summary(ops_priority_matchers, ops_key_findings, ops_risks)
    ops_decision_context = build_decision_context(ops_risks)

    # Compute decision readiness additively
    cx_readiness = evaluate_decision_readiness(synthesis_result, "CX_MANAGER")
    cx_readiness_payload = cx_readiness.get("decision_readiness", {}) if cx_readiness.get("status") == "SUCCESS" else {}

    ops_readiness = evaluate_decision_readiness(synthesis_result, "OPERATIONS_MANAGER")
    ops_readiness_payload = ops_readiness.get("decision_readiness", {}) if ops_readiness.get("status") == "SUCCESS" else {}

    # Initial views response without actions to pass to action recommendation generator
    views_res = {
        "status": "SUCCESS",
        "personas": {
            "CX_MANAGER": {
                "persona": "CX_MANAGER",
                "priority": cx_priority,
                "summary": cx_summary,
                "key_findings": cx_key_findings,
                "risks": cx_risks,
                "evidence_refs": cx_evidence_refs,
                "structured_refs": cx_structured_refs,
                "decision_context": cx_decision_context,
                "decision_readiness": cx_readiness_payload
            },
            "OPERATIONS_MANAGER": {
                "persona": "OPERATIONS_MANAGER",
                "priority": ops_priority,
                "summary": ops_summary,
                "key_findings": ops_key_findings,
                "risks": ops_risks,
                "evidence_refs": ops_evidence_refs,
                "structured_refs": ops_structured_refs,
                "decision_context": ops_decision_context,
                "decision_readiness": ops_readiness_payload
            }
        }
    }

    # Generate action recommendations dynamically
    actions_res = generate_action_recommendations(synthesis_result, views_res)
    cx_actions = []
    ops_actions = []
    if actions_res.get("status") == "SUCCESS":
        persona_actions = actions_res.get("persona_actions", {})
        cx_actions = persona_actions.get("CX_MANAGER", [])
        ops_actions = persona_actions.get("OPERATIONS_MANAGER", [])

    # Construct the final response with actions integrated additively
    return {
        "status": "SUCCESS",
        "personas": {
            "CX_MANAGER": {
                "persona": "CX_MANAGER",
                "priority": cx_priority,
                "summary": cx_summary,
                "key_findings": cx_key_findings,
                "risks": cx_risks,
                "evidence_refs": cx_evidence_refs,
                "structured_refs": cx_structured_refs,
                "decision_context": cx_decision_context,
                "decision_readiness": cx_readiness_payload,
                "recommended_actions": cx_actions
            },
            "OPERATIONS_MANAGER": {
                "persona": "OPERATIONS_MANAGER",
                "priority": ops_priority,
                "summary": ops_summary,
                "key_findings": ops_key_findings,
                "risks": ops_risks,
                "evidence_refs": ops_evidence_refs,
                "structured_refs": ops_structured_refs,
                "decision_context": ops_decision_context,
                "decision_readiness": ops_readiness_payload,
                "recommended_actions": ops_actions
            }
        }
    }
