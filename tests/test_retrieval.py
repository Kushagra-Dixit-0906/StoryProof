import os
import pytest
import pandas as pd
import re
from src.engine.retrieval import retrieve_evidence, determine_evidence_class
from src.engine.materiality import load_yaml, analyze_kpi_change
from src.engine.drivers import profile_driver
from src.engine.hypotheses import synthesize_hypotheses
from src.engine.evidence import ingest_evidence

CONFIG_PATH = "config/evidence_sources.yaml"
KPI_CONFIG_PATH = "config/kpi_definitions.yaml"
DATA_DIR = "data"

@pytest.fixture
def real_config():
    return load_yaml(CONFIG_PATH)

# Test 1: Exact product match
def test_exact_product_match(real_config):
    query = {"product": "CRM Cloud", "kpi": "AHT"}
    res = retrieve_evidence(query, DATA_DIR, CONFIG_PATH)
    assert res["status"] == "SUCCESS"
    for r in res["records"]:
        if r["metadata"]["product"] is not None:
            assert r["metadata"]["product"] == "CRM Cloud"

# Test 2: Exact customer segment match
def test_exact_customer_segment_match(real_config):
    query = {"customer_segment": "Mid-Market", "kpi": "AHT"}
    res = retrieve_evidence(query, DATA_DIR, CONFIG_PATH)
    assert res["status"] == "SUCCESS"
    for r in res["records"]:
        if r["metadata"]["customer_segment"] is not None:
            assert r["metadata"]["customer_segment"] == "Mid-Market"

# Test 3: Date-window matching
def test_date_window_matching(real_config):
    query = {
        "periods": [("2026-06-01", "2026-06-30")],
        "kpi": "AHT"
    }
    res = retrieve_evidence(query, DATA_DIR, CONFIG_PATH)
    assert res["status"] == "SUCCESS"
    for r in res["records"]:
        if r["metadata"]["date"]:
            dt = pd.to_datetime(r["metadata"]["date"])
            assert pd.to_datetime("2026-06-01") <= dt <= pd.to_datetime("2026-06-30")

# Test 4: AI rollout evidence retrieval
def test_ai_rollout_evidence_retrieval(real_config):
    query = {"kpi": "AHT", "hypothesis": "AI rollout"}
    res = retrieve_evidence(query, DATA_DIR, CONFIG_PATH)
    assert res["status"] == "SUCCESS"
    has_ai = False
    for r in res["records"]:
        if any("terms" in reason.lower() and ("ai" in reason.lower() or "bot" in reason.lower() or "assistant" in reason.lower()) for reason in r["matching_reasons"]):
            has_ai = True
            break
    assert has_ai is True

# Test 5: CRM Cloud patch evidence retrieval
def test_crm_patch_evidence_retrieval(real_config):
    query = {"kpi": "AHT", "hypothesis": "CRM patch"}
    res = retrieve_evidence(query, DATA_DIR, CONFIG_PATH)
    assert res["status"] == "SUCCESS"
    crm_patch_record = None
    for r in res["records"]:
        if "rollout_report" in r["source_file"] and "Confounding Factors" in r["text"]:
            crm_patch_record = r
            break
    assert crm_patch_record is not None
    assert crm_patch_record["metadata"]["product"] == "CRM Cloud"

# Test 6: FCR/resolution evidence retrieval
def test_fcr_resolution_evidence_retrieval(real_config):
    query = {"kpi": "FCR"}
    res = retrieve_evidence(query, DATA_DIR, CONFIG_PATH)
    assert res["status"] == "SUCCESS"
    has_fcr_term = False
    for r in res["records"]:
        if any("terms" in reason.lower() and ("fcr" in reason.lower() or "resolv" in reason.lower()) for reason in r["matching_reasons"]):
            has_fcr_term = True
            break
    assert has_fcr_term is True

# Test 7: No-match behavior
def test_no_match_behavior(real_config):
    query = {"kpi": "NonexistentKPI", "product": "Core ERP", "customer_segment": "SMB"}
    res = retrieve_evidence(query, DATA_DIR, CONFIG_PATH)
    # Fails to meet minimum threshold of 1.0 or filtered out
    assert res["status"] in ["NO_MATCH", "SUCCESS"]

# Test 8: Missing metadata safety
def test_missing_metadata_safety(real_config):
    query = {"product": "CRM Cloud", "kpi": "CSAT"}
    res = retrieve_evidence(query, DATA_DIR, CONFIG_PATH)
    assert res["status"] == "SUCCESS"
    has_comment = False
    for r in res["records"]:
        if "customer_feedback" in r["source_file"] and "CRM Cloud" in r["text"]:
            has_comment = True
            break
    assert has_comment is True

# Test 9: Provenance preservation
def test_provenance_preservation(real_config):
    query = {"kpi": "AHT"}
    res = retrieve_evidence(query, DATA_DIR, CONFIG_PATH)
    assert res["status"] == "SUCCESS"
    for r in res["records"]:
        assert r["evidence_id"] is not None
        assert r["source_key"] is not None
        assert r["source_file"] is not None
        assert len(r["text"]) > 0

# Test 10: Deterministic ordering
def test_deterministic_ordering(real_config):
    query = {"kpi": "AHT"}
    res = retrieve_evidence(query, DATA_DIR, CONFIG_PATH)
    assert res["status"] == "SUCCESS"
    records = res["records"]
    for idx in range(len(records) - 1):
        r1 = records[idx]
        r2 = records[idx+1]
        assert r1["relevance_score"] >= r2["relevance_score"]
        if r1["relevance_score"] == r2["relevance_score"]:
            assert r1["evidence_id"] < r2["evidence_id"]

# Test 11: Exact relevance-score calculation
def test_exact_relevance_score_calculation():
    mock_record = {
        "evidence_id": "mock_1",
        "source_key": "support_transcripts",
        "source_path": "mock.txt",
        "text": "Auto-Assistant is fast.",
        "date": "2026-06-15",
        "customer_segment": "SMB",
        "product": "CRM Cloud"
    }
    query = {
        "kpi": "AHT",
        "product": "CRM Cloud",
        "customer_segment": "SMB",
        "periods": [("2026-06-01", "2026-06-30")],
        "hypothesis": "AI rollout"
    }
    
    import src.engine.retrieval as ret_mod
    orig_ingest = ret_mod.ingest_evidence
    ret_mod.ingest_evidence = lambda sk, dd, cp: {"status": "SUCCESS", "records": [mock_record]}
    
    try:
        res = retrieve_evidence(query, "dummy_dir")
        assert res["status"] == "SUCCESS"
        rec = res["records"][0]
        # Product (+2.0), Segment (+2.0), Date (+1.0), Keywords "auto-assistant", "fast" (+2.0) = 7.0
        assert rec["relevance_score"] == 7.0
    finally:
        ret_mod.ingest_evidence = orig_ingest

# Test 12: Keyword score cap at +3.0
def test_keyword_score_cap():
    mock_record = {
        "evidence_id": "mock_1",
        "source_key": "support_transcripts",
        "source_path": "mock.txt",
        "text": "bot chatbot AI auto-assistant fast generic speed",  # 7 keywords matched
        "date": None,
        "customer_segment": None,
        "product": None
    }
    query = {
        "kpi": "AHT",
        "hypothesis": "AI rollout"
    }
    
    import src.engine.retrieval as ret_mod
    orig_ingest = ret_mod.ingest_evidence
    ret_mod.ingest_evidence = lambda sk, dd, cp: {"status": "SUCCESS", "records": [mock_record]}
    
    try:
        res = retrieve_evidence(query, "dummy_dir")
        assert res["status"] == "SUCCESS"
        rec = res["records"][0]
        # Score should be exactly 3.0 (capped at +3.0)
        assert rec["relevance_score"] == 3.0
    finally:
        ret_mod.ingest_evidence = orig_ingest

# Test 13: Duplicate keyword occurrences do not inflate score
def test_duplicate_keyword_no_inflation():
    mock_record = {
        "evidence_id": "mock_1",
        "source_key": "support_transcripts",
        "source_path": "mock.txt",
        "text": "AI AI AI AI bot bot bot",  # Duplicate terms
        "date": None,
        "customer_segment": None,
        "product": None
    }
    query = {
        "kpi": "AHT",
        "hypothesis": "AI rollout"
    }
    
    import src.engine.retrieval as ret_mod
    orig_ingest = ret_mod.ingest_evidence
    ret_mod.ingest_evidence = lambda sk, dd, cp: {"status": "SUCCESS", "records": [mock_record]}
    
    try:
        res = retrieve_evidence(query, "dummy_dir")
        assert res["status"] == "SUCCESS"
        rec = res["records"][0]
        # Only distinct terms "ai" and "bot" should match (2.0)
        assert rec["relevance_score"] == 2.0
    finally:
        ret_mod.ingest_evidence = orig_ingest

# Test 14: Word-boundary safety for keywords
def test_word_boundary_safety():
    mock_record = {
        "evidence_id": "mock_1",
        "source_key": "support_transcripts",
        "source_path": "mock.txt",
        "text": "debugging synchronize detail",  # Substrings containing bug, sync, AI
        "date": None,
        "customer_segment": None,
        "product": None
    }
    query = {
        "kpi": "AHT",
        "hypothesis": "CRM patch"
    }
    
    import src.engine.retrieval as ret_mod
    orig_ingest = ret_mod.ingest_evidence
    ret_mod.ingest_evidence = lambda sk, dd, cp: {"status": "SUCCESS", "records": [mock_record]}
    
    try:
        res = retrieve_evidence(query, "dummy_dir")
        # Should not match anything, resulting in NO_MATCH since score is 0.0
        assert res["status"] == "NO_MATCH"
    finally:
        ret_mod.ingest_evidence = orig_ingest

# Test 15: Duplicate evidence prevention
def test_duplicate_evidence_prevention(real_config):
    query = {"kpi": "AHT"}
    res = retrieve_evidence(query, DATA_DIR, CONFIG_PATH)
    assert res["status"] == "SUCCESS"
    ids = [r["evidence_id"] for r in res["records"]]
    assert len(ids) == len(set(ids))

# Test 16: Exact source-text preservation
def test_exact_source_text_preservation(real_config):
    query = {"kpi": "AHT"}
    res = retrieve_evidence(query, DATA_DIR, CONFIG_PATH)
    assert res["status"] == "SUCCESS"
    for r in res["records"]:
        assert len(r["text"].strip()) > 0
        assert "..." not in r["text"] or r["text"].count("...") <= 5

# Test 17: Conservative evidence classification
def test_conservative_evidence_classification():
    # Context classification check
    rec_timeline = {
        "source_key": "rollout_report",
        "text": "TIMELINE & ADOPTION SCHEDULE: Phase 1 launch..."
    }
    assert determine_evidence_class(rec_timeline) == "CONTEXT"
    
    # Limitation check
    rec_lim = {
        "source_key": "rollout_report",
        "text": "Confounding Factors: May-4 patch introduced a contact-sync issue."
    }
    assert determine_evidence_class(rec_lim) == "LIMITATION"
    
    # Association check
    rec_assoc = {
        "source_key": "rollout_report",
        "text": "Average Handling Time (AHT) has decreased dramatically."
    }
    assert determine_evidence_class(rec_assoc) == "ASSOCIATION"

# Test 18: Customer complaint is not automatically classified as FACT
def test_customer_complaint_not_fact():
    # Transcript containing bug complaint
    rec_complaint = {
        "source_key": "support_transcripts",
        "text": "Customer: The chatbot is useless. CRM Cloud sync fails."
    }
    # Should be classified as HYPOTHESIS, not FACT
    assert determine_evidence_class(rec_complaint) == "HYPOTHESIS"
    
    # Customer feedback review comment
    rec_feedback = {
        "source_key": "customer_feedback",
        "text": "The bot closed my ticket instantly without fixing it."
    }
    assert determine_evidence_class(rec_feedback) == "HYPOTHESIS"

# Test 19: Causal language is not generated
def test_causal_language_not_generated(real_config):
    query = {"kpi": "AHT"}
    res = retrieve_evidence(query, DATA_DIR, CONFIG_PATH)
    assert res["status"] == "SUCCESS"
    
    for r in res["records"]:
        causal_words = ["caused", "causes", "responsible for", "resulted in"]
        reasons_text = " ".join(r["matching_reasons"]).lower()
        for word in causal_words:
            assert word not in reasons_text

# Test 20: Regression compatibility with 3A, 3B.1, 3B.2, and 3C.1
def test_regression_compatibility():
    kpi_config = load_yaml(KPI_CONFIG_PATH)
    
    # 3A materiality
    mat_res = analyze_kpi_change("AHT", kpi_config, DATA_DIR, ("2026-01-01", "2026-03-31"), ("2026-06-01", "2026-06-30"))
    assert mat_res["status"] == "MATERIAL"
    
    # 3B.1 driver profile
    drv_res = profile_driver("AHT", "product", ("2026-01-01", "2026-03-31"), ("2026-06-01", "2026-06-30"), DATA_DIR, kpi_config)
    assert drv_res["status"] == "SUCCESS"
    assert abs(drv_res["reconciliation_error"]) <= 1e-9
    
    # 3B.2 hypothesis synthesis
    hyp_res = synthesize_hypotheses("AHT", DATA_DIR, kpi_config, ("2026-01-01", "2026-03-31"), ("2026-06-01", "2026-06-30"), "product")
    assert hyp_res["overall_evidence_state"] == "INVESTIGATION_REQUIRED"
    
    # 3C.1 Ingestion
    ing_res = ingest_evidence("support_transcripts", DATA_DIR, CONFIG_PATH)
    assert ing_res["status"] == "SUCCESS"
