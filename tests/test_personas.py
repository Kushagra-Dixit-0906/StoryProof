import pytest
from src.engine.synthesis import generate_synthesis_report
from src.engine.personas import generate_persona_views

# Mock synthesis report for unit testing
MOCK_SYNTHESIS_RESULT = {
    "status": "SUCCESS",
    "report": [
        {
            "title": "KPI Movement",
            "statements": [
                {
                    "text": "AHT changed from 10.16 to 5.77 minutes.",
                    "classification": "FACT",
                    "structured_refs": ["AHT_materiality"],
                    "evidence_refs": []
                },
                {
                    "text": "CSAT score changed from 78.02 to 68.88 points.",
                    "classification": "FACT",
                    "structured_refs": ["CSAT_materiality"],
                    "evidence_refs": []
                },
                {
                    "text": "Repeat_Contact_Rate changed from 0.0820 to 0.1650.",
                    "classification": "FACT",
                    "structured_refs": ["Repeat_Contact_Rate_materiality"],
                    "evidence_refs": []
                },
                {
                    "text": "FCR changed from 0.7430 to 0.7210.",
                    "classification": "FACT",
                    "structured_refs": ["FCR_materiality"],
                    "evidence_refs": []
                }
            ]
        },
        {
            "title": "Competing Hypotheses",
            "statements": [
                {
                    "text": "AI rollout hypothesis exhibits STRONG_ASSOCIATION with AHT shifts.",
                    "classification": "ASSOCIATION",
                    "structured_refs": ["AHT_ai_hypothesis"],
                    "evidence_refs": ["rollout_report_4"]
                }
            ]
        },
        {
            "title": "Qualitative Evidence",
            "statements": [
                {
                    "text": "Customer reviews contain feedback expressing satisfaction levels.",
                    "classification": "HYPOTHESIS",
                    "structured_refs": [],
                    "evidence_refs": ["customer_feedback_6"]
                }
            ]
        },
        {
            "title": "Confounding Factors",
            "statements": [
                {
                    "text": "CRM Cloud software patch is identified as a concurrent confounding event.",
                    "classification": "CONTEXT",
                    "structured_refs": ["AHT_crm_hypothesis"],
                    "evidence_refs": ["support_transcripts_5"]
                }
            ]
        },
        {
            "title": "Causality Disclaimer",
            "statements": [
                {
                    "text": "The available evidence does not establish causality; observed changes represent associations and candidate explanations only.",
                    "classification": "LIMITATION",
                    "structured_refs": ["AHT_materiality", "CSAT_materiality"],
                    "evidence_refs": []
                }
            ]
        }
    ]
}

# 1. Basic persona generation succeeds
def test_basic_persona_generation_succeeds():
    res = generate_persona_views(MOCK_SYNTHESIS_RESULT)
    assert res["status"] == "SUCCESS"
    assert "personas" in res

# 2. Both CX_MANAGER and OPERATIONS_MANAGER are returned
def test_both_personas_returned():
    res = generate_persona_views(MOCK_SYNTHESIS_RESULT)
    personas = res["personas"]
    assert "CX_MANAGER" in personas
    assert "OPERATIONS_MANAGER" in personas

# 3. CX Manager prioritizes customer-impact findings (CSAT > FCR > Repeat Contact)
def test_cx_prioritizes_customer_impact():
    res = generate_persona_views(MOCK_SYNTHESIS_RESULT)
    cx = res["personas"]["CX_MANAGER"]
    findings = cx["key_findings"]
    
    # We find indices of CSAT, FCR, and Repeat Contact findings
    idx_csat = -1
    idx_fcr = -1
    idx_repeat = -1
    for idx, f in enumerate(findings):
        if "CSAT" in f["text"]:
            idx_csat = idx
        elif "FCR" in f["text"]:
            idx_fcr = idx
        elif "Repeat_Contact" in f["text"]:
            idx_repeat = idx
            
    # Priority order CSAT (1) < FCR (2) < Repeat (3)
    assert idx_csat != -1
    assert idx_fcr != -1
    assert idx_repeat != -1
    assert idx_csat < idx_fcr
    assert idx_fcr < idx_repeat

# 4. Operations Manager prioritizes efficiency/operational findings (AHT > FCR > Repeat Contact)
def test_ops_prioritizes_operational_findings():
    res = generate_persona_views(MOCK_SYNTHESIS_RESULT)
    ops = res["personas"]["OPERATIONS_MANAGER"]
    findings = ops["key_findings"]
    
    idx_aht = -1
    idx_fcr = -1
    idx_repeat = -1
    for idx, f in enumerate(findings):
        if "AHT" in f["text"]:
            idx_aht = idx
        elif "FCR" in f["text"]:
            idx_fcr = idx
        elif "Repeat_Contact" in f["text"]:
            idx_repeat = idx
            
    assert idx_aht != -1
    assert idx_fcr != -1
    assert idx_repeat != -1
    assert idx_aht < idx_fcr
    assert idx_fcr < idx_repeat

# 5. AHT finding appears in Operations view
def test_aht_in_ops_view():
    res = generate_persona_views(MOCK_SYNTHESIS_RESULT)
    ops = res["personas"]["OPERATIONS_MANAGER"]
    assert any("AHT" in f["text"] for f in ops["key_findings"])

# 6. CSAT/FCR findings appear in CX view
def test_csat_fcr_in_cx_view():
    res = generate_persona_views(MOCK_SYNTHESIS_RESULT)
    cx = res["personas"]["CX_MANAGER"]
    assert any("CSAT" in f["text"] for f in cx["key_findings"])
    assert any("FCR" in f["text"] for f in cx["key_findings"])

# 7. AI rollout findings appear in Operations view
def test_ai_rollout_in_ops_view():
    res = generate_persona_views(MOCK_SYNTHESIS_RESULT)
    ops = res["personas"]["OPERATIONS_MANAGER"]
    assert any("AI rollout" in f["text"] for f in ops["key_findings"])

# 8. CRM patch/confounder appears in Operations view
def test_crm_patch_in_ops_view():
    res = generate_persona_views(MOCK_SYNTHESIS_RESULT)
    ops = res["personas"]["OPERATIONS_MANAGER"]
    assert any("CRM" in r["text"] for r in ops["risks"])

# 9. Repeat Contact Rate appears in CX view
def test_repeat_contact_in_cx_view():
    res = generate_persona_views(MOCK_SYNTHESIS_RESULT)
    cx = res["personas"]["CX_MANAGER"]
    assert any("Repeat_Contact" in f["text"] for f in cx["key_findings"])

# 10. Qualitative customer evidence appears in CX view
def test_qualitative_evidence_in_cx_view():
    res = generate_persona_views(MOCK_SYNTHESIS_RESULT)
    cx = res["personas"]["CX_MANAGER"]
    assert any("Customer reviews" in r["text"] for r in cx["risks"])

# 11. References are preserved
def test_references_preserved():
    res = generate_persona_views(MOCK_SYNTHESIS_RESULT)
    ops = res["personas"]["OPERATIONS_MANAGER"]
    
    # Find AI rollout statement
    ai_stmt = next(f for f in ops["key_findings"] if "AI rollout" in f["text"])
    assert ai_stmt["evidence_refs"] == ["rollout_report_4"]
    assert ai_stmt["structured_refs"] == ["AHT_ai_hypothesis"]

# 12. No fabricated evidence IDs
def test_no_fabricated_evidence_ids():
    res = generate_persona_views(MOCK_SYNTHESIS_RESULT)
    
    # Collect all mock IDs in the source synthesis result
    mock_ids = set()
    for sec in MOCK_SYNTHESIS_RESULT["report"]:
        for s in sec["statements"]:
            mock_ids.update(s["evidence_refs"])
            
    for persona_name, p in res["personas"].items():
        for ref in p["evidence_refs"]:
            assert ref in mock_ids
            
        for f in p["key_findings"] + p["risks"]:
            for ref in f["evidence_refs"]:
                assert ref in mock_ids

# 13. Classifications are preserved
def test_classifications_preserved():
    res = generate_persona_views(MOCK_SYNTHESIS_RESULT)
    ops = res["personas"]["OPERATIONS_MANAGER"]
    
    # AHT finding is FACT
    aht_stmt = next(f for f in ops["key_findings"] if "AHT" in f["text"])
    assert aht_stmt["classification"] == "FACT"
    
    # CRM patch finding is CONTEXT
    crm_stmt = next(r for r in ops["risks"] if "CRM" in r["text"])
    assert crm_stmt["classification"] == "CONTEXT"

# 14. Mandatory causality disclaimer exists for CX Manager
def test_disclaimer_exists_in_cx():
    res = generate_persona_views(MOCK_SYNTHESIS_RESULT)
    cx = res["personas"]["CX_MANAGER"]
    disclaimer = "The available evidence does not establish causality; observed changes represent associations and candidate explanations only."
    assert disclaimer in cx["summary"]
    assert any(disclaimer in r["text"] for r in cx["risks"])

# 15. Mandatory causality disclaimer exists for Operations Manager
def test_disclaimer_exists_in_ops():
    res = generate_persona_views(MOCK_SYNTHESIS_RESULT)
    ops = res["personas"]["OPERATIONS_MANAGER"]
    disclaimer = "The available evidence does not establish causality; observed changes represent associations and candidate explanations only."
    assert disclaimer in ops["summary"]
    assert any(disclaimer in r["text"] for r in ops["risks"])

# 16. No prohibited causal language appears in generated persona text
def test_no_prohibited_causal_language():
    res = generate_persona_views(MOCK_SYNTHESIS_RESULT)
    causal_words = ["caused", "causes", "responsible for", "resulted in", "led to", "due to", "drove", "driven by", "because of"]
    
    for persona_name, p in res["personas"].items():
        summary_lower = p["summary"].lower()
        context_lower = p["decision_context"].lower()
        for word in causal_words:
            assert word not in summary_lower, f"Forbidden causal word '{word}' found in summary of {persona_name}"
            assert word not in context_lower, f"Forbidden causal word '{word}' found in decision_context of {persona_name}"

# 17. Missing synthesis result returns NOT_AVAILABLE safely
def test_missing_synthesis_result_returns_not_available():
    res = generate_persona_views(None)
    assert res["status"] == "NOT_AVAILABLE"
    assert res["personas"] == {}

# 18. Missing report safely returns NOT_AVAILABLE
def test_missing_report_returns_not_available():
    res = generate_persona_views({"status": "SUCCESS"})
    assert res["status"] == "NOT_AVAILABLE"
    assert res["personas"] == {}
    
    res2 = generate_persona_views({"status": "ERROR", "report": []})
    assert res2["status"] == "NOT_AVAILABLE"
    assert res2["personas"] == {}

# 19. Deterministic ordering is preserved (CX_MANAGER first, then OPERATIONS_MANAGER)
def test_deterministic_persona_ordering():
    res = generate_persona_views(MOCK_SYNTHESIS_RESULT)
    keys = list(res["personas"].keys())
    assert keys == ["CX_MANAGER", "OPERATIONS_MANAGER"]

# 20. Repeated execution produces identical output
def test_repeated_execution_consistency():
    res1 = generate_persona_views(MOCK_SYNTHESIS_RESULT)
    res2 = generate_persona_views(MOCK_SYNTHESIS_RESULT)
    assert res1 == res2

# 21. Empty optional sections are handled safely
def test_empty_optional_sections_handling():
    empty_result = {
        "status": "SUCCESS",
        "report": []
    }
    res = generate_persona_views(empty_result)
    assert res["status"] == "SUCCESS"
    assert res["personas"]["CX_MANAGER"]["key_findings"] == []
    assert res["personas"]["OPERATIONS_MANAGER"]["key_findings"] == []

# 22. Regression compatibility with existing synthesis output
def test_regression_compatibility():
    real_synthesis = generate_synthesis_report("data")
    assert real_synthesis["status"] == "SUCCESS"
    
    res = generate_persona_views(real_synthesis)
    assert res["status"] == "SUCCESS"
    assert "CX_MANAGER" in res["personas"]
    assert "OPERATIONS_MANAGER" in res["personas"]
    
    cx = res["personas"]["CX_MANAGER"]
    ops = res["personas"]["OPERATIONS_MANAGER"]
    
    # Verify standard metrics are present in the real report output
    assert any("CSAT" in f["text"] for f in cx["key_findings"])
    assert any("AHT" in f["text"] for f in ops["key_findings"])

# 23. Test that CX persona reflects dynamic synthesis input changes
def test_cx_summary_reflects_synthesis_change():
    import copy
    custom_result = copy.deepcopy(MOCK_SYNTHESIS_RESULT)
    # Replace the CSAT statement text
    for sec in custom_result["report"]:
        for stmt in sec["statements"]:
            if "CSAT score changed" in stmt["text"]:
                stmt["text"] = "CSAT improved materially by 10 points."
                
    res = generate_persona_views(custom_result)
    cx = res["personas"]["CX_MANAGER"]
    assert "CSAT improved materially by 10 points." in cx["summary"]
    assert "CSAT declined materially" not in cx["summary"]

# 24. Test that Operations summary reflects dynamic synthesis input changes
def test_ops_summary_reflects_synthesis_change():
    import copy
    custom_result = copy.deepcopy(MOCK_SYNTHESIS_RESULT)
    # Replace AHT/AI statements
    for sec in custom_result["report"]:
        for stmt in sec["statements"]:
            if "AHT changed from" in stmt["text"]:
                stmt["text"] = "AHT increased materially during the period."
            if "AI rollout hypothesis" in stmt["text"]:
                stmt["text"] = "AI rollout hypothesis exhibits WEAK_ASSOCIATION with AHT shifts."
                
    res = generate_persona_views(custom_result)
    ops = res["personas"]["OPERATIONS_MANAGER"]
    assert "AHT increased materially during the period." in ops["summary"]
    assert "AI rollout hypothesis exhibits WEAK_ASSOCIATION with AHT shifts." in ops["summary"]
    assert "Handling time decreased materially" not in ops["summary"]

# 25. Test that absent findings are not fabricated and use a neutral fallback
def test_absent_findings_not_fabricated():
    import copy
    custom_result = copy.deepcopy(MOCK_SYNTHESIS_RESULT)
    # Remove all statements from the report
    for sec in custom_result["report"]:
        sec["statements"] = []
        
    res = generate_persona_views(custom_result)
    cx = res["personas"]["CX_MANAGER"]
    ops = res["personas"]["OPERATIONS_MANAGER"]
    # The summary should only contain fallback and disclaimer
    assert "No additional finding is available for this priority." in cx["summary"]
    assert "The available evidence does not establish causality" in cx["summary"]
    assert "No additional finding is available for this priority." in ops["summary"]
    assert "The available evidence does not establish causality" in ops["summary"]
    
# 26. Test that evidence_refs and structured_refs remain unchanged
def test_refs_remain_unchanged():
    res = generate_persona_views(MOCK_SYNTHESIS_RESULT)
    ops = res["personas"]["OPERATIONS_MANAGER"]
    ai_stmt = next(f for f in ops["key_findings"] if "AI rollout" in f["text"])
    assert ai_stmt["evidence_refs"] == ["rollout_report_4"]
    assert ai_stmt["structured_refs"] == ["AHT_ai_hypothesis"]
