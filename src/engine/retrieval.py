import os
import re
import pandas as pd
from src.engine.evidence import ingest_evidence
from src.engine.materiality import load_yaml

# Safe keyword patterns compiled with word boundaries
KEYWORD_PATTERNS = {
    "AHT": [r"\bhandling time\b", r"\bminutes\b", r"\bseconds\b", r"\bfast\b", r"\bspeed\b", r"\binstant\b", r"\bgeneric\b"],
    "AI_Rollout": [r"\bbot\b", r"\bchatbot\b", r"\bai\b", r"\bauto-assistant\b", r"\bchat assistant\b", r"\bautomated\b"],
    "CRM_Patch": [r"\bpatch\b", r"\bsync\b", r"\bbug\b", r"\bdatabase lock\b", r"\bsystem update\b", r"\bpayload\b", r"\bpayload size\b", r"\bgreyed out\b"],
    "FCR": [r"\bfcr\b", r"\bresolved\b", r"\bfixing\b", r"\bsolved\b", r"\bresolution\b"]
}

def determine_evidence_class(rec):
    """
    Deterministically and conservatively classifies an evidence record.
    FACT: Explicit operational fact, numerical value, status, or directly observed event.
    ASSOCIATION: Explicitly describes an observed pattern or co-occurrence.
    HYPOTHESIS: Suspected mechanism, proposed explanation, complaint, opinion, or interpretation.
    CONTEXT: Background, timeline, rollout status.
    LIMITATION: Explicit data limitation, uncertainty, or boundary.
    """
    source_key = rec["source_key"]
    text_lower = rec["text"].lower()

    if source_key == "customer_feedback":
        # Customer survey reviews are subjective opinions/complaints -> HYPOTHESIS
        return "HYPOTHESIS"

    if source_key == "support_transcripts":
        # If the transcript contains complaints about bugs or chatbot -> HYPOTHESIS
        complaint_terms = ["bug", "fails", "useless", "unhappy", "wasted", "generic"]
        has_complaint = any(term in text_lower for term in complaint_terms)
        if has_complaint:
            return "HYPOTHESIS"
        
        # If it has a system/agent log of FCR or handling time without complaints -> FACT
        log_terms = ["fcr recorded", "handling time:", "total handling time", "fcr logged", "session closed"]
        has_log = any(term in text_lower for term in log_terms)
        if has_log:
            return "FACT"
        
        return "CONTEXT"

    if source_key == "rollout_report":
        if "timeline & adoption schedule" in text_lower or "document ref" in text_lower:
            return "CONTEXT"
        if "confounding factors" in text_lower or "data limitations" in text_lower:
            return "LIMITATION"
        if "average handling time" in text_lower or "contact-sync issue" in text_lower or "noted a 2x increase" in text_lower:
            return "ASSOCIATION"
        
        return "CONTEXT"

    return "CONTEXT"

def retrieve_evidence(query, data_dir, config_path="config/evidence_sources.yaml"):
    """
    Deterministic qualitative evidence retrieval and linking layer.
    """
    sources_to_load = ["support_transcripts", "customer_feedback", "rollout_report"]
    all_records = []
    
    for src in sources_to_load:
        res = ingest_evidence(src, data_dir, config_path)
        if res["status"] == "SUCCESS":
            all_records.extend(res["records"])

    if not all_records:
        return {
            "status": "NOT_AVAILABLE",
            "reason": "No qualitative evidence sources could be loaded or they are empty.",
            "records": []
        }

    kpi = query.get("kpi")
    product = query.get("product")
    segment = query.get("customer_segment")
    periods = query.get("periods", [])
    hypothesis = query.get("hypothesis")

    matched_records = []

    for rec in all_records:
        # Strict metadata exclusion check:
        # If both query and record specify product/segment, and they differ, filter it out.
        if product and rec.get("product") and rec.get("product") != product:
            continue
        if segment and rec.get("customer_segment") and rec.get("customer_segment") != segment:
            continue

        relevance_score = 0.0
        reasons = []

        # 1. Exact Product Match (+2.0)
        if product and rec.get("product") == product:
            relevance_score += 2.0
            reasons.append(f"Exact product match: {product}")

        # 2. Exact Segment Match (+2.0)
        if segment and rec.get("customer_segment") == segment:
            relevance_score += 2.0
            reasons.append(f"Exact customer segment match: {segment}")

        # 3. Date Window Match (+1.0)
        if rec.get("date") and periods:
            rec_dt = pd.to_datetime(rec["date"])
            in_window = False
            for p_start, p_end in periods:
                if pd.to_datetime(p_start) <= rec_dt <= pd.to_datetime(p_end):
                    in_window = True
                    break
            if not in_window:
                continue  # Exclude record if date does not fall within target periods
            relevance_score += 1.0
            reasons.append("Date falls within query target periods")

        # 4. Deterministic Word Boundary Keyword Matching
        keyword_score = 0.0
        text_lower = rec["text"].lower()
        matched_terms = []

        # Query product and segment name matching in text if metadata is None
        if product and rec.get("product") is None:
            prod_pat = r"\b" + re.escape(product.lower()) + r"\b"
            if re.search(prod_pat, text_lower):
                keyword_score += 1.0
                matched_terms.append(product)

        if segment and rec.get("customer_segment") is None:
            seg_pat = r"\b" + re.escape(segment.lower()) + r"\b"
            if re.search(seg_pat, text_lower):
                keyword_score += 1.0
                matched_terms.append(segment)

        # KPI term search
        kpi_category = kpi
        if kpi == "Repeat_Contact_Rate":
            kpi_category = "AHT"  # repeat is related to support ops
        elif kpi == "CSAT" or kpi == "Retention_Rate":
            kpi_category = "FCR"  # CX related to resolution quality

        categories_to_search = []
        if kpi_category in KEYWORD_PATTERNS:
            categories_to_search.append(kpi_category)
        if hypothesis == "AI rollout" or hypothesis == "ai_rollout":
            categories_to_search.append("AI_Rollout")
        if hypothesis == "CRM patch" or hypothesis == "crm_patch":
            categories_to_search.append("CRM_Patch")

        # Search terms case-insensitively using complete word bounds
        for cat in categories_to_search:
            for pattern in KEYWORD_PATTERNS[cat]:
                if re.search(pattern, text_lower):
                    term_clean = pattern.replace(r"\b", "")
                    if term_clean not in matched_terms:
                        matched_terms.append(term_clean)
                        keyword_score += 1.0

        # Cap keyword matching contribution at +3.0 exactly
        if keyword_score > 3.0:
            keyword_score = 3.0
            reasons.append(f"Matched distinct terms: {', '.join(matched_terms)} (capped at +3.0)")
        elif keyword_score > 0:
            reasons.append(f"Matched distinct terms: {', '.join(matched_terms)}")

        relevance_score += keyword_score

        # Minimum score threshold gate (1.0)
        if relevance_score >= 1.0:
            evidence_class = determine_evidence_class(rec)
            
            # Map clean record matching causality policy constraints
            matched_records.append({
                "evidence_id": rec["evidence_id"],
                "source_key": rec["source_key"],
                "source_file": rec["source_path"],
                "text": rec["text"],
                "metadata": {
                    "date": rec["date"],
                    "customer_segment": rec["customer_segment"],
                    "product": rec["product"]
                },
                "evidence_class": evidence_class,
                "relevance_score": relevance_score,
                "matching_reasons": reasons
            })

    if not matched_records:
        return {
            "status": "NO_MATCH",
            "reason": "No evidence records met the minimum relevance threshold of 1.0.",
            "records": []
        }

    # Sort deterministically: relevance_score descending, then evidence_id ascending
    sorted_records = sorted(
        matched_records,
        key=lambda x: (-x["relevance_score"], x["evidence_id"])
    )

    return {
        "status": "SUCCESS",
        "records": sorted_records
    }
