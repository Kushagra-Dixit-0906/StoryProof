import os
import sqlite3
import datetime
import hashlib
import re

def _validate_iso_date(val):
    """
    Helper to check if a value is a valid ISO date string (YYYY-MM-DD).
    """
    if not isinstance(val, str):
        return False
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", val):
        return False
    try:
        datetime.date.fromisoformat(val)
        return True
    except ValueError:
        return False

def _is_integer_compatible(val):
    """
    Helper to check if a value is integer/numeric compatible.
    Bools are explicitly excluded.
    """
    if isinstance(val, bool):
        return False
    if isinstance(val, (int, float)):
        return True
    if isinstance(val, str):
        try:
            float(val)
            return True
        except ValueError:
            return False
    return False

def initialize_database(db_path="data/storyproof_audit.db"):
    """
    Initializes the SQLite audit database and creates execution_runs 
    and analyst_feedback tables if they do not exist.
    
    Returns:
      True on success, False on failure.
    """
    try:
        # Create directory path if it doesn't exist
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()
        
        # Create execution_runs table (including actions_list column)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS execution_runs (
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
                actions_count INTEGER NOT NULL,
                actions_list TEXT
            );
        """)
        
        # Backward-compatibility fallback: alter table to add column if it was created without it
        try:
            cursor.execute("ALTER TABLE execution_runs ADD COLUMN actions_list TEXT;")
        except sqlite3.OperationalError:
            # Column already exists, safe to ignore
            pass
            
        # Create analyst_feedback table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analyst_feedback (
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
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Warning: Database initialization failed at '{db_path}': {e}")
        return False

def log_execution_run(synthesis_result, persona_views, db_path="data/storyproof_audit.db", 
                       baseline_period=None, comparison_period=None):
    """
    Logs metadata about the execution run to the execution_runs table.
    The baseline_period and comparison_period must be explicitly supplied.
    
    Returns:
      A timestamp-bound execution identifier (run_id) on success, or None on failure/abstention.
      The run_id uniquely identifies the execution instant and its content payload.
    """
    # 1. Period supply validation
    if baseline_period is None or comparison_period is None:
        return None
    if not isinstance(baseline_period, (list, tuple)) or len(baseline_period) != 2:
        return None
    if not isinstance(comparison_period, (list, tuple)) or len(comparison_period) != 2:
        return None
        
    if not _validate_iso_date(baseline_period[0]) or not _validate_iso_date(baseline_period[1]):
        return None
    if not _validate_iso_date(comparison_period[0]) or not _validate_iso_date(comparison_period[1]):
        return None

    # 2. Schema validation of upstream data structures
    if synthesis_result is None or not isinstance(synthesis_result, dict) or synthesis_result.get("status") != "SUCCESS":
        return None
    if "report" not in synthesis_result:
        return None
        
    if persona_views is None or not isinstance(persona_views, dict) or persona_views.get("status") != "SUCCESS":
        return None
    if "personas" not in persona_views or not isinstance(persona_views["personas"], dict):
        return None

    try:
        # Extract and validate readiness payloads
        cx_persona = persona_views["personas"].get("CX_MANAGER")
        ops_persona = persona_views["personas"].get("OPERATIONS_MANAGER")
        
        if not isinstance(cx_persona, dict) or not isinstance(ops_persona, dict):
            return None
            
        cx_dr = cx_persona.get("decision_readiness")
        ops_dr = ops_persona.get("decision_readiness")
        
        if not isinstance(cx_dr, dict) or not isinstance(ops_dr, dict):
            return None
            
        if "readiness_score" not in cx_dr or "readiness_score" not in ops_dr:
            return None
        if "overall_state" not in cx_dr or "overall_state" not in ops_dr:
            return None
            
        cx_score_val = cx_dr.get("readiness_score")
        ops_score_val = ops_dr.get("readiness_score")
        cx_state = cx_dr.get("overall_state")
        ops_state = ops_dr.get("overall_state")
        
        if not _is_integer_compatible(cx_score_val) or not _is_integer_compatible(ops_score_val):
            return None
        if not isinstance(cx_state, str) or not cx_state:
            return None
        if not isinstance(ops_state, str) or not ops_state:
            return None
            
        cx_score = int(float(cx_score_val))
        ops_score = int(float(ops_score_val))
        
        # Validate and count total recommended actions
        cx_actions = cx_persona.get("recommended_actions")
        ops_actions = ops_persona.get("recommended_actions")
        
        if not isinstance(cx_actions, list) or not isinstance(ops_actions, list):
            return None
            
        actions_count = len(cx_actions) + len(ops_actions)
        
        # Verify database initialization success
        if initialize_database(db_path) is not True:
            return None
            
        # Collect generated action IDs for membership validation
        actions_list_data = []
        for act in cx_actions:
            if isinstance(act, dict) and "id" in act:
                actions_list_data.append(str(act["id"]))
        for act in ops_actions:
            if isinstance(act, dict) and "id" in act:
                actions_list_data.append(str(act["id"]))
        actions_list_str = ",".join(actions_list_data)
        
        # Generate timestamp-bound run_id for the specific execution instant
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        hasher = hashlib.sha256()
        hasher.update(f"{timestamp}_{baseline_period[0]}_{comparison_period[0]}_{cx_score}_{ops_score}".encode("utf-8"))
        run_id = hasher.hexdigest()[:16]
        
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO execution_runs (
                run_id, timestamp, baseline_start, baseline_end, 
                comparison_start, comparison_end, 
                cx_readiness_score, cx_readiness_state, 
                ops_readiness_score, ops_readiness_state, 
                actions_count, actions_list
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            run_id, timestamp, baseline_period[0], baseline_period[1],
            comparison_period[0], comparison_period[1],
            cx_score, cx_state,
            ops_score, ops_state,
            actions_count, actions_list_str
        ))
        
        conn.commit()
        conn.close()
        return run_id
    except Exception as e:
        print(f"Warning: Failed to log execution run: {e}")
        return None

def log_analyst_feedback(run_id, action_id, status, comments="", analyst_name="analyst", db_path="data/storyproof_audit.db"):
    """
    Logs human analyst feedback/corrections to the analyst_feedback table.
    Verifies that the action_id belongs to the specified run_id.
    
    Returns:
      feedback_id (str) on success, or None on failure/abstention.
    """
    # Validation constraints
    if not run_id or not action_id or not status:
        return None
    if status not in ["APPROVED", "REJECTED", "FLAGGED"]:
        print(f"Warning: Invalid status '{status}' rejected. Must be APPROVED, REJECTED, or FLAGGED.")
        return None

    # Verify database initialization success
    if initialize_database(db_path) is not True:
        return None

    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()
        
        # Verify run_id exists and retrieve its actions_list
        cursor.execute("SELECT actions_list FROM execution_runs WHERE run_id = ?;", (run_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            print(f"Warning: run_id '{run_id}' not found in database.")
            return None
            
        actions_list_str = row[0]
        valid_actions = actions_list_str.split(",") if actions_list_str else []
        if action_id not in valid_actions:
            conn.close()
            print(f"Warning: action_id '{action_id}' does not belong to run '{run_id}'.")
            return None
            
        # Generate feedback ID
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        hasher = hashlib.sha256()
        hasher.update(f"{timestamp}_{run_id}_{action_id}_{status}".encode("utf-8"))
        feedback_id = hasher.hexdigest()[:16]
        
        cursor.execute("""
            INSERT INTO analyst_feedback (
                feedback_id, run_id, action_id, status, comments, analyst_name, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (feedback_id, run_id, action_id, status, comments, analyst_name, timestamp))
        
        conn.commit()
        conn.close()
        return feedback_id
    except sqlite3.IntegrityError as e:
        print(f"Warning: Integrity constraints failed: {e}")
        return None
    except Exception as e:
        print(f"Warning: Failed to log analyst feedback: {e}")
        return None

def get_run_history(db_path="data/storyproof_audit.db"):
    """
    Queries execution_runs and returns list of dictionaries in reverse chronological order.
    """
    if not os.path.exists(db_path):
        return []
        
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM execution_runs ORDER BY timestamp DESC;")
        rows = cursor.fetchall()
        
        history = [dict(row) for row in rows]
        conn.close()
        return history
    except Exception as e:
        print(f"Warning: Failed to fetch run history: {e}")
        return []

def get_feedback_by_run(run_id, db_path="data/storyproof_audit.db"):
    """
    Queries analyst_feedback for a specific run_id.
    """
    if not os.path.exists(db_path):
        return []
        
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM analyst_feedback WHERE run_id = ? ORDER BY timestamp ASC;", (run_id,))
        rows = cursor.fetchall()
        
        feedback = [dict(row) for row in rows]
        conn.close()
        return feedback
    except Exception as e:
        print(f"Warning: Failed to fetch feedback: {e}")
        return []
