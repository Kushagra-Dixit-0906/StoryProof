import pytest
import copy
from src.engine.actions import generate_action_recommendations
from src.engine.personas import generate_persona_views
from src.engine.synthesis import generate_synthesis_report

# Helper to construct a clean mock synthesis result
def get_clean_mock_synthesis():
    return {
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
                    }
                ]
            },
            {
                "title": "Materiality & Statistical Signal",
                "statements": [
                    {
                        "text": "AHT registered a non-material decrease.",
                        "classification": "FACT",
                        "structured_refs": ["AHT_materiality"],
                        "evidence_refs": []
                    },
                    {
                        "text": "CSAT registered a non-material decrease.",
                        "classification": "FACT",
                        "structured_refs": ["CSAT_materiality"],
                        "evidence_refs": []
                    }
                ]
            },
            {
                "title": "Competing Hypotheses",
                "statements": [
                    {
                        "text": "AI rollout hypothesis exhibits WEAK_ASSOCIATION with AHT shifts.",
                        "classification": "ASSOCIATION",
                        "structured_refs": ["AHT_ai_hypothesis"],
                        "evidence_refs": []
                    }
                ]
            },
            {
                "title": "Qualitative Evidence",
                "statements": []
            },
            {
                "title": "Contradictory / Tension Evidence",
                "statements": []
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

# 1 & 2. None and invalid inputs return NOT_AVAILABLE
def test_abstention_on_none_and_invalid():
    res1 = generate_action_recommendations(None, None)
    assert res1["status"] == "NOT_AVAILABLE"
    assert res1["persona_actions"] == {}
    
    mock_syn = get_clean_mock_synthesis()
    res2 = generate_action_recommendations(mock_syn, None)
    assert res2["status"] == "NOT_AVAILABLE"
    
    mock_views = {"status": "SUCCESS", "personas": {}}
    res3 = generate_action_recommendations(None, mock_views)
    assert res3["status"] == "NOT_AVAILABLE"

# 3. Action Schema Validation
def test_action_schema_validation():
    mock_syn = get_clean_mock_synthesis()
    
    # Trigger insufficient history for AI_Resolution_Rate
    mock_syn["report"].append({
        "title": "Data Limitations",
        "statements": [
            {
                "text": "AI_Resolution_Rate could not be fully analyzed as it has insufficient history (21 days available, 60 days required).",
                "classification": "LIMITATION",
                "structured_refs": ["AI_Resolution_Rate_materiality"],
                "evidence_refs": []
            }
        ]
    })
    
    views = generate_persona_views(mock_syn)
    res = generate_action_recommendations(mock_syn, views)
    assert res["status"] == "SUCCESS"
    
    # Check all fields for the generated action
    actions = res["persona_actions"]["OPERATIONS_MANAGER"]
    assert len(actions) > 0
    act = actions[0]
    
    required_keys = [
        "id", "action_type", "title", "description", "priority", 
        "observed_finding", "reason", "justification", 
        "structured_refs", "evidence_refs", "trigger_info"
    ]
    for key in required_keys:
        assert key in act

# 4. Rule 1 - Insufficient History
def test_rule1_insufficient_history_action():
    mock_syn = get_clean_mock_synthesis()
    mock_syn["report"].append({
        "title": "Data Limitations",
        "statements": [
            {
                "text": "CSAT could not be fully analyzed as it has insufficient history (15 days available, 90 days required).",
                "classification": "LIMITATION",
                "structured_refs": ["CSAT_materiality"],
                "evidence_refs": []
            }
        ]
    })
    
    views = generate_persona_views(mock_syn)
    res = generate_action_recommendations(mock_syn, views)
    cx_actions = res["persona_actions"]["CX_MANAGER"]
    
    # Insufficient history for CSAT should be HIGH priority (primary metric)
    assert any(
        a["action_type"] == "STABILIZE_BASELINE" and 
        a["priority"] == "HIGH" and 
        "15" in a["justification"] and "90" in a["justification"]
        for a in cx_actions
    )

# 5. Rule 2 - Ambiguity / System Patch
def test_rule2_ambiguity_system_patch_action():
    mock_syn = get_clean_mock_synthesis()
    # Add confounding patch association for FCR
    mock_syn["report"][2]["statements"] = [
        {
            "text": "AI rollout hypothesis exhibits STRONG_ASSOCIATION with FCR shifts.",
            "classification": "ASSOCIATION",
            "structured_refs": ["FCR_ai_hypothesis"],
            "evidence_refs": []
        },
        {
            "text": "CRM patch hypothesis exhibits STRONG_ASSOCIATION with FCR shifts.",
            "classification": "ASSOCIATION",
            "structured_refs": ["FCR_crm_hypothesis"],
            "evidence_refs": ["crm_report_1"]
        }
    ]
    
    views = generate_persona_views(mock_syn)
    res = generate_action_recommendations(mock_syn, views)
    ops_actions = res["persona_actions"]["OPERATIONS_MANAGER"]
    
    assert any(
        a["action_type"] == "SYSTEM_PATCH" and 
        "FCR" in a["id"] and 
        "crm_report_1" in a["evidence_refs"]
        for a in ops_actions
    )

# 6. Rule 3 - Metric Tension Guardrail
def test_rule3_metric_tension_action():
    mock_syn = get_clean_mock_synthesis()
    # Add active tension
    mock_syn["report"][4] = {
        "title": "Contradictory / Tension Evidence",
        "statements": [
            {
                "text": "Handling time decreased materially, while qualitative evidence contains repeated reports of unresolved interactions.",
                "classification": "ASSOCIATION",
                "structured_refs": ["AHT_materiality"],
                "evidence_refs": ["trans_5"]
            }
        ]
    }
    
    views = generate_persona_views(mock_syn)
    res = generate_action_recommendations(mock_syn, views)
    ops_actions = res["persona_actions"]["OPERATIONS_MANAGER"]
    
    assert any(
        a["action_type"] == "RESOLUTION_GUARDRAIL" and 
        "AHT" in a["id"] and 
        a["evidence_refs"] == ["trans_5"]
        for a in ops_actions
    )

# 7. Rule 4 - Verified Optimization
def test_rule4_verified_optimization_action():
    mock_syn = get_clean_mock_synthesis()
    # CSAT change is material and CSAT increased
    mock_syn["report"][0]["statements"][1]["text"] = "CSAT score increased from 68.88 to 78.02 points (absolute change: 9.14 points, relative change: +13.3%)."
    mock_syn["report"][1]["statements"][1]["text"] = "CSAT registered a material increase based on configured materiality thresholds."
    
    # To satisfy Rule 4, we must have qualitative verification for CSAT material change
    mock_syn["report"][3]["statements"].append({
        "text": "Qualitative customer surveys show positive CSAT comments.",
        "classification": "HYPOTHESIS",
        "evidence_refs": ["fb_positive_2"]
    })
    
    views = generate_persona_views(mock_syn)
    res = generate_action_recommendations(mock_syn, views)
    cx_actions = res["persona_actions"]["CX_MANAGER"]
    
    # Ready/no risks, so optimization should trigger with LOW priority
    assert any(
        a["action_type"] == "OPERATIONAL_OPTIMIZATION" and 
        a["priority"] == "LOW" and 
        a["evidence_refs"] == ["fb_positive_2"]
        for a in cx_actions
    )

# 8 & 9. No Optimization under NOT_READY states
def test_no_optimization_under_not_ready():
    mock_syn = get_clean_mock_synthesis()
    # CSAT change is material and improved
    mock_syn["report"][0]["statements"][1]["text"] = "CSAT score increased from 68.88 to 78.02 points."
    mock_syn["report"][1]["statements"][1]["text"] = "CSAT registered a material increase based on configured materiality thresholds."
    mock_syn["report"][3]["statements"].append({
        "text": "Qualitative customer surveys show positive CSAT comments.",
        "classification": "HYPOTHESIS",
        "evidence_refs": ["fb_positive_2"]
    })
    
    # 1. State: NOT_READY_INSUFFICIENT_DATA
    mock_syn_history = copy.deepcopy(mock_syn)
    mock_syn_history["report"].append({
        "title": "Data Limitations",
        "statements": [
            {
                "text": "Retention_Rate has insufficient history.",
                "classification": "LIMITATION",
                "structured_refs": ["Retention_Rate_materiality"],
                "evidence_refs": []
            }
        ]
    })
    views_history = generate_persona_views(mock_syn_history)
    res_history = generate_action_recommendations(mock_syn_history, views_history)
    cx_actions_history = res_history["persona_actions"]["CX_MANAGER"]
    # Should not contain optimization actions because insufficient history is triggered
    assert not any(a["action_type"] == "OPERATIONAL_OPTIMIZATION" for a in cx_actions_history)

    # 2. State: NOT_READY_AMBIGUITY
    mock_syn_ambig = copy.deepcopy(mock_syn)
    mock_syn_ambig["report"][2]["statements"] = [
        {
            "text": "AI rollout hypothesis exhibits STRONG_ASSOCIATION with CSAT shifts.",
            "classification": "ASSOCIATION",
            "evidence_refs": []
        },
        {
            "text": "CRM patch hypothesis exhibits STRONG_ASSOCIATION with CSAT shifts.",
            "classification": "ASSOCIATION",
            "evidence_refs": []
        }
    ]
    views_ambig = generate_persona_views(mock_syn_ambig)
    res_ambig = generate_action_recommendations(mock_syn_ambig, views_ambig)
    cx_actions_ambig = res_ambig["persona_actions"]["CX_MANAGER"]
    # Should not contain optimization actions because high ambiguity is triggered
    assert not any(a["action_type"] == "OPERATIONAL_OPTIMIZATION" for a in cx_actions_ambig)

# 10. Wording adapts to KPI direction changes
def test_adaptability_to_kpi_direction_change():
    mock_syn = get_clean_mock_synthesis()
    
    # CSAT material increase
    mock_syn_inc = copy.deepcopy(mock_syn)
    mock_syn_inc["report"][0]["statements"][1]["text"] = "CSAT score increased from 68.88 to 78.02 points."
    mock_syn_inc["report"][1]["statements"][1]["text"] = "CSAT registered a material increase based on configured materiality thresholds."
    mock_syn_inc["report"][3]["statements"].append({
        "text": "Qualitative feedback show CSAT improvements.",
        "classification": "HYPOTHESIS",
        "evidence_refs": ["fb_inc"]
    })
    views_inc = generate_persona_views(mock_syn_inc)
    res_inc = generate_action_recommendations(mock_syn_inc, views_inc)
    
    # CSAT material decrease
    mock_syn_dec = copy.deepcopy(mock_syn)
    mock_syn_dec["report"][0]["statements"][1]["text"] = "CSAT score decreased from 78.02 to 68.88 points."
    mock_syn_dec["report"][1]["statements"][1]["text"] = "CSAT registered a material decrease based on configured materiality thresholds."
    mock_syn_dec["report"][3]["statements"].append({
        "text": "Qualitative feedback show CSAT decline.",
        "classification": "HYPOTHESIS",
        "evidence_refs": ["fb_dec"]
    })
    views_dec = generate_persona_views(mock_syn_dec)
    res_dec = generate_action_recommendations(mock_syn_dec, views_dec)
    
    # Verify that in increase, optimization is generated
    cx_inc = res_inc["persona_actions"]["CX_MANAGER"]
    assert any(a["action_type"] == "OPERATIONAL_OPTIMIZATION" for a in cx_inc)
    
    # Verify that in decrease, optimization is NOT generated
    cx_dec = res_dec["persona_actions"]["CX_MANAGER"]
    assert not any(a["action_type"] == "OPERATIONAL_OPTIMIZATION" for a in cx_dec)

# 11 & 12. No hardcoding of current scenario values
def test_no_hardcoding():
    # If synthesis has completely different KPIs, checks still pass dynamically
    mock_syn = {
        "status": "SUCCESS",
        "report": [
            {
                "title": "KPI Movement",
                "statements": [
                    {
                        "text": "Custom_Metric changed from 10 to 20.",
                        "classification": "FACT",
                        "structured_refs": ["Custom_Metric_materiality"],
                        "evidence_refs": []
                    }
                ]
            },
            {
                "title": "Materiality & Statistical Signal",
                "statements": [
                    {
                        "text": "Custom_Metric registered a material increase.",
                        "classification": "FACT",
                        "structured_refs": ["Custom_Metric_materiality"],
                        "evidence_refs": []
                    }
                ]
            },
            {
                "title": "Competing Hypotheses",
                "statements": []
            },
            {
                "title": "Qualitative Evidence",
                "statements": []
            },
            {
                "title": "Contradictory / Tension Evidence",
                "statements": []
            },
            {
                "title": "Causality Disclaimer",
                "statements": []
            }
        ]
    }
    
    views = generate_persona_views(mock_syn)
    res = generate_action_recommendations(mock_syn, views)
    assert res["status"] == "SUCCESS"

# 13. Priority Determinism
def test_priority_determinism():
    mock_syn = get_clean_mock_synthesis()
    # Add tension and history failure
    mock_syn["report"].append({
        "title": "Data Limitations",
        "statements": [
            {
                "text": "CSAT has insufficient history.",
                "classification": "LIMITATION",
                "structured_refs": ["CSAT_materiality"],
                "evidence_refs": []
            }
        ]
    })
    
    views = generate_persona_views(mock_syn)
    res = generate_action_recommendations(mock_syn, views)
    cx_actions = res["persona_actions"]["CX_MANAGER"]
    
    # Priority for CSAT history should always be HIGH
    csat_hist = next(a for a in cx_actions if "CSAT" in a["id"] and a["action_type"] == "STABILIZE_BASELINE")
    assert csat_hist["priority"] == "HIGH"

# 14. Deterministic Ordering
def test_deterministic_ordering():
    mock_syn = get_clean_mock_synthesis()
    mock_syn["report"].append({
        "title": "Data Limitations",
        "statements": [
            {
                "text": "CSAT has insufficient history.",
                "classification": "LIMITATION",
                "structured_refs": ["CSAT_materiality"],
                "evidence_refs": []
            }
        ]
    })
    mock_syn["report"][4] = {
        "title": "Contradictory / Tension Evidence",
        "statements": [
            {
                "text": "FCR registered a non-material change, whereas CSAT declined materially, while customer feedback contains complaints about interaction resolution.",
                "classification": "ASSOCIATION",
                "structured_refs": ["FCR_materiality", "CSAT_materiality"],
                "evidence_refs": ["csat_comments_3"]
            }
        ]
    }
    
    views1 = generate_persona_views(mock_syn)
    res1 = generate_action_recommendations(mock_syn, views1)
    
    views2 = generate_persona_views(mock_syn)
    res2 = generate_action_recommendations(mock_syn, views2)
    
    assert res1 == res2

# 15 & 16. Reference and Evidence Reference Preservation
def test_reference_preservation():
    mock_syn = get_clean_mock_synthesis()
    mock_syn["report"][4] = {
        "title": "Contradictory / Tension Evidence",
        "statements": [
            {
                "text": "Handling time decreased materially, while qualitative evidence contains repeated reports of unresolved interactions.",
                "classification": "ASSOCIATION",
                "structured_refs": ["AHT_materiality"],
                "evidence_refs": ["trans_99"]
            }
        ]
    }
    
    views = generate_persona_views(mock_syn)
    res = generate_action_recommendations(mock_syn, views)
    ops_actions = res["persona_actions"]["OPERATIONS_MANAGER"]
    
    tension_act = next(a for a in ops_actions if a["action_type"] == "RESOLUTION_GUARDRAIL")
    assert "AHT_materiality" in tension_act["structured_refs"]
    assert tension_act["evidence_refs"] == ["trans_99"]

# 17. No fabricated references
def test_no_fabricated_references():
    mock_syn = get_clean_mock_synthesis()
    views = generate_persona_views(mock_syn)
    res = generate_action_recommendations(mock_syn, views)
    
    for persona, actions in res["persona_actions"].items():
        for act in actions:
            for ref in act["evidence_refs"]:
                assert ref in ["trans_5", "csat_comments_3", "crm_report_1"] or any(ref in stmt["evidence_refs"] for sec in mock_syn["report"] for stmt in sec["statements"])

# 18. No prohibited causal language
def test_no_prohibited_causal_language():
    mock_syn = get_clean_mock_synthesis()
    mock_syn["report"].append({
        "title": "Data Limitations",
        "statements": [
            {
                "text": "CSAT has insufficient history.",
                "classification": "LIMITATION",
                "structured_refs": [],
                "evidence_refs": []
            }
        ]
    })
    
    views = generate_persona_views(mock_syn)
    res = generate_action_recommendations(mock_syn, views)
    
    prohibited = ["caused", "causes", "caused by", "causal", "responsible for", "resulted in", "led to", "due to", "because of", "driven by", "responsible"]
    for persona, actions in res["persona_actions"].items():
        for act in actions:
            for field in ["title", "description", "observed_finding", "reason", "justification"]:
                text = act[field].lower()
                for p_word in prohibited:
                    assert p_word not in text, f"Causal word '{p_word}' found in action field '{field}': '{act[field]}'"

# 19 & 20. Persona Differentiations
def test_persona_differentiation():
    mock_syn = get_clean_mock_synthesis()
    
    mock_syn["report"].append({
        "title": "Data Limitations",
        "statements": [
            {
                "text": "AI_Resolution_Rate has insufficient history.",
                "classification": "LIMITATION",
                "structured_refs": ["AI_Resolution_Rate_materiality"],
                "evidence_refs": []
            }
        ]
    })
    
    views = generate_persona_views(mock_syn)
    res = generate_action_recommendations(mock_syn, views)
    
    cx = res["persona_actions"]["CX_MANAGER"]
    ops = res["persona_actions"]["OPERATIONS_MANAGER"]
    
    assert any("AI_Resolution_Rate" in a["id"] for a in ops)
    assert not any("AI_Resolution_Rate" in a["id"] for a in cx)

# 21 & 22. Existing Persona and Readiness Fields Remain Unchanged
def test_existing_persona_and_readiness_intact():
    real_synthesis = generate_synthesis_report("data")
    views = generate_persona_views(real_synthesis)
    
    for persona_name in ["CX_MANAGER", "OPERATIONS_MANAGER"]:
        payload = views["personas"][persona_name]
        
        assert "persona" in payload
        assert "priority" in payload
        assert "summary" in payload
        assert "key_findings" in payload
        assert "risks" in payload
        assert "evidence_refs" in payload
        assert "structured_refs" in payload
        assert "decision_context" in payload
        
        assert "decision_readiness" in payload
        dr = payload["decision_readiness"]
        assert "overall_state" in dr
        assert "readiness_score" in dr
        assert "flags" in dr
        assert "details" in dr
        assert "recommendation" in dr
        assert "causality_disclaimer" in dr
        
        assert "recommended_actions" in payload

# 23. Repeated execution produces identical outputs
def test_repeated_execution_consistency():
    mock_syn = get_clean_mock_synthesis()
    views = generate_persona_views(mock_syn)
    res1 = generate_action_recommendations(mock_syn, views)
    res2 = generate_action_recommendations(mock_syn, views)
    assert res1 == res2

# 24. Empty or missing findings are handled safely
def test_empty_findings_safety():
    mock_syn = {
        "status": "SUCCESS",
        "report": []
    }
    views = generate_persona_views(mock_syn)
    res = generate_action_recommendations(mock_syn, views)
    assert res["status"] == "SUCCESS"
    assert res["persona_actions"]["CX_MANAGER"] == []
    assert res["persona_actions"]["OPERATIONS_MANAGER"] == []
