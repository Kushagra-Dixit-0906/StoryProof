import os
import sys
from src.engine.evidence import ingest_evidence

DATA_DIR = "data"
CONFIG_PATH = "config/evidence_sources.yaml"

def print_record_sample(rec):
    print(f"Evidence ID: {rec['evidence_id']}")
    print(f"Source:      {rec['source_key']} ({rec['source_name']})")
    print(f"Date:        {rec['date']}")
    if rec.get("customer_segment"):
        print(f"Segment:     {rec['customer_segment']}")
    if rec.get("product"):
        print(f"Product:     {rec['product']}")
    
    # Clean preview (e.g. truncate and keep on single line or clean paragraph)
    preview = rec['text'].replace("\n", " ")
    if len(preview) > 120:
        preview = preview[:117] + "..."
    print(f"Text:        {preview}")
    print("-" * 60)

def main():
    print("============================================================")
    print("STORYPROOF EVIDENCE INGESTION — 3C.1")
    print("============================================================")
    
    sources = ["support_transcripts", "customer_feedback", "rollout_report"]
    all_records = []
    
    for src in sources:
        res = ingest_evidence(src, DATA_DIR, CONFIG_PATH)
        print(f"SOURCE: {src}")
        print(f"Status: {res['status']}")
        print(f"Evidence records: {len(res['records'])}")
        print()
        if res["status"] == "SUCCESS":
            all_records.extend(res["records"])
            
    print("-" * 60)
    print("PROVENANCE CHECK")
    print("-" * 60)
    
    # Provenance validation
    all_valid = True
    for rec in all_records:
        prov = rec.get("provenance")
        if not prov or "file" not in prov or "source_key" not in prov:
            all_valid = False
            break
        if prov["source_key"] != rec["source_key"] or prov["file"] != rec["source_path"]:
            all_valid = False
            break
            
    prov_str = "YES" if all_valid and len(all_records) > 0 else "NO"
    print(f"All evidence records have valid source provenance: {prov_str}")
    print()

    print("-" * 60)
    print("SAMPLE RECORDS")
    print("-" * 60)
    
    # Print a few samples across sources
    # Support transcript sample
    transcripts = [r for r in all_records if r["source_key"] == "support_transcripts"]
    if transcripts:
        print_record_sample(transcripts[0])
        
    # Feedback sample
    feedback = [r for r in all_records if r["source_key"] == "customer_feedback"]
    if feedback:
        print_record_sample(feedback[0])
        
    # Rollout report sample
    report = [r for r in all_records if r["source_key"] == "rollout_report"]
    if len(report) > 3:
        # Print Executive Summary or CRM Cloud Patch section (usually index 1 and 3/4)
        print_record_sample(report[1])  # Executive Summary
        # Find CRM Cloud patch record
        crm_patch = [r for r in report if r["product"] == "CRM Cloud"]
        if crm_patch:
            print_record_sample(crm_patch[0])
            
    print("============================================================")

if __name__ == "__main__":
    main()
