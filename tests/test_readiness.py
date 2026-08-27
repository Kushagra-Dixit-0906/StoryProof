import pytest
import copy
from src.engine.readiness import evaluate_decision_readiness, calculate_readiness_score
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
                        "text": "AHT registered a non-material decrease based on configured materiality thresholds.",
                        "classification": "FACT",
                        "structured_refs": ["AHT_materiality"],
                        "evidence_refs": []
                    },
                    {
                        "text": "CSAT registered a non-material decrease based on configured materiality thresholds.",
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

# 1. Abstention checks
def test_abstention_on_invalid_input():
    # None input
    res = evaluate_decision_readiness(None)
    assert res["status"] == "NOT_AVAILABLE"
    assert res["decision_readiness"] == {}
    
    # Invalid dict status
    res2 = evaluate_decision_readiness({"status": "ERROR"})
    assert res2["status"] == "NOT_AVAILABLE"
    
    # Missing report key
    res3 = evaluate_decision_readiness({"status": "SUCCESS"})
    assert res3["status"] == "NOT_AVAILABLE"

# 2. Ready State (Score 100)
def test_ready_state_maximum_score():
    mock_syn = get_clean_mock_synthesis()
    res = evaluate_decision_readiness(mock_syn)
    assert res["status"] == "SUCCESS"
    dr = res["decision_readiness"]
    assert dr["readiness_score"] == 100
    assert dr["overall_state"] == "READY"
    assert dr["flags"]["insufficient_history"] is False
    assert dr["flags"]["high_ambiguity"] is False
    assert dr["flags"]["unverified_material_change"] is False
    assert dr["flags"]["metric_tension_detected"] is False

# 3. Insufficient History State (-30 penalty)
def test_insufficient_history_penalty():
    mock_syn = get_clean_mock_synthesis()
    # Add a statement indicating insufficient history for AI_Resolution_Rate
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
    
    # Evaluate overall (scope includes AI_Resolution_Rate)
    res = evaluate_decision_readiness(mock_syn)
    assert res["status"] == "SUCCESS"
    dr = res["decision_readiness"]
    assert dr["flags"]["insufficient_history"] is True
    assert "AI_Resolution_Rate" in dr["details"]["insufficient_history_metrics"]
    assert dr["readiness_score"] == 70
    assert dr["overall_state"] == "NOT_READY_INSUFFICIENT_DATA"

# 4. High Ambiguity State / Confounding (-30 penalty)
def test_high_ambiguity_penalty():
    mock_syn = get_clean_mock_synthesis()
    # Add multiple hypotheses with strong/moderate associations on AHT
    mock_syn["report"][2]["statements"] = [
        {
            "text": "AI rollout hypothesis exhibits STRONG_ASSOCIATION with AHT shifts.",
            "classification": "ASSOCIATION",
            "structured_refs": ["AHT_ai_hypothesis"],
            "evidence_refs": []
        },
        {
            "text": "CRM patch hypothesis exhibits STRONG_ASSOCIATION with AHT shifts.",
            "classification": "ASSOCIATION",
            "structured_refs": ["AHT_crm_hypothesis"],
            "evidence_refs": []
        }
    ]
    
    res = evaluate_decision_readiness(mock_syn)
    dr = res["decision_readiness"]
    assert dr["flags"]["high_ambiguity"] is True
    assert dr["readiness_score"] == 70
    assert dr["overall_state"] == "NOT_READY_AMBIGUITY"
    assert any("AHT" in msg for msg in dr["details"]["confounding_explanations"])

# 5. Tension / Contradiction State (-20 penalty)
def test_tension_detected_penalty():
    mock_syn = get_clean_mock_synthesis()
    # Add active tension statement
    mock_syn["report"][4] = {
        "title": "Contradictory / Tension Evidence",
        "statements": [
            {
                "text": "Handling time decreased materially, while qualitative evidence contains repeated reports of unresolved interactions.",
                "classification": "ASSOCIATION",
                "structured_refs": ["AHT_materiality"],
                "evidence_refs": ["trans_1"]
            }
        ]
    }
    
    res = evaluate_decision_readiness(mock_syn)
    dr = res["decision_readiness"]
    assert dr["flags"]["metric_tension_detected"] is True
    assert dr["readiness_score"] == 80  # 100 - 20 = 80
    assert dr["overall_state"] == "READY" # score 80 is READY boundary

# 6. Unverified Material Change State (-20 penalty)
def test_unverified_material_change_penalty():
    mock_syn = get_clean_mock_synthesis()
    # Make AHT change material
    mock_syn["report"][1]["statements"][0]["text"] = "AHT registered a material decrease based on configured materiality thresholds."
    
    # We do NOT add any qualitative evidence for AHT, so it is unverified
    res = evaluate_decision_readiness(mock_syn)
    dr = res["decision_readiness"]
    assert dr["flags"]["unverified_material_change"] is True
    assert "AHT" in dr["details"]["unverified_metrics"]
    assert dr["readiness_score"] == 80  # 100 - 20 = 80
    
    # Now verify that adding qualitative evidence containing AHT and evidence_refs resolves the penalty
    mock_syn["report"][3]["statements"] = [
        {
            "text": "Transcripts describe customer support interactions with AHT drops.",
            "classification": "HYPOTHESIS",
            "structured_refs": ["AHT_materiality"],
            "evidence_refs": ["qual_ref_1"]
        }
    ]
    res_verified = evaluate_decision_readiness(mock_syn)
    assert res_verified["decision_readiness"]["flags"]["unverified_material_change"] is False
    assert res_verified["decision_readiness"]["readiness_score"] == 100

# 7. Stacked/Cumulative Penalties
def test_cumulative_penalties():
    mock_syn = get_clean_mock_synthesis()
    
    # 1. Insufficient history (-30)
    mock_syn["report"].append({
        "title": "Data Limitations",
        "statements": [
            {
                "text": "AI_Resolution_Rate could not be fully analyzed as it has insufficient history.",
                "classification": "LIMITATION",
                "structured_refs": ["AI_Resolution_Rate_materiality"],
                "evidence_refs": []
            }
        ]
    })
    
    # 2. Confounding on AHT (-30)
    mock_syn["report"][2]["statements"] = [
        {
            "text": "AI rollout hypothesis exhibits STRONG_ASSOCIATION with AHT shifts.",
            "classification": "ASSOCIATION",
            "evidence_refs": []
        },
        {
            "text": "CRM patch hypothesis exhibits STRONG_ASSOCIATION with AHT shifts.",
            "classification": "ASSOCIATION",
            "evidence_refs": []
        }
    ]
    
    # 3. Tension (-20)
    mock_syn["report"][4]["statements"] = [
        {
            "text": "Tension statement between AHT and unresolved complaints.",
            "classification": "ASSOCIATION",
            "evidence_refs": ["ref_1"]
        }
    ]
    
    # Total score should be 100 - 30 - 30 - 20 = 20
    res = evaluate_decision_readiness(mock_syn)
    dr = res["decision_readiness"]
    assert dr["readiness_score"] == 20
    assert dr["flags"]["insufficient_history"] is True
    assert dr["flags"]["high_ambiguity"] is True
    assert dr["flags"]["metric_tension_detected"] is True
    assert dr["overall_state"] == "NOT_READY_INSUFFICIENT_DATA" # history dominates state

# 8. Persona Integration
def test_persona_integration():
    mock_syn = get_clean_mock_synthesis()
    # Add insufficient history on AI_Resolution_Rate
    mock_syn["report"].append({
        "title": "Data Limitations",
        "statements": [
            {
                "text": "AI_Resolution_Rate could not be fully analyzed as it has insufficient history.",
                "classification": "LIMITATION",
                "structured_refs": ["AI_Resolution_Rate_materiality"],
                "evidence_refs": []
            }
        ]
    })
    
    persona_views = generate_persona_views(mock_syn)
    assert persona_views["status"] == "SUCCESS"
    
    cx = persona_views["personas"]["CX_MANAGER"]
    ops = persona_views["personas"]["OPERATIONS_MANAGER"]
    
    # CX scope does NOT include AI_Resolution_Rate, so its readiness should be READY (100)
    assert cx["decision_readiness"]["readiness_score"] == 100
    assert cx["decision_readiness"]["overall_state"] == "READY"
    
    # Operations scope includes AI_Resolution_Rate, so its readiness should be NOT_READY_INSUFFICIENT_DATA (70)
    assert ops["decision_readiness"]["readiness_score"] == 70
    assert ops["decision_readiness"]["overall_state"] == "NOT_READY_INSUFFICIENT_DATA"

# 9. Causality Language Scan
def test_causality_language_scan():
    mock_syn = get_clean_mock_synthesis()
    # Add various failures
    mock_syn["report"].append({
        "title": "Data Limitations",
        "statements": [
            {
                "text": "AI_Resolution_Rate has insufficient history.",
                "classification": "LIMITATION",
                "structured_refs": [],
                "evidence_refs": []
            }
        ]
    })
    
    res = evaluate_decision_readiness(mock_syn)
    dr = res["decision_readiness"]
    recommendation = dr["recommendation"]
    
    # Prohibited words list
    prohibited = ["caused", "causes", "caused by", "causal", "responsible for", "resulted in", "led to", "due to", "because of", "driven by", "responsible"]
    for p_word in prohibited:
        assert p_word not in recommendation.lower(), f"Forbidden causal word '{p_word}' found in recommendation: '{recommendation}'"
        
    assert dr["causality_disclaimer"] == "The available evidence does not establish causality; observed changes represent associations and candidate explanations only."

# 10. Dynamic Synthesis Input Mapping (No hardcoding)
def test_dynamic_synthesis_input_mapping():
    mock_syn = get_clean_mock_synthesis()
    
    # First: clean run
    res1 = evaluate_decision_readiness(mock_syn)
    assert res1["decision_readiness"]["readiness_score"] == 100
    
    # Dynamically change CSAT to material but unverified
    mock_syn["report"][1]["statements"][1]["text"] = "CSAT registered a material decrease."
    res2 = evaluate_decision_readiness(mock_syn)
    assert res2["decision_readiness"]["readiness_score"] == 80
    assert res2["decision_readiness"]["flags"]["unverified_material_change"] is True
    assert "CSAT" in res2["decision_readiness"]["details"]["unverified_metrics"]
    
    # Dynamically verify CSAT by adding qualitative evidence
    mock_syn["report"][3]["statements"].append({
        "text": "CSAT survey comments show negative customer feedback.",
        "classification": "HYPOTHESIS",
        "evidence_refs": ["fb_1"]
    })
    res3 = evaluate_decision_readiness(mock_syn)
    assert res3["decision_readiness"]["readiness_score"] == 100
    assert res3["decision_readiness"]["flags"]["unverified_material_change"] is False

# 11. Regression Pass (Verify existing Milestone 4.1 fields are identical)
def test_regression_persona_fields_intact():
    # Use real synthesis output to compare before and after
    real_synthesis = generate_synthesis_report("data")
    assert real_synthesis["status"] == "SUCCESS"
    
    # Run the view generator
    res = generate_persona_views(real_synthesis)
    assert res["status"] == "SUCCESS"
    
    # Verify standard keys are exactly matching what is required in 4.1
    for p_name in ["CX_MANAGER", "OPERATIONS_MANAGER"]:
        payload = res["personas"][p_name]
        
        # Verify keys
        required_keys = ["persona", "priority", "summary", "key_findings", "risks", "evidence_refs", "structured_refs", "decision_context", "decision_readiness"]
        for key in required_keys:
            assert key in payload
            
        # Verify findings sorting and counts are valid
        assert len(payload["priority"]) > 0
        assert len(payload["summary"]) > 0
        assert "The available evidence does not establish causality" in payload["summary"]
        
        # Verify no causal language in summary
        causal_words = ["caused", "causes", "responsible for", "resulted in", "led to", "due to", "drove", "driven by", "because of"]
        for word in causal_words:
            assert word not in payload["summary"].lower()
            assert word not in payload["decision_context"].lower()
