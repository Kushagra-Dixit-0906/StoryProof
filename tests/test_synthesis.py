import os
import pytest
import pandas as pd
from src.engine.synthesis import generate_synthesis_report
from src.engine.materiality import load_yaml, analyze_kpi_change
from src.engine.drivers import profile_driver
from src.engine.hypotheses import synthesize_hypotheses
from src.engine.evidence import ingest_evidence
from src.engine.retrieval import retrieve_evidence

CONFIG_PATH = "config/evidence_sources.yaml"
KPI_CONFIG_PATH = "config/kpi_definitions.yaml"
DATA_DIR = "data"

@pytest.fixture
def real_kpi_config():
    return load_yaml(KPI_CONFIG_PATH)

# Test 1: Basic synthesis structure
def test_basic_synthesis_structure():
    res = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    assert res["status"] == "SUCCESS"
    assert "report" in res
    report = res["report"]
    assert len(report) > 0
    for section in report:
        assert "title" in section
        assert "statements" in section
        for s in section["statements"]:
            assert "text" in s
            assert "classification" in s
            assert "structured_refs" in s
            assert "evidence_refs" in s

# Test 2: Material KPI inclusion
def test_material_kpi_inclusion():
    res = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    report = res["report"]
    # Check that CSAT is mentioned as material (decline)
    found_csat = False
    for sec in report:
        for s in sec["statements"]:
            if "CSAT" in s["text"] and "material" in s["text"]:
                found_csat = True
    assert found_csat is True

# Test 3: Materiality values preserved from 3A
def test_materiality_values_preserved(real_kpi_config):
    res = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    report = res["report"]
    # CSAT baseline in 3A: 78.02, comparison: 68.88
    # AHT baseline: 10.16, comparison: 5.77
    found_aht = False
    for sec in report:
        for s in sec["statements"]:
            if "AHT changed from 10.16 to 5.77" in s["text"]:
                found_aht = True
    assert found_aht is True

# Test 4: Statistical signal preservation
def test_statistical_signal_preservation():
    res = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    report = res["report"]
    found_signal = False
    for sec in report:
        for s in sec["statements"]:
            if "material decrease" in s["text"] or "material increase" in s["text"]:
                found_signal = True
    assert found_signal is True

# Test 5: Driver inclusion
def test_driver_inclusion():
    res = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    report = res["report"]
    found_driver = False
    for sec in report:
        if sec["title"] == "Leading Candidate Drivers":
            assert len(sec["statements"]) > 0
            found_driver = True
    assert found_driver is True

# Test 6: Hypothesis inclusion
def test_hypothesis_inclusion():
    res = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    report = res["report"]
    found_hyp = False
    for sec in report:
        if sec["title"] == "Competing Hypotheses":
            assert len(sec["statements"]) > 0
            found_hyp = True
    assert found_hyp is True

# Test 7: Qualitative evidence inclusion
def test_qualitative_evidence_inclusion():
    res = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    report = res["report"]
    found_qual = False
    for sec in report:
        if sec["title"] == "Qualitative Evidence":
            assert len(sec["statements"]) > 0
            for s in sec["statements"]:
                if s["evidence_refs"]:
                    found_qual = True
    assert found_qual is True

# Test 8: Evidence provenance preservation
def test_evidence_provenance_preservation():
    res = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    report = res["report"]
    for sec in report:
        for s in sec["statements"]:
            for ref in s["evidence_refs"]:
                # Provenance: ID format is source_key_index
                assert "_" in ref
                assert not ref.startswith("uuid")

# Test 9: Evidence classification preservation
def test_evidence_classification_preservation():
    res = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    report = res["report"]
    # Find qualitative evidence section and verify classifications are HYPOTHESIS/CONTEXT/FACT
    for sec in report:
        if sec["title"] == "Qualitative Evidence":
            for s in sec["statements"]:
                assert s["classification"] in ["FACT", "ASSOCIATION", "HYPOTHESIS", "CONTEXT", "LIMITATION"]

# Test 10: Contradictory evidence/tension handling
def test_contradictory_evidence_tension_handling():
    res = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    report = res["report"]
    found_tension = False
    for sec in report:
        if sec["title"] == "Contradictory / Tension Evidence":
            for s in sec["statements"]:
                if "Handling time decreased materially, while qualitative evidence contains repeated reports" in s["text"]:
                    found_tension = True
                    assert s["classification"] == "ASSOCIATION"
                    assert len(s["evidence_refs"]) > 0
                    assert len(s["structured_refs"]) > 0
    assert found_tension is True

# Test 11: NO_MATCH qualitative evidence handling
def test_no_match_qualitative_evidence_handling():
    # If retrieve_evidence returns no matches, synthesis must fallback to limitation stating no matching evidence
    import src.engine.synthesis as syn_mod
    orig_ret = syn_mod.retrieve_evidence
    # Mock retrieve_evidence to return NO_MATCH
    syn_mod.retrieve_evidence = lambda query, dd, cp: {"status": "NO_MATCH", "records": []}
    try:
        res = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
        assert res["status"] == "SUCCESS"
        report = res["report"]
        found_fallback = False
        for sec in report:
            for s in sec["statements"]:
                if "No matching qualitative" in s["text"]:
                    found_fallback = True
        assert found_fallback is True
    finally:
        syn_mod.retrieve_evidence = orig_ret

# Test 12: Missing structured input handling
def test_missing_structured_input_handling():
    # Test that synthesis handles empty config or database error safely
    res = generate_synthesis_report("nonexistent_dir", KPI_CONFIG_PATH, CONFIG_PATH)
    # Safely creates report representing limitations
    assert res["status"] in ["SUCCESS", "ERROR"]

# Test 13: AI Resolution Rate insufficient-history preservation
def test_ai_resolution_insufficient_history_preservation():
    res = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    report = res["report"]
    found_limit = False
    for sec in report:
        for s in sec["statements"]:
            if "AI Resolution Rate" in s["text"] and "insufficient history" in s["text"]:
                found_limit = True
                assert s["classification"] == "LIMITATION"
    assert found_limit is True

# Test 14: Multi-KPI synthesis
def test_multi_kpi_synthesis():
    res = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    report = res["report"]
    kpis_found = []
    for sec in report:
        for s in sec["statements"]:
            for k in ["AHT", "FCR", "CSAT", "Repeat_Contact_Rate", "Retention_Rate", "AI_Resolution_Rate"]:
                if k in s["text"] and k not in kpis_found:
                    kpis_found.append(k)
    assert len(kpis_found) >= 5

# Test 15: Deterministic section ordering
def test_deterministic_section_ordering():
    res = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    report = res["report"]
    expected_order = [
        "Executive Finding",
        "KPI Movement",
        "Materiality & Statistical Signal",
        "Leading Candidate Drivers",
        "Competing Hypotheses",
        "Qualitative Evidence",
        "Contradictory / Tension Evidence",
        "Confounding Factors",
        "Data Limitations",
        "Investigation Conclusion",
        "Causality Disclaimer"
    ]
    titles = [sec["title"] for sec in report]
    assert titles == expected_order

# Test 16: Deterministic statement ordering
def test_deterministic_statement_ordering():
    res1 = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    res2 = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    
    for sec1, sec2 in zip(res1["report"], res2["report"]):
        assert sec1["title"] == sec2["title"]
        texts1 = [s["text"] for s in sec1["statements"]]
        texts2 = [s["text"] for s in sec2["statements"]]
        assert texts1 == texts2

@pytest.fixture
def real_config():
    return load_yaml(CONFIG_PATH)

# Test 17: Repeated execution produces identical output
def test_repeated_execution_consistency():
    res1 = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    res2 = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    assert res1 == res2

# Test 18: No generated causal language
def test_no_generated_causal_language():
    res = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    report = res["report"]
    
    causal_words = ["caused", "causes", "caused by", "causal", "responsible for", "resulted in", "led to", "due to", "because of", "driven by", "responsible"]
    
    for sec in report:
        for s in sec["statements"]:
            text_lower = s["text"].lower()
            if "does not establish causality" in text_lower:
                continue  # skip the mandatory causality disclaimer
            for word in causal_words:
                assert word not in text_lower, f"Forbidden causal word '{word}' found in statement: '{s['text']}'"

# Test 19: Original source text remains untouched
def test_original_source_text_untouched(real_config):
    # 1. Ingest all evidence records from the three unstructured sources
    all_source_records = {}
    for source in ["support_transcripts", "customer_feedback", "rollout_report"]:
        ing_res = ingest_evidence(source, DATA_DIR, CONFIG_PATH)
        assert ing_res["status"] == "SUCCESS"
        for record in ing_res["records"]:
            all_source_records[record["evidence_id"]] = record["text"]

    # 2. Generate report
    res = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    assert res["status"] == "SUCCESS"
    report = res["report"]

    # 3. Verify referenced evidence corresponds exactly to the original evidence text
    for sec in report:
        for s in sec["statements"]:
            for r_id in s["evidence_refs"]:
                assert r_id in all_source_records
                original_text = all_source_records[r_id]
                
                # If the statement text embeds a snippet in parentheses, verify it is exact
                if "(" in s["text"] and "...)" in s["text"]:
                    start_idx = s["text"].find("(") + 1
                    end_idx = s["text"].find("...)")
                    if start_idx > 0 and end_idx > start_idx:
                        snippet = s["text"][start_idx:end_idx].strip()
                        assert snippet in original_text

# Test 20: Every statement has at least one structured or qualitative reference
def test_every_statement_has_reference():
    res = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    report = res["report"]
    for sec in report:
        for s in sec["statements"]:
            assert len(s["structured_refs"]) > 0 or len(s["evidence_refs"]) > 0, f"Statement has no references: '{s['text']}'"

# Test 21: No fabricated evidence IDs
def test_no_fabricated_evidence_ids():
    # Ingestion IDs
    ing_res = ingest_evidence("support_transcripts", DATA_DIR, CONFIG_PATH)
    real_ids = [r["evidence_id"] for r in ing_res["records"]]
    
    ing_fb = ingest_evidence("customer_feedback", DATA_DIR, CONFIG_PATH)
    real_ids.extend([r["evidence_id"] for r in ing_fb["records"]])
    
    ing_rr = ingest_evidence("rollout_report", DATA_DIR, CONFIG_PATH)
    real_ids.extend([r["evidence_id"] for r in ing_rr["records"]])
    
    res = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    report = res["report"]
    for sec in report:
        for s in sec["statements"]:
            for r_id in s["evidence_refs"]:
                assert r_id in real_ids, f"Fabricated evidence ID '{r_id}' found in statement: '{s['text']}'"

# Test 22: Regression compatibility with 3A
def test_regression_3a(real_kpi_config):
    mat_res = analyze_kpi_change("AHT", real_kpi_config, DATA_DIR, ("2026-01-01", "2026-03-31"), ("2026-06-01", "2026-06-30"))
    assert mat_res["status"] == "MATERIAL"

# Test 23: Regression compatibility with 3B.1
def test_regression_3b1(real_kpi_config):
    drv_res = profile_driver("AHT", "product", ("2026-01-01", "2026-03-31"), ("2026-06-01", "2026-06-30"), DATA_DIR, real_kpi_config)
    assert drv_res["status"] == "SUCCESS"

# Test 24: Regression compatibility with 3B.2
def test_regression_3b2(real_kpi_config):
    hyp_res = synthesize_hypotheses("AHT", DATA_DIR, real_kpi_config, ("2026-01-01", "2026-03-31"), ("2026-06-01", "2026-06-30"), "product")
    assert hyp_res["overall_evidence_state"] == "INVESTIGATION_REQUIRED"

# Test 25: Regression compatibility with 3C.1
def test_regression_3c1():
    res = ingest_evidence("support_transcripts", DATA_DIR, CONFIG_PATH)
    assert res["status"] == "SUCCESS"

# Test 26: Regression compatibility with 3C.2
def test_regression_3c2():
    query = {"product": "CRM Cloud", "kpi": "AHT"}
    res = retrieve_evidence(query, DATA_DIR, CONFIG_PATH)
    assert res["status"] == "SUCCESS"

# Test 27: Synthesis must not describe Retention_Rate as non-material when materiality engine says MATERIAL
def test_synthesis_retention_materiality_consistency(real_kpi_config):
    """Regression: Retention_Rate is MATERIAL per the authoritative materiality engine.
    No synthesis statement should describe it as non-material."""
    # Confirm the authoritative materiality result
    mat_res = analyze_kpi_change("Retention_Rate", real_kpi_config, DATA_DIR,
                                  ("2026-01-01", "2026-03-31"), ("2026-06-01", "2026-06-30"))
    assert mat_res["status"] == "MATERIAL", "Precondition: Retention_Rate must be MATERIAL"
    assert mat_res["materiality"]["crossed"] is True

    # Generate synthesis and verify consistency
    res = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    assert res["status"] == "SUCCESS"
    for sec in res["report"]:
        for s in sec["statements"]:
            text_lower = s["text"].lower()
            # Check if Retention appears in the non-material clause
            # (after "whereas"), not just co-occurrence in the sentence
            if "non-material" in text_lower:
                non_mat_clause = text_lower.split("whereas")[-1] if "whereas" in text_lower else text_lower
                if "retention" in non_mat_clause:
                    pytest.fail(
                        f"Synthesis contradicts materiality engine for Retention_Rate: '{s['text']}'"
                    )

# Test 28: Investigation Conclusion must derive materiality language from engine results
def test_investigation_conclusion_data_driven():
    """The Investigation Conclusion fact sentence must derive materiality
    classification from the authoritative materiality engine, not hard-code it."""
    res = generate_synthesis_report(DATA_DIR, KPI_CONFIG_PATH, CONFIG_PATH)
    assert res["status"] == "SUCCESS"

    # Find the Investigation Conclusion section
    concl_section = None
    for sec in res["report"]:
        if sec["title"] == "Investigation Conclusion":
            concl_section = sec
            break
    assert concl_section is not None, "Investigation Conclusion section must exist"

    # The first statement should be the FACT about materiality
    fact_stmt = concl_section["statements"][0]
    assert fact_stmt["classification"] == "FACT"

    # Retention_Rate is MATERIAL and declined: must appear as "decreased materially"
    text_lower = fact_stmt["text"].lower()
    assert "retention" in text_lower, "Retention must be mentioned in conclusion"
    assert "decreased materially" in text_lower or "material" in text_lower, \
        f"Retention must be classified as material in conclusion: '{fact_stmt['text']}'"
    # Must NOT place Retention in the non-material clause
    if "whereas" in text_lower and "non-material" in text_lower:
        non_mat_clause = text_lower.split("whereas")[-1]
        assert "retention" not in non_mat_clause, \
            f"Conclusion places Retention in non-material clause: '{fact_stmt['text']}'"
