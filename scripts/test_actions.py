import sys
from src.engine.synthesis import generate_synthesis_report
from src.engine.personas import generate_persona_views

def main():
    data_dir = "data"
    
    # 1. Run synthesis report
    print("Running synthesis report...")
    synthesis_result = generate_synthesis_report(data_dir)
    if synthesis_result.get("status") != "SUCCESS":
        print(f"Error: Synthesis generation failed. Reason: {synthesis_result.get('reason')}")
        sys.exit(1)
        
    # 2. Run persona views (which additively includes recommended actions)
    print("Running persona narrative engine...")
    persona_result = generate_persona_views(synthesis_result)
    if persona_result.get("status") != "SUCCESS":
        print(f"Error: Persona generation failed. Reason: {persona_result.get('reason')}")
        sys.exit(1)
        
    personas = persona_result["personas"]
    
    print("\n============================================================")
    print("STORYPROOF ACTION RECOMMENDATION ENGINE - MILESTONE 4.3")
    print("============================================================\n")

    for persona_name in ["CX_MANAGER", "OPERATIONS_MANAGER"]:
        payload = personas[persona_name]
        actions = payload.get("recommended_actions", [])
        
        print(f"PERSONA: {persona_name.replace('_', ' ')}")
        print("------------------------------------------------------------")
        print(f"Total Recommended Actions: {len(actions)}")
        
        for idx, act in enumerate(actions, 1):
            print(f"\nAction {idx}: [{act.get('priority')}] {act.get('title')}")
            print(f"  - ID:                 {act.get('id')}")
            print(f"  - Type:               {act.get('action_type')}")
            print(f"  - Observed Finding:   {act.get('observed_finding')}")
            print(f"  - Reason:             {act.get('reason')}")
            print(f"  - Justification:      {act.get('justification')}")
            print(f"  - Structured Refs:    {act.get('structured_refs')}")
            print(f"  - Evidence Refs:      {act.get('evidence_refs')}")
            print(f"  - Trigger Info:       {act.get('trigger_info')}")
            
        print("\n------------------------------------------------------------\n")

    # Disclaimer
    cx_dr = personas["CX_MANAGER"].get("decision_readiness", {})
    print("CAUSALITY DISCLAIMER:")
    print(cx_dr.get("causality_disclaimer", "The available evidence does not establish causality; observed changes represent associations and candidate explanations only."))
    print("============================================================")

if __name__ == "__main__":
    main()
