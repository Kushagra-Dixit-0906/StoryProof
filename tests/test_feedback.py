import os
import pytest
import sqlite3
import copy
import datetime
from unittest.mock import patch
from src.feedback.handler import (
    initialize_database,
    log_execution_run,
    log_analyst_feedback,
    get_run_history,
    get_feedback_by_run
)
from src.engine.synthesis import generate_synthesis_report
from src.engine.personas import generate_persona_views

# Default valid periods for testing
DEFAULT_BASELINE = ("2026-01-01", "2026-03-31")
DEFAULT_COMPARISON = ("2026-06-01", "2026-06-30")

# Mock valid synthesis result
def get_mock_synthesis():
    return {
        "status": "SUCCESS",
        "report": [
            {
                "title": "KPI Movement",
                "statements": []
            }
        ]
    }

# Mock valid views result
def get_mock_views():
    return {
        "status": "SUCCESS",
        "personas": {
            "CX_MANAGER": {
                "decision_readiness": {
                    "readiness_score": 85,
                    "overall_state": "READY_WITH_RESERVATIONS"
                },
                "recommended_actions": [
                    {"id": "ACT_CX_1", "priority": "HIGH", "title": "Check CSAT"}
                ]
            },
            "OPERATIONS_MANAGER": {
                "decision_readiness": {
                    "readiness_score": 90,
                    "overall_state": "READY"
                },
                "recommended_actions": [
                    {"id": "ACT_OPS_1", "priority": "MEDIUM", "title": "Establish AHT baseline"}
                ]
            }
        }
    }

# 1. DB Initialization and Table Creation Checks
def test_db_initialization(tmp_path):
    db_file = tmp_path / "test_audit.db"
    db_path = str(db_file)
    
    assert initialize_database(db_path) is True
    assert os.path.exists(db_path)
    
    # Verify tables and columns
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cursor.fetchall()]
    
    cursor.execute("PRAGMA table_info(execution_runs);")
    columns = [col[1] for col in cursor.fetchall()]
    conn.close()
    
    assert "execution_runs" in tables
    assert "analyst_feedback" in tables
    assert "actions_list" in columns

# 2. Abstention when passing invalid synthesis/views result
def test_log_execution_abstention(tmp_path):
    db_path = str(tmp_path / "test_audit.db")
    
    assert log_execution_run(None, None, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON) is None
    
    invalid_syn = {"status": "ERROR", "report": []}
    valid_views = get_mock_views()
    assert log_execution_run(invalid_syn, valid_views, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON) is None
    
    valid_syn = get_mock_synthesis()
    invalid_views = {"status": "ERROR"}
    assert log_execution_run(valid_syn, invalid_views, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON) is None

# 3. Log execution run succeeds
def test_log_execution_run_success(tmp_path):
    db_path = str(tmp_path / "test_audit.db")
    
    syn = get_mock_synthesis()
    views = get_mock_views()
    
    run_id = log_execution_run(syn, views, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON)
    assert run_id is not None
    assert len(run_id) == 16
    
    # Check values in DB
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM execution_runs WHERE run_id = ?;", (run_id,))
    row = dict(cursor.fetchone())
    conn.close()
    
    assert row["cx_readiness_score"] == 85
    assert row["cx_readiness_state"] == "READY_WITH_RESERVATIONS"
    assert row["ops_readiness_score"] == 90
    assert row["ops_readiness_state"] == "READY"
    assert row["actions_count"] == 2
    assert "ACT_CX_1" in row["actions_list"]
    assert "ACT_OPS_1" in row["actions_list"]

# 4. Log analyst feedback succeeds (valid action membership)
def test_log_analyst_feedback_success(tmp_path):
    db_path = str(tmp_path / "test_audit.db")
    
    syn = get_mock_synthesis()
    views = get_mock_views()
    run_id = log_execution_run(syn, views, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON)
    
    feedback_id = log_analyst_feedback(
        run_id=run_id,
        action_id="ACT_CX_1",
        status="APPROVED",
        comments="Approved comment",
        analyst_name="TestAnalyst",
        db_path=db_path
    )
    assert feedback_id is not None
    
    # Verify in DB
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM analyst_feedback WHERE feedback_id = ?;", (feedback_id,))
    row = dict(cursor.fetchone())
    conn.close()
    
    assert row["run_id"] == run_id
    assert row["action_id"] == "ACT_CX_1"
    assert row["status"] == "APPROVED"
    assert row["comments"] == "Approved comment"
    assert row["analyst_name"] == "TestAnalyst"

# 5. Status Validation Constraints Check
def test_log_feedback_invalid_status(tmp_path):
    db_path = str(tmp_path / "test_audit.db")
    
    syn = get_mock_synthesis()
    views = get_mock_views()
    run_id = log_execution_run(syn, views, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON)
    
    # Invalid status should return None
    feedback_id = log_analyst_feedback(
        run_id=run_id,
        action_id="ACT_CX_1",
        status="UNKNOWN_STATUS",
        comments="Hello",
        db_path=db_path
    )
    assert feedback_id is None

# 6. Foreign Key Constraint Enforcement
def test_log_feedback_foreign_key_fails(tmp_path):
    db_path = str(tmp_path / "test_audit.db")
    
    # Ensure database tables exist
    initialize_database(db_path)
    
    # Logging feedback with non-existent run_id must fail
    feedback_id = log_analyst_feedback(
        run_id="NON_EXISTENT_RUN_ID",
        action_id="ACT_CX_1",
        status="APPROVED",
        comments="Hello",
        db_path=db_path
    )
    assert feedback_id is None

# 7. Run History Retrieval
def test_get_run_history(tmp_path):
    db_path = str(tmp_path / "test_audit.db")
    
    syn = get_mock_synthesis()
    views = get_mock_views()
    
    run_id1 = log_execution_run(syn, views, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON)
    run_id2 = log_execution_run(syn, views, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON)
    
    history = get_run_history(db_path)
    assert len(history) == 2
    assert history[0]["run_id"] == run_id2
    assert history[1]["run_id"] == run_id1

# 8. Feedback Retrieval by run_id
def test_get_feedback_by_run(tmp_path):
    db_path = str(tmp_path / "test_audit.db")
    
    syn = get_mock_synthesis()
    views = get_mock_views()
    run_id = log_execution_run(syn, views, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON)
    
    log_analyst_feedback(run_id, "ACT_CX_1", "APPROVED", "C1", db_path=db_path)
    log_analyst_feedback(run_id, "ACT_OPS_1", "FLAGGED", "C2", db_path=db_path)
    
    feedback = get_feedback_by_run(run_id, db_path)
    assert len(feedback) == 2
    assert feedback[0]["action_id"] == "ACT_CX_1"
    assert feedback[0]["status"] == "APPROVED"
    assert feedback[1]["action_id"] == "ACT_OPS_1"
    assert feedback[1]["status"] == "FLAGGED"

# 9. SQL Injection / Special Characters Safety
def test_sql_injection_safety(tmp_path):
    db_path = str(tmp_path / "test_audit.db")
    
    syn = get_mock_synthesis()
    views = get_mock_views()
    run_id = log_execution_run(syn, views, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON)
    
    injection_comment = "'); DROP TABLE analyst_feedback; --"
    feedback_id = log_analyst_feedback(
        run_id=run_id,
        action_id="ACT_CX_1",
        status="APPROVED",
        comments=injection_comment,
        db_path=db_path
    )
    assert feedback_id is not None
    
    # Query database and verify table still exists and comment matches
    history = get_feedback_by_run(run_id, db_path)
    assert len(history) == 1
    assert history[0]["comments"] == injection_comment

# 10. File Absence Gracefulness
def test_database_absence_gracefulness():
    # Calling get functions on non-existent file should return empty list
    non_existent_db = "data/non_existent_path_file_does_not_exist.db"
    if os.path.exists(non_existent_db):
        os.remove(non_existent_db)
        
    assert get_run_history(non_existent_db) == []
    assert get_feedback_by_run("some_run_id", non_existent_db) == []

# ------------------------------------------------------------------------------
# SURGICAL HARDENING TEST CASES (Milestone 4.4 Hardening Pass)
# ------------------------------------------------------------------------------

# 11. Missing baseline period
def test_missing_baseline_period(tmp_path):
    db_path = str(tmp_path / "test_audit.db")
    syn = get_mock_synthesis()
    views = get_mock_views()
    assert log_execution_run(syn, views, db_path, None, DEFAULT_COMPARISON) is None

# 12. Missing comparison period
def test_missing_comparison_period(tmp_path):
    db_path = str(tmp_path / "test_audit.db")
    syn = get_mock_synthesis()
    views = get_mock_views()
    assert log_execution_run(syn, views, db_path, DEFAULT_BASELINE, None) is None

# 13. Malformed period
def test_malformed_period(tmp_path):
    db_path = str(tmp_path / "test_audit.db")
    syn = get_mock_synthesis()
    views = get_mock_views()
    
    # Not list/tuple of length 2
    assert log_execution_run(syn, views, db_path, ("2026-01-01",), DEFAULT_COMPARISON) is None
    assert log_execution_run(syn, views, db_path, DEFAULT_BASELINE, "2026-06-01") is None
    
    # Invalid date strings
    assert log_execution_run(syn, views, db_path, ("2026-01-01", "invalid-date"), DEFAULT_COMPARISON) is None
    assert log_execution_run(syn, views, db_path, DEFAULT_BASELINE, ("2026-06-01", "2026-06-32")) is None

# 14. Initialization failure checks
@patch("src.feedback.handler.initialize_database")
def test_initialization_failure(mock_init, tmp_path):
    db_path = str(tmp_path / "test_audit.db")
    mock_init.return_value = False
    
    syn = get_mock_synthesis()
    views = get_mock_views()
    
    # Verification that None is returned, no exception escapes, and no success is reported
    assert log_execution_run(syn, views, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON) is None
    assert log_analyst_feedback("run123", "act123", "APPROVED", db_path=db_path) is None

# 15. Invalid readiness payload
def test_invalid_readiness_payload(tmp_path):
    db_path = str(tmp_path / "test_audit.db")
    syn = get_mock_synthesis()
    
    # Non-integer compatible score
    views_bad_score = get_mock_views()
    views_bad_score["personas"]["CX_MANAGER"]["decision_readiness"]["readiness_score"] = "invalid_score"
    assert log_execution_run(syn, views_bad_score, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON) is None
    
    # Bool value for score (bool is subclass of int, so needs explicit rejection)
    views_bool_score = get_mock_views()
    views_bool_score["personas"]["CX_MANAGER"]["decision_readiness"]["readiness_score"] = True
    assert log_execution_run(syn, views_bool_score, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON) is None
    
    # Missing score
    views_no_score = get_mock_views()
    del views_no_score["personas"]["CX_MANAGER"]["decision_readiness"]["readiness_score"]
    assert log_execution_run(syn, views_no_score, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON) is None

    # Missing state
    views_no_state = get_mock_views()
    del views_no_state["personas"]["CX_MANAGER"]["decision_readiness"]["overall_state"]
    assert log_execution_run(syn, views_no_state, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON) is None

# 16. Invalid action list
def test_invalid_action_list(tmp_path):
    db_path = str(tmp_path / "test_audit.db")
    syn = get_mock_synthesis()
    
    views_bad_actions = get_mock_views()
    # recommended_actions must be a list
    views_bad_actions["personas"]["CX_MANAGER"]["recommended_actions"] = {"action_id": "ACT_CX_1"}
    assert log_execution_run(syn, views_bad_actions, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON) is None

# 17. Valid action membership
def test_valid_action_membership(tmp_path):
    db_path = str(tmp_path / "test_audit.db")
    syn = get_mock_synthesis()
    views = get_mock_views()
    
    run_id = log_execution_run(syn, views, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON)
    assert run_id is not None
    
    # Valid action belonging to this run
    feedback_id = log_analyst_feedback(run_id, "ACT_CX_1", "APPROVED", "Valid comment", db_path=db_path)
    assert feedback_id is not None

# 18. Invalid action membership
def test_invalid_action_membership(tmp_path):
    db_path = str(tmp_path / "test_audit.db")
    syn = get_mock_synthesis()
    views = get_mock_views()
    
    run_id = log_execution_run(syn, views, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON)
    assert run_id is not None
    
    # Fake action_id not generated in this run
    feedback_id = log_analyst_feedback(run_id, "ACT_FAKE_ACTION", "APPROVED", "Fake action feedback", db_path=db_path)
    assert feedback_id is None

# 19. Fake run ID check
def test_fake_run_id_rejected(tmp_path):
    db_path = str(tmp_path / "test_audit.db")
    syn = get_mock_synthesis()
    views = get_mock_views()
    
    run_id = log_execution_run(syn, views, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON)
    assert run_id is not None
    
    # Fake run_id -> rejected
    feedback_id = log_analyst_feedback("FAKE_RUN_ID", "ACT_CX_1", "APPROVED", "Comment", db_path=db_path)
    assert feedback_id is None

# 20. Run ID semantics/format and repeated executions check
def test_run_id_semantics_and_distinctness(tmp_path):
    db_path = str(tmp_path / "test_audit.db")
    syn = get_mock_synthesis()
    views = get_mock_views()
    
    run_id1 = log_execution_run(syn, views, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON)
    run_id2 = log_execution_run(syn, views, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON)
    
    # Must be string of length 16
    assert isinstance(run_id1, str)
    assert len(run_id1) == 16
    
    # Repeated executions must yield distinct execution IDs (uniqueness behavior)
    assert run_id1 != run_id2

# 21. Real pipeline integration test
def test_real_pipeline_integration(tmp_path):
    db_path = str(tmp_path / "test_audit_temp.db")
    
    # 1. Run synthesis report
    real_syn = generate_synthesis_report("data")
    assert real_syn["status"] == "SUCCESS"
    
    # 2. Run persona views
    real_views = generate_persona_views(real_syn)
    assert real_views["status"] == "SUCCESS"
    
    # 3. Log execution run
    run_id = log_execution_run(real_syn, real_views, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON)
    assert run_id is not None
    
    # 4. Find generated action ID
    cx_persona = real_views["personas"].get("CX_MANAGER", {})
    cx_actions = cx_persona.get("recommended_actions", [])
    assert len(cx_actions) > 0
    action_id = cx_actions[0]["id"]
    
    # 5. Log analyst feedback
    feedback_id = log_analyst_feedback(
        run_id=run_id,
        action_id=action_id,
        status="APPROVED",
        comments="Integration test feedback",
        analyst_name="IntegrationTester",
        db_path=db_path
    )
    assert feedback_id is not None
    
    # 6. Retrieve history and feedback comments
    history = get_run_history(db_path)
    assert len(history) == 1
    assert history[0]["run_id"] == run_id
    
    comments = get_feedback_by_run(run_id, db_path)
    assert len(comments) == 1
    assert comments[0]["action_id"] == action_id
    assert comments[0]["status"] == "APPROVED"
    assert comments[0]["comments"] == "Integration test feedback"

# 22. Database migration test case (Issue Verification)
def test_sqlite_migration_path(tmp_path):
    db_path = str(tmp_path / "migration_test.db")
    
    # 1. Create an OLD-FORMAT database manually (without actions_list column)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE execution_runs (
            run_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            baseline_start TEXT NOT NULL,
            baseline_end TEXT NOT NULL,
            comparison_start TEXT NOT NULL,
            comparison_end TEXT NOT NULL,
            cx_readiness_score INTEGER NOT NULL,
            cx_readiness_state TEXT NOT NULL,
            ops_readiness_score INTEGER NOT NULL,
            ops_readiness_state TEXT NOT NULL,
            actions_count INTEGER NOT NULL
        );
    """)
    cursor.execute("""
        CREATE TABLE analyst_feedback (
            feedback_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            action_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('APPROVED', 'REJECTED', 'FLAGGED')),
            comments TEXT,
            analyst_name TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES execution_runs(run_id)
        );
    """)
    
    # Verify actions_list does not exist initially
    cursor.execute("PRAGMA table_info(execution_runs);")
    cols_pre = [col[1] for col in cursor.fetchall()]
    assert "actions_list" not in cols_pre
    
    # 2. Insert valid row into old-format database
    cursor.execute("""
        INSERT INTO execution_runs (
            run_id, timestamp, baseline_start, baseline_end,
            comparison_start, comparison_end,
            cx_readiness_score, cx_readiness_state,
            ops_readiness_score, ops_readiness_state,
            actions_count
        ) VALUES ('old_run_123', '2026-08-28T00:00:00Z', '2026-01-01', '2026-03-31',
                  '2026-06-01', '2026-06-30', 80, 'READY', 75, 'READY_WITH_RESERVATIONS', 5);
    """)
    conn.commit()
    conn.close()
    
    # 3. Call initialize_database(db_path) to upgrade
    assert initialize_database(db_path) is True
    
    # 4 & 5. Verify actions_list column now exists
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(execution_runs);")
    cols_post = [col[1] for col in cursor.fetchall()]
    assert "actions_list" in cols_post
    
    # 6. Verify pre-existing row and its original values remain intact
    cursor.execute("SELECT * FROM execution_runs WHERE run_id = 'old_run_123';")
    row = cursor.fetchone()
    # Check column counts (should be 12 now)
    assert len(row) == 12
    assert row[0] == 'old_run_123'
    assert row[1] == '2026-08-28T00:00:00Z'
    assert row[6] == 80
    assert row[7] == 'READY'
    assert row[8] == 75
    assert row[9] == 'READY_WITH_RESERVATIONS'
    assert row[10] == 5
    assert row[11] is None  # Newly added column defaults to NULL/None for pre-existing row
    
    conn.close()
    
    # 7 & 8. Verify calling initialize_database(db_path) again is safe/idempotent and no corruption
    assert initialize_database(db_path) is True
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(execution_runs);")
    cols_double = [col[1] for col in cursor.fetchall()]
    assert len(cols_double) == 12
    assert cols_double.count("actions_list") == 1
    conn.close()
    
    # 9. Verify subsequent log_execution_run() works correctly against the upgraded database
    syn = get_mock_synthesis()
    views = get_mock_views()
    new_run_id = log_execution_run(syn, views, db_path, DEFAULT_BASELINE, DEFAULT_COMPARISON)
    assert new_run_id is not None
    assert len(new_run_id) == 16
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM execution_runs WHERE run_id = ?;", (new_run_id,))
    new_row = dict(cursor.fetchone())
    conn.close()
    
    assert new_row["cx_readiness_score"] == 85
    assert new_row["actions_count"] == 2
    assert new_row["actions_list"] == "ACT_CX_1,ACT_OPS_1"

