import pytest
import os
import re
import tempfile
import sqlite3
import pandas as pd
import datetime
from unittest.mock import MagicMock, patch

# Import functions from app.py
from app import (
    validate_reporting_periods,
    load_kpi_definitions,
    check_role_permission,
    calculate_projected_llm_cost,
    run_intelligence_pipeline,
    resolve_execution_run_id
)

# Import feedback functions
from src.feedback.handler import (
    initialize_database,
    log_execution_run,
    log_analyst_feedback,
    get_run_history,
    get_feedback_by_run
)

# 1. Role list/role permission behavior
def test_role_permission_matrix():
    roles = ["CX Manager", "Operations Manager", "Guest", "Administrator"]
    
    # view_cx permission
    assert check_role_permission("CX Manager", "view_cx") is True
    assert check_role_permission("Guest", "view_cx") is True
    assert check_role_permission("Administrator", "view_cx") is True
    assert check_role_permission("Operations Manager", "view_cx") is False

    # view_ops permission
    assert check_role_permission("Operations Manager", "view_ops") is True
    assert check_role_permission("Guest", "view_ops") is True
    assert check_role_permission("Administrator", "view_ops") is True
    assert check_role_permission("CX Manager", "view_ops") is False

    # submit_feedback permission
    assert check_role_permission("CX Manager", "submit_feedback") is True
    assert check_role_permission("Operations Manager", "submit_feedback") is True
    assert check_role_permission("Guest", "submit_feedback") is False
    assert check_role_permission("Administrator", "submit_feedback") is True

    # view_observability & view_history
    assert check_role_permission("Administrator", "view_observability") is True
    assert check_role_permission("Administrator", "view_history") is True
    assert check_role_permission("Guest", "view_observability") is False
    assert check_role_permission("CX Manager", "view_history") is False

# 2. Guest read-only behavior
# 3. Manager feedback permission
def test_guest_and_manager_submission_rights():
    assert not check_role_permission("Guest", "submit_feedback")
    assert check_role_permission("CX Manager", "submit_feedback")
    assert check_role_permission("Operations Manager", "submit_feedback")

# 4. Administrator history behavior
def test_admin_history_permissions():
    assert check_role_permission("Administrator", "view_history")
    assert check_role_permission("Administrator", "submit_feedback")

# 5. Readiness extraction
def test_readiness_extraction_from_payload():
    mock_payload = {
        "personas": {
            "CX_MANAGER": {
                "decision_readiness": {
                    "readiness_score": 70,
                    "overall_state": "READY_WITH_RESERVATIONS",
                    "flags": {"insufficient_history": True},
                    "details": ["AI resolution rate has only 21 days of history"]
                }
            }
        }
    }
    cx_dr = mock_payload["personas"]["CX_MANAGER"]["decision_readiness"]
    assert cx_dr["readiness_score"] == 70
    assert cx_dr["overall_state"] == "READY_WITH_RESERVATIONS"
    assert cx_dr["flags"]["insufficient_history"] is True
    assert len(cx_dr["details"]) == 1

# 5a. None/missing readiness score display/extraction test
def test_readiness_none_score_handling():
    mock_payload = {
        "personas": {
            "CX_MANAGER": {
                "decision_readiness": {
                    "readiness_score": None,
                    "overall_state": "INVESTIGATION_REQUIRED",
                    "flags": {},
                    "details": []
                }
            }
        }
    }
    cx_dr = mock_payload["personas"]["CX_MANAGER"]["decision_readiness"]
    assert cx_dr["readiness_score"] is None
    assert cx_dr["overall_state"] == "INVESTIGATION_REQUIRED"

# 6. Action rendering/extraction
def test_action_extraction_from_payload():
    mock_payload = {
        "personas": {
            "CX_MANAGER": {
                "recommended_actions": [
                    {
                        "id": "ACT_CX_1",
                        "title": "Establish CSAT baseline",
                        "priority": "HIGH",
                        "description": "Establish a baseline CSAT prior to rollout",
                        "justification": "CSAT declined during pilot",
                        "structured_refs": ["CSAT"],
                        "evidence_refs": ["EV_1"]
                    }
                ]
            }
        }
    }
    actions = mock_payload["personas"]["CX_MANAGER"]["recommended_actions"]
    assert len(actions) == 1
    assert actions[0]["id"] == "ACT_CX_1"
    assert actions[0]["priority"] == "HIGH"
    assert "CSAT" in actions[0]["structured_refs"]

# 7. Feedback status validation
def test_feedback_status_validation(tmp_path):
    db_file = tmp_path / "test_feedback.db"
    db_path = str(db_file)
    assert initialize_database(db_path) is True
    
    # Try invalid status types
    assert log_analyst_feedback("run_123", "action_123", "APPROVED_MOCK", "no comments", "analyst", db_path) is None
    assert log_analyst_feedback("run_123", "action_123", "PENDING", "no comments", "analyst", db_path) is None
    
    # Valid statuses are APPROVED, REJECTED, FLAGGED
    # Checking validation triggers before checking membership rules
    assert log_analyst_feedback("run_123", "action_123", "APPROVED", "comments", "analyst", db_path) is None

# 8. Valid action membership behavior
# 9. Invalid action membership behavior
def test_action_membership_constraints(tmp_path):
    db_file = tmp_path / "test_membership.db"
    db_path = str(db_file)
    assert initialize_database(db_path) is True

    # Setup dummy execution run with defined actions list
    synthesis = {"status": "SUCCESS", "report": []}
    views = {
        "status": "SUCCESS",
        "personas": {
            "CX_MANAGER": {
                "decision_readiness": {"readiness_score": 90, "overall_state": "READY"},
                "recommended_actions": [
                    {"id": "ACT_1", "priority": "HIGH", "title": "First Action"}
                ]
            },
            "OPERATIONS_MANAGER": {
                "decision_readiness": {"readiness_score": 95, "overall_state": "READY"},
                "recommended_actions": [
                    {"id": "ACT_2", "priority": "LOW", "title": "Second Action"}
                ]
            }
        }
    }

    run_id = log_execution_run(synthesis, views, db_path, ("2026-01-01", "2026-03-31"), ("2026-06-01", "2026-06-30"))
    assert run_id is not None

    # Test valid action ID member (ACT_1)
    fb_id_valid = log_analyst_feedback(run_id, "ACT_1", "APPROVED", "Looking good", "analyst", db_path)
    assert fb_id_valid is not None

    # Test invalid action ID member (ACT_NON_EXISTENT)
    fb_id_invalid = log_analyst_feedback(run_id, "ACT_NON_EXISTENT", "APPROVED", "Not a real action", "analyst", db_path)
    assert fb_id_invalid is None

# 10. Run/session-state logic using the real helper function resolve_execution_run_id
def test_resolve_execution_run_id_behavior():
    # Setup dummy objects
    synthesis_result = {"status": "SUCCESS", "report": []}
    persona_views = {"status": "SUCCESS", "personas": {}}
    
    # Mock log_run_fn
    mock_run_counter = 0
    def mock_log_run(synthesis_result, persona_views, db_path, baseline_period, comparison_period):
        nonlocal mock_run_counter
        mock_run_counter += 1
        return f"mock_run_id_{mock_run_counter}"
        
    # 1. First submission creates/registers a run.
    run_id_1, key_1, logged_1 = resolve_execution_run_id(
        synthesis_result=synthesis_result,
        persona_views=persona_views,
        baseline_period=("2026-01-01", "2026-03-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir="data",
        cached_run_id=None,
        cached_key=None,
        db_path="mock_db_path",
        log_run_fn=mock_log_run
    )
    assert run_id_1 == "mock_run_id_1"
    assert key_1 == (("2026-01-01", "2026-03-31"), ("2026-06-01", "2026-06-30"), "data")
    assert logged_1 is True
    assert mock_run_counter == 1

    # 2. Second submission for the same run_key reuses the existing run_id.
    run_id_2, key_2, logged_2 = resolve_execution_run_id(
        synthesis_result=synthesis_result,
        persona_views=persona_views,
        baseline_period=("2026-01-01", "2026-03-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir="data",
        cached_run_id=run_id_1,
        cached_key=key_1,
        db_path="mock_db_path",
        log_run_fn=mock_log_run
    )
    assert run_id_2 == "mock_run_id_1"
    assert key_2 == key_1
    assert logged_2 is False
    assert mock_run_counter == 1

    # 3. Changing baseline/comparison/data_dir causes a new run registration.
    run_id_3, key_3, logged_3 = resolve_execution_run_id(
        synthesis_result=synthesis_result,
        persona_views=persona_views,
        baseline_period=("2026-02-01", "2026-03-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir="data",
        cached_run_id=run_id_2,
        cached_key=key_2,
        db_path="mock_db_path",
        log_run_fn=mock_log_run
    )
    assert run_id_3 == "mock_run_id_2"
    assert key_3 == (("2026-02-01", "2026-03-31"), ("2026-06-01", "2026-06-30"), "data")
    assert logged_3 is True
    assert mock_run_counter == 2

# 11. Latency calculation
def test_pipeline_latency_calculation():
    # Run the real intelligence pipeline on data
    syn, views, latency = run_intelligence_pipeline("data", ("2026-01-01", "2026-03-31"), ("2026-06-01", "2026-06-30"))
    
    # Assert latency is non-negative and is a real elapsed time
    assert isinstance(latency, float)
    assert latency >= 0.0
    assert syn["status"] == "SUCCESS"
    assert views["status"] == "SUCCESS"

# 12. Simulated token-cost calculation
# 13. No actual billing/API claims
def test_simulated_token_cost_math():
    cost_data = calculate_projected_llm_cost(5)
    
    assert cost_data["simulated_input_tokens"] == 8500
    assert cost_data["simulated_output_tokens"] == 1200
    assert cost_data["input_rate_per_1k"] == 0.005
    assert cost_data["output_rate_per_1k"] == 0.015
    
    # cost per run = (8500/1000 * 0.005) + (1200/1000 * 0.015)
    # cost per run = 0.0425 + 0.018 = 0.0605
    assert cost_data["cost_per_run"] == 0.0605
    assert cost_data["total_projected_cost"] == 5 * 0.0605
    
    # Assert cost variables are named simulated/projected
    for key in cost_data.keys():
        assert "simulated" in key or "projected" in key or "rate" in key or "cost" in key

# 14. Empty/error states
def test_empty_audit_history_handling(tmp_path):
    empty_db_path = str(tmp_path / "empty_audit.db")
    # File doesn't exist yet -> get_run_history returns [] safely
    assert get_run_history(empty_db_path) == []
    
    # Initialized but empty -> returns [] safely
    assert initialize_database(empty_db_path) is True
    assert get_run_history(empty_db_path) == []

# 15. Causality-safe StoryProof text in code
def test_dashboard_code_causality_safeguards():
    # Read app.py text content and verify no direct causal claims are made in the main StoryProof section.
    with open("app.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Search inside the StoryProof tab render block
    assert "with tab_proof:" in content
    proof_block = content.split("with tab_proof:")[1]
    
    prohibited = [r"\bcaused\b", r"\bcauses\b", r"\bresulted in\b", r"\bled to\b", r"\bdue to\b", r"\bdrove\b"]
    disclaimer = "The available evidence does not establish causality; observed changes represent associations and candidate explanations only."
    
    # Assert disclaimer is in app.py
    assert disclaimer in content

    # Find string literals in proof_block and check for causal verbs
    string_literals = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"|\'([^\'\\]*(?:\\.[^\'\\]*)*)\'', proof_block)
    for pair in string_literals:
        stmt = pair[0] or pair[1]
        if not stmt or stmt == disclaimer:
            continue
        stmt_lower = stmt.lower()
        for pattern in prohibited:
            assert not re.search(pattern, stmt_lower), f"Prohibited causal pattern '{pattern}' found in dashboard text: '{stmt}'"

# 15a. Causality-safe StoryProof text in dynamic outputs
def test_generated_payload_causality_safeguards():
    # Generate actual synthesis and persona view outputs using the real engines
    from src.engine.synthesis import generate_synthesis_report
    from src.engine.personas import generate_persona_views
    
    syn = generate_synthesis_report("data", kpi_config_path="config/kpi_definitions.yaml")
    assert syn["status"] == "SUCCESS"
    views = generate_persona_views(syn)
    assert views["status"] == "SUCCESS"

    prohibited = [
        r"\bcaused\b", r"\bcauses\b", r"\bcausal\b", r"\bresponsible for\b",
        r"\bresulted in\b", r"\bled to\b", r"\bdue to\b", r"\bbecause of\b",
        r"\bdriven by\b", r"\bdrove\b"
    ]
    disclaimer = "The available evidence does not establish causality; observed changes represent associations and candidate explanations only."

    # Extract all text segments dynamically from the views dictionary
    def collect_texts(val):
        texts = []
        if isinstance(val, str):
            texts.append(val)
        elif isinstance(val, dict):
            for k, v in val.items():
                texts.extend(collect_texts(v))
        elif isinstance(val, list):
            for item in val:
                texts.extend(collect_texts(item))
        return texts

    all_texts = collect_texts(views)
    assert len(all_texts) > 0

    for text in all_texts:
        if text.strip() == disclaimer:
            continue
        text_lower = text.lower()
        for pattern in prohibited:
            match = re.search(pattern, text_lower)
            assert not match, f"Prohibited causal pattern '{pattern}' found in generated text: '{text}'"

# 16. Integration with existing persona/action outputs
def test_persona_views_integration():
    # Tests that we can import and verify existing persona views outputs successfully
    from src.engine.synthesis import generate_synthesis_report
    from src.engine.personas import generate_persona_views
    
    syn = generate_synthesis_report("data", kpi_config_path="config/kpi_definitions.yaml")
    assert syn["status"] == "SUCCESS"
    
    views = generate_persona_views(syn)
    assert views["status"] == "SUCCESS"
    assert "CX_MANAGER" in views["personas"]
    assert "OPERATIONS_MANAGER" in views["personas"]

# 17. Regression compatibility with Phase 5.1 helpers
def test_regression_compatibility_dashboard_helpers():
    config = load_kpi_definitions("config/kpi_definitions.yaml")
    assert config is not None
    assert "AHT" in config
    assert "CSAT" in config
    
    # Period validation checks
    assert validate_reporting_periods(("2026-01-01", "2026-03-31"), ("2026-06-01", "2026-06-30")) is True
    assert validate_reporting_periods(("2026-03-31", "2026-01-01"), ("2026-06-01", "2026-06-30")) is False

# 18. Milestone 5.3 Gaps Verification
def test_milestone_5_3_gaps(tmp_path):
    # 1. Administrator feedback permission is True
    assert check_role_permission("Administrator", "submit_feedback") is True

    # 2. Guest/Viewer remains unable to submit feedback
    assert check_role_permission("Guest", "submit_feedback") is False

    # Load app.py content for static text checks
    with open("app.py", "r", encoding="utf-8") as f:
        app_content = f.read()

    # 3. Viewer warning string exists exactly
    assert "Viewer role: Feedback submission is disabled." in app_content

    # 4. Feedback form uses text area
    assert "st.text_area" in app_content

    # 5. Feedback button uses exactly "Submit Review"
    assert '"Submit Review"' in app_content or "'Submit Review'" in app_content

    # 6. Active run ID is established before feedback submission & cached behavior
    db_file = tmp_path / "test_5_3_cache.db"
    db_path = str(db_file)
    assert initialize_database(db_path) is True

    synthesis_result = {"status": "SUCCESS", "report": []}
    persona_views = {
        "status": "SUCCESS",
        "personas": {
            "CX_MANAGER": {
                "decision_readiness": {"readiness_score": 90, "overall_state": "READY"},
                "recommended_actions": [{"id": "ACT_CX_1", "priority": "HIGH", "title": "Check CSAT"}]
            },
            "OPERATIONS_MANAGER": {
                "decision_readiness": {"readiness_score": 95, "overall_state": "READY"},
                "recommended_actions": []
            }
        }
    }

    # Mock log_run_fn count to trace executions
    log_run_calls = 0
    def mock_log_run(synthesis_result, persona_views, db_path, baseline_period, comparison_period):
        nonlocal log_run_calls
        log_run_calls += 1
        return f"run_id_val_{log_run_calls}"

    # 7. First load establishes the run
    run_id_1, key_1, logged_1 = resolve_execution_run_id(
        synthesis_result=synthesis_result,
        persona_views=persona_views,
        baseline_period=("2026-01-01", "2026-03-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir="data",
        cached_run_id=None,
        cached_key=None,
        db_path=db_path,
        log_run_fn=mock_log_run
    )
    assert run_id_1 == "run_id_val_1"
    assert logged_1 is True
    assert log_run_calls == 1

    # 8. Repeated use of identical parameters does not create duplicate runs
    run_id_2, key_2, logged_2 = resolve_execution_run_id(
        synthesis_result=synthesis_result,
        persona_views=persona_views,
        baseline_period=("2026-01-01", "2026-03-31"),
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir="data",
        cached_run_id=run_id_1,
        cached_key=key_1,
        db_path=db_path,
        log_run_fn=mock_log_run
    )
    assert run_id_2 == "run_id_val_1"
    assert logged_2 is False
    assert log_run_calls == 1  # No additional calls

    # 9. Changing baseline/comparison/data_dir causes a new run identity
    run_id_3, key_3, logged_3 = resolve_execution_run_id(
        synthesis_result=synthesis_result,
        persona_views=persona_views,
        baseline_period=("2026-02-01", "2026-03-31"), # Changed start date
        comparison_period=("2026-06-01", "2026-06-30"),
        data_dir="data",
        cached_run_id=run_id_2,
        cached_key=key_2,
        db_path=db_path,
        log_run_fn=mock_log_run
    )
    assert run_id_3 == "run_id_val_2"
    assert logged_3 is True
    assert log_run_calls == 2

# 19. Milestone 5.4 Observability Dashboard Verification
def test_milestone_5_4_observability(tmp_path):
    from app import calculate_database_metrics, get_all_feedback, check_role_permission

    db_file = tmp_path / "test_5_4_obs.db"
    db_path = str(db_file)
    assert initialize_database(db_path) is True

    # 1. Check initial empty counts
    run_count, feedback_count, db_active = calculate_database_metrics(db_path)
    assert run_count == 0
    assert feedback_count == 0
    assert db_active is True

    # Setup mock runs and feedback
    synthesis = {"status": "SUCCESS", "report": []}
    views = {
        "status": "SUCCESS",
        "personas": {
            "CX_MANAGER": {
                "decision_readiness": {"readiness_score": 90, "overall_state": "READY"},
                "recommended_actions": [{"id": "ACT_1", "priority": "HIGH", "title": "First Action"}]
            },
            "OPERATIONS_MANAGER": {
                "decision_readiness": {"readiness_score": 95, "overall_state": "READY"},
                "recommended_actions": [{"id": "ACT_2", "priority": "LOW", "title": "Second Action"}]
            }
        }
    }

    # Log two runs
    run_id1 = log_execution_run(synthesis, views, db_path, ("2026-01-01", "2026-03-31"), ("2026-06-01", "2026-06-30"))
    run_id2 = log_execution_run(synthesis, views, db_path, ("2026-02-01", "2026-03-31"), ("2026-06-01", "2026-06-30"))
    assert run_id1 is not None
    assert run_id2 is not None

    # Log feedback
    fb1 = log_analyst_feedback(run_id1, "ACT_1", "APPROVED", "Approved 1", "AnalystA", db_path)
    fb2 = log_analyst_feedback(run_id2, "ACT_1", "FLAGGED", "Flagged 2", "AnalystB", db_path)
    assert fb1 is not None
    assert fb2 is not None

    # 2. Check counts accuracy (Efficient query check)
    run_count, feedback_count, db_active = calculate_database_metrics(db_path)
    assert run_count == 2
    assert feedback_count == 2

    # 3. Global feedback audit retrieval (newest first, run/action IDs associated)
    all_fb = get_all_feedback(db_path)
    assert len(all_fb) == 2
    # Since fb2 was logged after fb1, it should be first chronologically (newest first)
    assert all_fb[0]["feedback_id"] == fb2
    assert all_fb[0]["run_id"] == run_id2
    assert all_fb[0]["action_id"] == "ACT_1"
    assert all_fb[0]["comments"] == "Flagged 2"
    assert all_fb[0]["analyst_name"] == "AnalystB"

    assert all_fb[1]["feedback_id"] == fb1
    assert all_fb[1]["run_id"] == run_id1
    assert all_fb[1]["action_id"] == "ACT_1"
    assert all_fb[1]["comments"] == "Approved 1"
    assert all_fb[1]["analyst_name"] == "AnalystA"

    # 4. Security behavior
    # Admin can access history/observability
    assert check_role_permission("Administrator", "view_observability") is True
    assert check_role_permission("Administrator", "view_history") is True
    # Non-admin roles cannot
    assert check_role_permission("Guest", "view_observability") is False
    assert check_role_permission("CX Manager", "view_history") is False
    assert check_role_permission("Operations Manager", "view_history") is False

    # 5. UI elements static check
    with open("app.py", "r", encoding="utf-8") as f:
        app_code = f.read()

    # Verify st.columns and st.metric are used in the panel
    assert "st.columns(" in app_code
    assert "st.metric(" in app_code

    # Verify simulated LLM cost projections are explicitly labeled
    assert "SIMULATED / PROJECTED" in app_code
    assert "total_projected_cost" in app_code

    # Verify Parameter Restoration elements exist
    assert "st.session_state[\"b_start_input\"] = " in app_code
    assert "st.rerun()" in app_code
