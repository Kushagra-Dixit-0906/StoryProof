import sys
from src.engine.synthesis import generate_synthesis_report
from src.engine.personas import generate_persona_views
from src.engine.readiness import evaluate_decision_readiness

def main():
    data_dir = "data"
    
    # 1. Run synthesis report
    print("Running synthesis report...")
    synthesis_result = generate_synthesis_report(data_dir)
    if synthesis_result.get("status") != "SUCCESS":
        print(f"Error: Synthesis generation failed. Reason: {synthesis_result.get('reason')}")
        sys.exit(1)
        
    # 2. Run persona views (which additively includes readiness evaluations)
    print("Running persona narrative engine...")
    persona_result = generate_persona_views(synthesis_result)
    if persona_result.get("status") != "SUCCESS":
        print(f"Error: Persona generation failed. Reason: {persona_result.get('reason')}")
        sys.exit(1)
        
    personas = persona_result["personas"]
    cx = personas["CX_MANAGER"]
    ops = personas["OPERATIONS_MANAGER"]

    # 3. Print formatted output
    print("\n============================================================")
    print("STORYPROOF DECISION READINESS DASHBOARD - MILESTONE 4.2")
    print("============================================================\n")

    # CX Manager Readiness
    cx_dr = cx["decision_readiness"]
    print("PERSONA: CX MANAGER READINESS")
    print("------------------------------------------------------------")
    print(f"Overall State:     {cx_dr.get('overall_state')}")
    print(f"Readiness Score:   {cx_dr.get('readiness_score')} / 100")
    print("Active Flags:")
    for flag_name, active in cx_dr.get("flags", {}).items():
        status_str = "[TRIGGERED]" if active else "[CLEAN]"
        print(f"  - {flag_name:28}: {status_str}")
    print("Details:")
    print(f"  - Insufficient History: {cx_dr.get('details', {}).get('insufficient_history_metrics')}")
    print(f"  - Confounding Risks:    {cx_dr.get('details', {}).get('confounding_explanations')}")
    print(f"  - Metric Tensions:      {cx_dr.get('details', {}).get('tensions')}")
    print(f"  - Unverified Metrics:   {cx_dr.get('details', {}).get('unverified_metrics')}")
    print(f"Recommendation:    {cx_dr.get('recommendation')}\n")

    # Operations Manager Readiness
    ops_dr = ops["decision_readiness"]
    print("PERSONA: OPERATIONS MANAGER READINESS")
    print("------------------------------------------------------------")
    print(f"Overall State:     {ops_dr.get('overall_state')}")
    print(f"Readiness Score:   {ops_dr.get('readiness_score')} / 100")
    print("Active Flags:")
    for flag_name, active in ops_dr.get("flags", {}).items():
        status_str = "[TRIGGERED]" if active else "[CLEAN]"
        print(f"  - {flag_name:28}: {status_str}")
    print("Details:")
    print(f"  - Insufficient History: {ops_dr.get('details', {}).get('insufficient_history_metrics')}")
    print(f"  - Confounding Risks:    {ops_dr.get('details', {}).get('confounding_explanations')}")
    print(f"  - Metric Tensions:      {ops_dr.get('details', {}).get('tensions')}")
    print(f"  - Unverified Metrics:   {ops_dr.get('details', {}).get('unverified_metrics')}")
    print(f"Recommendation:    {ops_dr.get('recommendation')}\n")

    # Disclaimer
    print("CAUSALITY DISCLAIMER:")
    print(cx_dr.get("causality_disclaimer"))
    print("============================================================")

if __name__ == "__main__":
    main()
