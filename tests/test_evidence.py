import os
import pytest
import pandas as pd
import yaml
from src.engine.evidence import ingest_evidence
from src.engine.materiality import load_yaml, analyze_kpi_change
from src.engine.drivers import profile_driver
from src.engine.hypotheses import synthesize_hypotheses

CONFIG_PATH = "config/evidence_sources.yaml"
KPI_CONFIG_PATH = "config/kpi_definitions.yaml"
DATA_DIR = "data"

@pytest.fixture
def real_config():
    return load_yaml(CONFIG_PATH)

# Test 1: All three configured sources load successfully
def test_all_sources_load_successfully():
    sources = ["support_transcripts", "customer_feedback", "rollout_report"]
    for src in sources:
        res = ingest_evidence(src, DATA_DIR, CONFIG_PATH)
        assert res["status"] == "SUCCESS"
        assert len(res["records"]) > 0

# Test 2: Support transcript blocks are parsed
def test_support_transcripts_parsing():
    res = ingest_evidence("support_transcripts", DATA_DIR, CONFIG_PATH)
    assert res["status"] == "SUCCESS"
    records = res["records"]
    assert len(records) > 0
    # Check first record structure
    first = records[0]
    assert first["date"] == "2026-04-12"
    assert first["customer_segment"] == "Mid-Market"
    assert first["product"] == "CRM Cloud"
    assert first["evidence_id"] == "support_transcripts_1"

# Test 3: Customer feedback blocks are parsed
def test_customer_feedback_parsing():
    res = ingest_evidence("customer_feedback", DATA_DIR, CONFIG_PATH)
    assert res["status"] == "SUCCESS"
    records = res["records"]
    assert len(records) > 0
    # First CSAT Comment is 2026-01-15, SMB, Rating 5/5
    first = records[0]
    assert first["date"] == "2026-01-15"
    assert first["customer_segment"] == "SMB"
    assert first["product"] is None  # product is missing in header
    assert first["evidence_id"] == "customer_feedback_1"

# Test 4: Rollout report is ingested
def test_rollout_report_ingestion():
    res = ingest_evidence("rollout_report", DATA_DIR, CONFIG_PATH)
    assert res["status"] == "SUCCESS"
    records = res["records"]
    assert len(records) > 0
    # Check that CRM Cloud product is correctly mapped in patch section
    crm_patch_rec = None
    for r in records:
        if r["product"] == "CRM Cloud":
            crm_patch_rec = r
            break
    assert crm_patch_rec is not None
    assert "CRM Cloud product software patch" in crm_patch_rec["text"]

# Test 5: Evidence IDs are deterministic
def test_evidence_ids_are_deterministic():
    res1 = ingest_evidence("support_transcripts", DATA_DIR, CONFIG_PATH)
    res2 = ingest_evidence("support_transcripts", DATA_DIR, CONFIG_PATH)
    
    assert [r["evidence_id"] for r in res1["records"]] == [r["evidence_id"] for r in res2["records"]]

# Test 6: Provenance is present on every record
def test_provenance_is_present():
    for src in ["support_transcripts", "customer_feedback", "rollout_report"]:
        res = ingest_evidence(src, DATA_DIR, CONFIG_PATH)
        assert res["status"] == "SUCCESS"
        for r in res["records"]:
            assert "provenance" in r
            assert r["provenance"]["source_key"] == src
            assert r["provenance"]["file"] == r["source_path"]

# Test 7: Missing optional metadata becomes None rather than fabricated
def test_missing_optional_metadata(tmp_path):
    # support_transcripts layout missing Segment and Product
    mock_content = """[TRANSCRIPT - 2026-04-12] Support ID: MM-9801
Agent: Auto-Assistant-v1.2 (AI)
Query: Customer wants to add licenses.
Conversation here...
"""
    file_path = tmp_path / "support_transcripts_mock.txt"
    file_path.write_text(mock_content, encoding="utf-8")
    
    mock_sources = {
        "sources": {
            "support_transcripts": {
                "name": "Mock support transcripts",
                "path": "support_transcripts_mock.txt",
                "source_type": "QUALITATIVE",
                "authority_level": "CONTEXTUAL_SUPPORT"
            }
        }
    }
    config_path = tmp_path / "evidence_sources.yaml"
    with open(config_path, "w") as f:
        yaml.dump(mock_sources, f)
        
    res = ingest_evidence("support_transcripts", str(tmp_path), str(config_path))
    assert res["status"] == "SUCCESS"
    rec = res["records"][0]
    assert rec["date"] == "2026-04-12"
    assert rec["customer_segment"] is None  # missing -> None
    assert rec["product"] is None  # missing -> None

# Test 8: Missing source file returns a safe failure/NOT_AVAILABLE result
def test_missing_source_file_returns_not_available():
    res = ingest_evidence("missing_source_key_or_file", DATA_DIR, CONFIG_PATH)
    assert res["status"] == "NOT_AVAILABLE"
    assert len(res["records"]) == 0

# Test 9: Empty source file is handled safely
def test_empty_source_file_handled_safely(tmp_path):
    file_path = tmp_path / "empty_feedback.txt"
    file_path.write_text("", encoding="utf-8")
    
    mock_sources = {
        "sources": {
            "customer_feedback": {
                "name": "Mock empty feedback",
                "path": "empty_feedback.txt",
                "source_type": "QUALITATIVE",
                "authority_level": "CONTEXTUAL_CX"
            }
        }
    }
    config_path = tmp_path / "evidence_sources.yaml"
    with open(config_path, "w") as f:
        yaml.dump(mock_sources, f)
        
    res = ingest_evidence("customer_feedback", str(tmp_path), str(config_path))
    assert res["status"] == "NOT_AVAILABLE"
    assert "empty" in res["reason"].lower()

# Test 10: Exact source text is preserved
def test_exact_source_text_preserved():
    res = ingest_evidence("support_transcripts", DATA_DIR, CONFIG_PATH)
    assert res["status"] == "SUCCESS"
    # Verify exact line is in the parsed text
    first_text = res["records"][0]["text"]
    assert "[TRANSCRIPT - 2026-04-12] Support ID: MM-9801" in first_text
    assert "Agent: Auto-Assistant-v1.2 (AI)" in first_text

# Test 11: Existing 3A/3B behavior is unaffected (Regression Check)
def test_regression_behavior():
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
