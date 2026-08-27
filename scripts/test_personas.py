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
        
    # 2. Run persona views
    print("Running persona narrative engine...")
    persona_result = generate_persona_views(synthesis_result)
    if persona_result.get("status") != "SUCCESS":
        print(f"Error: Persona generation failed. Reason: {persona_result.get('reason')}")
        sys.exit(1)
        
    personas = persona_result["personas"]
    cx = personas["CX_MANAGER"]
    ops = personas["OPERATIONS_MANAGER"]

    # 3. Print formatted output
    print("============================================================\n"
          "STORYPROOF PERSONA NARRATIVE ENGINE — 4.1\n"
          "============================================================\n")

    # CX Manager
    print("PERSONA: CX MANAGER\n"
          "------------------------------------------------------------")
    print(f"Priority: {', '.join(cx['priority'])}")
    print(f"Summary: {cx['summary']}")
    print("Key Findings:")
    for f in cx["key_findings"]:
        print(f"  - [{f['classification']}] {f['text']}")
        print(f"    Structured Refs: {f['structured_refs']}")
        print(f"    Evidence Refs: {f['evidence_refs']}")
    print("Risks:")
    for r in cx["risks"]:
        print(f"  - [{r['classification']}] {r['text']}")
        print(f"    Structured Refs: {r['structured_refs']}")
        print(f"    Evidence Refs: {r['evidence_refs']}")
    print(f"Evidence References: {', '.join(cx['evidence_refs'])}")
    print(f"Structured References: {', '.join(cx['structured_refs'])}")
    print(f"Decision Context: {cx['decision_context']}\n")

    # Operations Manager
    print("PERSONA: OPERATIONS MANAGER\n"
          "------------------------------------------------------------")
    print(f"Priority: {', '.join(ops['priority'])}")
    print(f"Summary: {ops['summary']}")
    print("Key Findings:")
    for f in ops["key_findings"]:
        print(f"  - [{f['classification']}] {f['text']}")
        print(f"    Structured Refs: {f['structured_refs']}")
        print(f"    Evidence Refs: {f['evidence_refs']}")
    print("Risks:")
    for r in ops["risks"]:
        print(f"  - [{r['classification']}] {r['text']}")
        print(f"    Structured Refs: {r['structured_refs']}")
        print(f"    Evidence Refs: {r['evidence_refs']}")
    print(f"Evidence References: {', '.join(ops['evidence_refs'])}")
    print(f"Structured References: {', '.join(ops['structured_refs'])}")
    print(f"Decision Context: {ops['decision_context']}\n")

    # Disclaimer
    print("CAUSALITY DISCLAIMER:\n"
          "The available evidence does not establish causality; observed changes represent associations and candidate explanations only.\n"
          "============================================================")

if __name__ == "__main__":
    main()
