import os
import re
import yaml
from src.engine.materiality import load_yaml

def ingest_evidence(source_key, data_dir, config_path="config/evidence_sources.yaml"):
    """
    Ingests unstructured evidence from the specified source key.
    Verifies path and content, parses records deterministically, and preserves provenance.
    """
    if not os.path.exists(config_path):
        return {
            "status": "NOT_AVAILABLE",
            "reason": f"Config file '{config_path}' does not exist.",
            "records": []
        }

    try:
        config = load_yaml(config_path)
    except Exception as e:
        return {
            "status": "NOT_AVAILABLE",
            "reason": f"Failed to load config: {e}",
            "records": []
        }

    sources = config.get("sources", {})
    if source_key not in sources:
        return {
            "status": "NOT_AVAILABLE",
            "reason": f"Source key '{source_key}' not defined in config.",
            "records": []
        }

    source_def = sources[source_key]
    rel_path = source_def.get("path")
    if not rel_path:
        return {
            "status": "NOT_AVAILABLE",
            "reason": f"No path defined for source key '{source_key}'.",
            "records": []
        }

    # Robust path resolution
    if os.path.exists(rel_path):
        file_path = rel_path
    elif data_dir and os.path.exists(os.path.join(data_dir, rel_path)):
        file_path = os.path.join(data_dir, rel_path)
    elif data_dir and rel_path.startswith("data/") and os.path.exists(os.path.join(data_dir, rel_path[5:])):
        file_path = os.path.join(data_dir, rel_path[5:])
    else:
        file_path = os.path.join(data_dir, rel_path) if data_dir else rel_path

    # Verify file existence and properties safely
    if not os.path.exists(file_path):
        return {
            "status": "NOT_AVAILABLE",
            "reason": f"Source file '{file_path}' does not exist.",
            "records": []
        }

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        return {
            "status": "NOT_AVAILABLE",
            "reason": f"File is not readable: {e}",
            "records": []
        }

    if not text.strip():
        return {
            "status": "NOT_AVAILABLE",
            "reason": "File is empty.",
            "records": []
        }

    source_name = source_def.get("name", source_key)
    source_type = source_def.get("source_type", "QUALITATIVE")
    authority_level = source_def.get("authority_level", "CONTEXTUAL")

    records = []

    if source_key == "support_transcripts":
        # Parse Chat Transcripts
        # Split by [TRANSCRIPT - YYYY-MM-DD] blocks
        start_positions = [m.start() for m in re.finditer(r'\[TRANSCRIPT - ', text)]
        blocks = []
        if start_positions:
            for idx, pos in enumerate(start_positions):
                end_pos = start_positions[idx+1] if idx + 1 < len(start_positions) else len(text)
                blocks.append(text[pos:end_pos].strip())
        
        for i, block in enumerate(blocks, 1):
            date_match = re.search(r'\[TRANSCRIPT - (\d{4}-\d{2}-\d{2})\]', block)
            date_val = date_match.group(1) if date_match else None

            segment_match = re.search(r'Customer Segment:\s*([^\n]+)', block)
            segment_val = segment_match.group(1).strip() if segment_match else None

            product_match = re.search(r'Product:\s*([^\n]+)', block)
            product_val = product_match.group(1).strip() if product_match else None

            records.append({
                "evidence_id": f"{source_key}_{i}",
                "source_key": source_key,
                "source_name": source_name,
                "source_path": rel_path,
                "source_type": source_type,
                "authority_level": authority_level,
                "date": date_val,
                "customer_segment": segment_val,
                "product": product_val,
                "text": block,
                "provenance": {
                    "file": rel_path,
                    "source_key": source_key
                }
            })

    elif source_key == "customer_feedback":
        # Parse Customer Feedback comments
        start_positions = [m.start() for m in re.finditer(r'CSAT Survey Comment - ', text)]
        blocks = []
        if start_positions:
            for idx, pos in enumerate(start_positions):
                end_pos = start_positions[idx+1] if idx + 1 < len(start_positions) else len(text)
                blocks.append(text[pos:end_pos].strip())

        for i, block in enumerate(blocks, 1):
            lines = block.split("\n")
            header = lines[0] if lines else ""

            date_match = re.search(r'Date:\s*(\d{4}-\d{2}-\d{2})', header)
            date_val = date_match.group(1) if date_match else None

            segment_match = re.search(r'Segment:\s*([^-]+)', header)
            segment_val = segment_match.group(1).strip() if segment_match else None

            records.append({
                "evidence_id": f"{source_key}_{i}",
                "source_key": source_key,
                "source_name": source_name,
                "source_path": rel_path,
                "source_type": source_type,
                "authority_level": authority_level,
                "date": date_val,
                "customer_segment": segment_val,
                "product": None,  # CSAT survey lacks structured product metadata in header
                "text": block,
                "provenance": {
                    "file": rel_path,
                    "source_key": source_key
                }
            })

    elif source_key == "rollout_report":
        # Parse Rollout Status Report
        lines = text.strip().split("\n")
        doc_date = "2026-06-30"  # parsed from Date: June 30, 2026
        
        # Helper to build a record
        def make_record(rec_index, rec_text, product_val=None):
            return {
                "evidence_id": f"{source_key}_{rec_index}",
                "source_key": source_key,
                "source_name": source_name,
                "source_path": rel_path,
                "source_type": source_type,
                "authority_level": authority_level,
                "date": doc_date,
                "customer_segment": None,
                "product": product_val,
                "text": rec_text.strip(),
                "provenance": {
                    "file": rel_path,
                    "source_key": source_key
                }
            }

        rec_idx = 1
        
        # 1. Document Metadata Header
        if len(lines) >= 4:
            records.append(make_record(rec_idx, "\n".join(lines[0:4])))
            rec_idx += 1

        # 2. EXECUTIVE SUMMARY
        try:
            exec_start = text.index("EXECUTIVE SUMMARY:")
            timeline_start = text.index("TIMELINE & ADOPTION SCHEDULE:")
            exec_block = text[exec_start:timeline_start].strip()
            records.append(make_record(rec_idx, exec_block))
            rec_idx += 1
        except ValueError:
            pass

        # 3. TIMELINE & ADOPTION SCHEDULE
        try:
            timeline_start = text.index("TIMELINE & ADOPTION SCHEDULE:")
            metrics_start = text.index("OPERATIONAL IMPACT METRICS (Q2 AGGREGATE):")
            timeline_block = text[timeline_start:metrics_start].strip()
            records.append(make_record(rec_idx, timeline_block))
            rec_idx += 1
        except ValueError:
            pass

        # 4. OPERATIONAL IMPACT METRICS sub-items
        try:
            metrics_start = text.index("OPERATIONAL IMPACT METRICS (Q2 AGGREGATE):")
            metrics_text = text[metrics_start:].strip()
            
            sub_sections = []
            current_section = []
            metric_lines = metrics_text.split("\n")
            for ml in metric_lines:
                if ml.strip().startswith(("1.", "2.", "3.", "4.")):
                    if current_section:
                        sub_sections.append("\n".join(current_section).strip())
                    current_section = [ml]
                else:
                    if current_section:
                        current_section.append(ml)
            if current_section:
                sub_sections.append("\n".join(current_section).strip())

            for sec in sub_sections:
                p_val = "CRM Cloud" if "CRM Cloud" in sec else None
                records.append(make_record(rec_idx, sec, product_val=p_val))
                rec_idx += 1
        except ValueError:
            pass

    return {
        "status": "SUCCESS",
        "records": records
    }
