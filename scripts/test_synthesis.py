import os
import sys
from src.engine.synthesis import generate_synthesis_report

DATA_DIR = "data"
CONFIG_PATH = "config/evidence_sources.yaml"
KPI_CONFIG_PATH = "config/kpi_definitions.yaml"

def main():
    print("=============================================================")
    print("STORYPROOF NARRATIVE SYNTHESIS REPORT — 3C.3")
    print("=============================================================\n")
    
    res = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    if res["status"] != "SUCCESS":
        print(f"Failed to generate report: {res.get('reason')}")
        sys.exit(1)
        
    report = res["report"]
    for sec in report:
        print(f"SECTION: {sec['title']}")
        print("-" * 60)
        for i, s in enumerate(sec["statements"], 1):
            print(f"Statement {i}:")
            print(f"  Text:           {s['text']}")
            print(f"  Classification: {s['classification']}")
            if s.get("structured_refs"):
                print(f"  Structured Refs: {s['structured_refs']}")
            if s.get("evidence_refs"):
                print(f"  Evidence Refs:   {s['evidence_refs']}")
            print()
        print("=" * 60)
        print()

if __name__ == "__main__":
    main()
