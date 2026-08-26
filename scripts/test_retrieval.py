import os
from src.engine.retrieval import retrieve_evidence

DATA_DIR = "data"
CONFIG_PATH = "config/evidence_sources.yaml"

def print_retrieval_results(scenario_name, query):
    print("=" * 70)
    print(f"SCENARIO: {scenario_name}")
    print("=" * 70)
    print(f"Query Context: {query}")
    print("-" * 70)

    res = retrieve_evidence(query, DATA_DIR, CONFIG_PATH)
    print(f"Status: {res['status']}")
    if res["status"] != "SUCCESS":
        print(f"Reason: {res.get('reason')}")
        print()
        return

    records = res["records"]
    print(f"Retrieved Records Count: {len(records)}")
    print("-" * 70)

    for r in records[:3]:  # Show top 3 matches for readability
        print(f"Evidence ID:    {r['evidence_id']}")
        print(f"Source Key:     {r['source_key']}")
        print(f"Source File:    {r['source_file']}")
        print(f"Evidence Class: {r['evidence_class']}")
        print(f"Relevance Score: {r['relevance_score']:.1f}")
        print(f"Matching Reasons: {', '.join(r['matching_reasons'])}")
        
        # Clean text preview
        text_preview = r['text'].replace("\n", " ")
        if len(text_preview) > 130:
            text_preview = text_preview[:127] + "..."
        print(f"Text Preview:    {text_preview}")
        print("." * 60)
    print()

def main():
    print("=============================================================")
    print("STORYPROOF EVIDENCE RETRIEVAL DEMO RUNNER — 3C.2")
    print("=============================================================\n")

    # Scenario 1: AHT improvement + AI rollout evidence
    query_1 = {
        "kpi": "AHT",
        "hypothesis": "AI rollout",
        "periods": [("2026-04-01", "2026-06-30")]
    }
    print_retrieval_results("AHT Improvement & AI Rollout Investigation", query_1)

    # Scenario 2: CSAT decline + customer feedback
    query_2 = {
        "kpi": "CSAT",
        "customer_segment": "Mid-Market",
        "periods": [("2026-04-01", "2026-06-30")]
    }
    print_retrieval_results("CSAT Decline & Mid-Market Customer Reviews", query_2)

    # Scenario 3: CRM Cloud patch hypothesis
    query_3 = {
        "kpi": "AHT",
        "product": "CRM Cloud",
        "hypothesis": "CRM patch",
        "periods": [("2026-05-01", "2026-06-30")]
    }
    print_retrieval_results("CRM Cloud Patch Bug & AHT Deterioration Context", query_3)

    # Scenario 4: Repeat Contact Rate + resolution complaints
    query_4 = {
        "kpi": "Repeat_Contact_Rate",
        "hypothesis": "AI rollout",
        "periods": [("2026-04-01", "2026-06-30")]
    }
    print_retrieval_results("Repeat Contact Rate Spike & AI Rollout", query_4)

    # Scenario 5: No-match example
    query_5 = {
        "kpi": "NonexistentKPI",
        "product": "Core ERP",
        "customer_segment": "SMB"
    }
    print_retrieval_results("No-Match Behavior / Nonexistent Query Context", query_5)

    # Scenario 6: Provenance output demonstration
    query_6 = {
        "kpi": "FCR",
        "periods": [("2026-04-01", "2026-04-30")]
    }
    print_retrieval_results("Provenance Ingestion & FCR Records", query_6)

    print("=============================================================")

if __name__ == "__main__":
    main()
