import os
import sys
from src.engine.synthesis import generate_synthesis_report
from src.engine.personas import generate_persona_views
from src.feedback.handler import (
    log_execution_run,
    log_analyst_feedback,
    get_run_history,
    get_feedback_by_run
)

def main():
    data_dir = "data"
    temp_db_path = "data/storyproof_audit_temp.db"
    
    # Explicitly supply reporting periods
    baseline_period = ("2026-01-01", "2026-03-31")
    comparison_period = ("2026-06-01", "2026-06-30")
    
    # Clean up temp db if it already exists
    if os.path.exists(temp_db_path):
        try:
            os.remove(temp_db_path)
        except Exception as e:
            print(f"Warning: Could not remove old temp database: {e}")

    print("Running synthesis report...")
    synthesis_result = generate_synthesis_report(data_dir, baseline_period=baseline_period, comparison_period=comparison_period)
    if synthesis_result.get("status") != "SUCCESS":
        print(f"Error: Synthesis failed. Reason: {synthesis_result.get('reason')}")
        sys.exit(1)

    print("Running persona views & action engine...")
    persona_result = generate_persona_views(synthesis_result)
    if persona_result.get("status") != "SUCCESS":
        print(f"Error: Persona generation failed. Reason: {persona_result.get('reason')}")
        sys.exit(1)

    # 1. Log execution run to temporary DB (with explicit periods)
    print(f"\n[AUDIT] Logging execution run to '{temp_db_path}'...")
    run_id = log_execution_run(synthesis_result, persona_result, db_path=temp_db_path, 
                               baseline_period=baseline_period, comparison_period=comparison_period)
    if not run_id:
        print("Error: Failed to log execution run.")
        sys.exit(1)
    print(f"[AUDIT] Run successfully logged. Assigned Run ID: {run_id}")

    # 2. Extract one action to give mock feedback on
    cx_persona = persona_result["personas"].get("CX_MANAGER", {})
    cx_actions = cx_persona.get("recommended_actions", [])
    
    target_action_id = "ACT_CX_MANAGER_PATCH_CSAT"
    # Fallback to first CX action if the target is not found
    if not any(a["id"] == target_action_id for a in cx_actions) and cx_actions:
        target_action_id = cx_actions[0]["id"]
        
    print(f"\n[FEEDBACK] Simulating human analyst feedback on action: '{target_action_id}'")
    feedback_id = log_analyst_feedback(
        run_id=run_id,
        action_id=target_action_id,
        status="APPROVED",
        comments="Verified with customer survey feedback transcripts.",
        analyst_name="Senior Analyst",
        db_path=temp_db_path
    )
    if not feedback_id:
        print("Error: Failed to log analyst feedback.")
        sys.exit(1)
    print(f"[FEEDBACK] Feedback recorded. Feedback ID: {feedback_id}")

    # 3. Retrieve and print history
    print("\n============================================================")
    print("STORYPROOF AUDIT TRAIL LOGS")
    print("============================================================\n")
    
    history = get_run_history(temp_db_path)
    print(f"Total Execution Runs in DB: {len(history)}")
    for r in history:
        print(f"\nRun ID:             {r.get('run_id')}")
        print(f"Timestamp:          {r.get('timestamp')}")
        print(f"Baseline Period:    {r.get('baseline_start')} to {r.get('baseline_end')}")
        print(f"Comparison Period:  {r.get('comparison_start')} to {r.get('comparison_end')}")
        print(f"CX Readiness:       Score {r.get('cx_readiness_score')} ({r.get('cx_readiness_state')})")
        print(f"Ops Readiness:      Score {r.get('ops_readiness_score')} ({r.get('ops_readiness_state')})")
        print(f"Actions Generated:  {r.get('actions_count')}")

        # Fetch feedback comments for this run
        comments = get_feedback_by_run(r.get('run_id'), temp_db_path)
        if comments:
            print("\n  Analyst Feedback Corrections:")
            for c in comments:
                print(f"    - Action ID:    {c.get('action_id')}")
                print(f"      Status:       {c.get('status')}")
                print(f"      Comments:     {c.get('comments')}")
                print(f"      Analyst:      {c.get('analyst_name')}")
                print(f"      Submitted:    {c.get('timestamp')}")
        else:
            print("\n  Analyst Feedback Corrections: None logged.")

    print("\n============================================================")

    # 4. Clean up temporary database
    print(f"\nCleaning up temp database file '{temp_db_path}'...")
    if os.path.exists(temp_db_path):
        try:
            os.remove(temp_db_path)
            print("Temp database removed successfully.")
        except Exception as e:
            print(f"Warning: Could not remove temp database: {e}")

if __name__ == "__main__":
    main()
