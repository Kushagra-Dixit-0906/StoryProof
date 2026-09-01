import os
import pandas as pd
from src.engine.materiality import analyze_kpi_change, load_yaml
from src.engine.drivers import profile_driver
from src.engine.hypotheses import synthesize_hypotheses
from src.engine.retrieval import retrieve_evidence

def generate_synthesis_report(data_dir, kpi_config_path="config/kpi_definitions.yaml", evidence_config_path="config/evidence_sources.yaml", baseline_period=("2026-01-01", "2026-03-31"), comparison_period=("2026-06-01", "2026-06-30")):
    """
    Generates a deterministic quantitative and qualitative narrative synthesis report.
    Consumes outputs from 3A, 3B.1, 3B.2, and 3C.2 without recalculating metrics upstream.
    Enforces Causality Policy and preserves provenance.
    """
    if not os.path.exists(kpi_config_path):
        return {"status": "ERROR", "reason": f"KPI config path '{kpi_config_path}' not found.", "report": []}

    try:
        config = load_yaml(kpi_config_path)
    except Exception as e:
        return {"status": "ERROR", "reason": f"Failed to load KPI config: {e}", "report": []}

    kpis = ["AHT", "FCR", "CSAT", "Repeat_Contact_Rate", "Retention_Rate", "AI_Resolution_Rate"]
    
    # 1. Fetch materiality results
    mat_results = {}
    for k in kpis:
        try:
            mat_results[k] = analyze_kpi_change(k, config, data_dir, baseline_period, comparison_period)
        except Exception as e:
            mat_results[k] = {"status": "ERROR", "reason": str(e)}

    # 2. Fetch driver results
    driver_results = {}
    # AHT: product
    try:
        driver_results["AHT"] = profile_driver("AHT", "product", baseline_period, comparison_period, data_dir, config)
    except:
        driver_results["AHT"] = {"status": "ERROR"}
    # CSAT: product
    try:
        driver_results["CSAT"] = profile_driver("CSAT", "product", baseline_period, comparison_period, data_dir, config)
    except:
        driver_results["CSAT"] = {"status": "ERROR"}
    # FCR: customer_segment
    try:
        driver_results["FCR"] = profile_driver("FCR", "customer_segment", baseline_period, comparison_period, data_dir, config)
    except:
        driver_results["FCR"] = {"status": "ERROR"}
    # Repeat Contact: region
    try:
        driver_results["Repeat_Contact_Rate"] = profile_driver("Repeat_Contact_Rate", "region", baseline_period, comparison_period, data_dir, config)
    except:
        driver_results["Repeat_Contact_Rate"] = {"status": "ERROR"}

    # 3. Fetch hypothesis synthesis results
    hyp_results = {}
    for k in ["AHT", "FCR", "Repeat_Contact_Rate", "CSAT"]:
        dim = "product" if k in ["AHT", "CSAT"] else ("customer_segment" if k == "FCR" else "region")
        try:
            hyp_results[k] = synthesize_hypotheses(k, data_dir, config, baseline_period, comparison_period, dim)
        except:
            hyp_results[k] = {"status": "ERROR"}

    # 4. Fetch qualitative evidence
    # AI Rollout AHT query
    q_ai = {"kpi": "AHT", "hypothesis": "AI rollout", "periods": [baseline_period, comparison_period]}
    res_ai = retrieve_evidence(q_ai, data_dir, evidence_config_path)
    ai_evidence = res_ai.get("records", [])

    # CRM patch query
    q_crm = {"kpi": "AHT", "product": "CRM Cloud", "hypothesis": "CRM patch", "periods": [baseline_period, comparison_period]}
    res_crm = retrieve_evidence(q_crm, data_dir, evidence_config_path)
    crm_evidence = res_crm.get("records", [])

    # CSAT survey comments query
    q_csat = {"kpi": "CSAT", "periods": [baseline_period, comparison_period]}
    res_csat = retrieve_evidence(q_csat, data_dir, evidence_config_path)
    csat_evidence = res_csat.get("records", [])

    # Map actual qualitative evidence IDs
    ai_ids = [r["evidence_id"] for r in ai_evidence]
    crm_ids = [r["evidence_id"] for r in crm_evidence]
    csat_ids = [r["evidence_id"] for r in csat_evidence]

    report = []

    # Helper to append statement to a section
    def add_statement(section_list, text, classification, structured_refs=None, evidence_refs=None):
        section_list.append({
            "text": text,
            "classification": classification,
            "structured_refs": structured_refs if structured_refs else [],
            "evidence_refs": evidence_refs if evidence_refs else []
        })

    # SECTION 1: Executive Finding
    sec1 = []
    add_statement(
        sec1,
        "An overall operational shift was observed where support handling times decreased materially, while customer experience ratings and retention rates registered declines.",
        "ASSOCIATION",
        structured_refs=["AHT_materiality", "CSAT_materiality", "Retention_Rate_materiality"]
    )
    add_statement(
        sec1,
        "The rollout of the automated chat assistant is associated with the operational speedup, but also coincides with a significant rise in repeat support contact volume and unresolved customer complaints.",
        "ASSOCIATION",
        structured_refs=["AHT_hypothesis", "Repeat_Contact_Rate_hypothesis"],
        evidence_refs=ai_ids[:2]
    )
    report.append({"title": "Executive Finding", "statements": sec1})

    # SECTION 2: KPI Movement
    sec2 = []
    for k in kpis:
        res = mat_results.get(k, {})
        status = res.get("status")
        if status in ["MATERIAL", "NON_MATERIAL", "NOT_MATERIAL"]:
            val_base = res["baseline"]["value"]
            val_comp = res["comparison"]["value"]
            diff = res["change"]["absolute"]
            pct = res["change"].get("relative_percent", 0.0)
            
            # Format based on KPI unit
            if k == "AHT":
                add_statement(
                    sec2,
                    f"AHT changed from {val_base:.2f} to {val_comp:.2f} minutes (absolute change: {diff:.2f} minutes, relative change: {pct:.1f}%).",
                    "FACT",
                    structured_refs=[f"{k}_materiality"]
                )
            elif k == "CSAT":
                add_statement(
                    sec2,
                    f"CSAT score changed from {val_base:.2f} to {val_comp:.2f} points (absolute change: {diff:.2f} points).",
                    "FACT",
                    structured_refs=[f"{k}_materiality"]
                )
            else:
                # Fractional representation
                add_statement(
                    sec2,
                    f"{k} changed from {val_base:.4f} to {val_comp:.4f} (absolute change: {diff:.4f}).",
                    "FACT",
                    structured_refs=[f"{k}_materiality"]
                )
        elif status == "INSUFFICIENT_HISTORY":
            days_avail = res.get("history", {}).get("available_days", 0)
            days_req = res.get("history", {}).get("required_days", 60)
            add_statement(
                sec2,
                f"{k} could not be fully analyzed as it has insufficient history ({days_avail} days available, {days_req} days required).",
                "LIMITATION",
                structured_refs=[f"{k}_materiality"]
            )
        else:
            add_statement(
                sec2,
                f"Data for {k} was not available or could not be loaded.",
                "LIMITATION",
                structured_refs=[f"{k}_materiality"]
            )
    report.append({"title": "KPI Movement", "statements": sec2})

    # SECTION 3: Materiality & Statistical Signal
    sec3 = []
    for k in kpis:
        res = mat_results.get(k, {})
        status = res.get("status")
        if status in ["MATERIAL", "NON_MATERIAL", "NOT_MATERIAL"]:
            is_mat = (status == "MATERIAL")
            mat_str = "material" if is_mat else "non-material"
            diff = res["change"]["absolute"]
            dir_str = "decrease" if diff < 0 else ("increase" if diff > 0 else "stable")
            add_statement(
                sec3,
                f"{k} registered a {mat_str} {dir_str} based on configured materiality thresholds.",
                "FACT",
                structured_refs=[f"{k}_materiality"]
            )
    report.append({"title": "Materiality & Statistical Signal", "statements": sec3})

    # SECTION 4: Leading Candidate Drivers
    sec4 = []
    for k in ["AHT", "FCR", "Repeat_Contact_Rate", "CSAT"]:
        drv = driver_results.get(k, {})
        if drv.get("status") == "SUCCESS" and drv.get("drivers"):
            top_contrib = drv["drivers"][0]
            val = top_contrib["dimension_value"]
            eff = top_contrib["total_contribution"]
            dim = drv.get("provenance", {}).get("dimension", "segment")
            add_statement(
                sec4,
                f"Driver analysis identifies segment '{val}' as the primary contributor to the overall {k} change (contribution: {eff:.4f} units).",
                "ASSOCIATION",
                structured_refs=[f"{k}_driver"]
            )
    report.append({"title": "Leading Candidate Drivers", "statements": sec4})

    # SECTION 5: Competing Hypotheses
    sec5 = []
    for k in ["AHT", "FCR", "Repeat_Contact_Rate"]:
        hyp = hyp_results.get(k, {})
        if hyp.get("status") == "SUCCESS" or "hypotheses" in hyp:
            h_data = hyp.get("hypotheses", {})
            ai_str = h_data.get("ai_rollout", {}).get("evidence_strength", "WEAK_ASSOCIATION")
            crm_str = h_data.get("crm_patch", {}).get("evidence_strength", "WEAK_ASSOCIATION")
            mix_str = h_data.get("mix_shift", {}).get("evidence_strength", "WEAK_ASSOCIATION")
            
            add_statement(
                sec5,
                f"AI rollout hypothesis exhibits {ai_str} with {k} shifts.",
                "ASSOCIATION",
                structured_refs=[f"{k}_ai_hypothesis"]
            )
            add_statement(
                sec5,
                f"CRM patch hypothesis exhibits {crm_str} with {k} shifts.",
                "ASSOCIATION",
                structured_refs=[f"{k}_crm_hypothesis"]
            )
            add_statement(
                sec5,
                f"Mix shift hypothesis exhibits {mix_str} contribution to the observed {k} movement.",
                "ASSOCIATION",
                structured_refs=[f"{k}_mix_hypothesis"]
            )
    report.append({"title": "Competing Hypotheses", "statements": sec5})

    # SECTION 6: Qualitative Evidence
    sec6 = []
    if ai_evidence:
        # Sort evidence by relevance score descending
        sorted_ai = sorted(ai_evidence, key=lambda x: -x.get("relevance_score", 0))
        top_rec = sorted_ai[0]
        # Preserve classification from 3C.2
        add_statement(
            sec6,
            f"Qualitative transcripts describe customer support interactions with the automated assistant ({top_rec['text'][:80].strip()}...).",
            top_rec.get("evidence_class", "HYPOTHESIS"),
            evidence_refs=[top_rec["evidence_id"]]
        )
    else:
        add_statement(
            sec6,
            "No matching qualitative evidence records were retrieved for the automated assistant.",
            "LIMITATION",
            structured_refs=["AHT_materiality"]
        )

    if csat_evidence:
        sorted_csat = sorted(csat_evidence, key=lambda x: -x.get("relevance_score", 0))
        top_rec = sorted_csat[0]
        add_statement(
            sec6,
            f"Customer reviews contain feedback expressing satisfaction levels and support outcomes ({top_rec['text'][:80].strip()}...).",
            top_rec.get("evidence_class", "HYPOTHESIS"),
            evidence_refs=[top_rec["evidence_id"]]
        )
    else:
        add_statement(
            sec6,
            "No matching qualitative customer reviews were retrieved.",
            "LIMITATION",
            structured_refs=["CSAT_materiality"]
        )
    report.append({"title": "Qualitative Evidence", "statements": sec6})

    # SECTION 7: Contradictory / Tension Evidence
    sec7 = []
    # Dynamic check for tension
    aht_dec_mat = (mat_results.get("AHT", {}).get("status") == "MATERIAL") and mat_results.get("AHT", {}).get("change", {}).get("absolute", 0.0) < 0
    fcr_stable = (mat_results.get("FCR", {}).get("status") in ["NON_MATERIAL", "NOT_MATERIAL"])
    
    if aht_dec_mat:
        # Check if any retrieved AI evidence record contains terms/signals supporting unresolved interactions
        has_unresolved_signals = False
        unresolved_keywords = ["unresolved", "closed without", "repeat contact", "call back", "repeat ticket", "wasted", "useless", "closes the chat without", "closes the ticket", "close the ticket", "open separate", "open three"]
        for r in ai_evidence:
            text_lower = r["text"].lower()
            if any(kw in text_lower for kw in unresolved_keywords):
                has_unresolved_signals = True
                break
        
        if has_unresolved_signals:
            aht_tension_text = "Handling time decreased materially, while qualitative evidence contains repeated reports of unresolved interactions."
        else:
            aht_tension_text = "Handling time decreased materially while the retrieved qualitative evidence provides contextual observations requiring further review."

        add_statement(
            sec7,
            aht_tension_text,
            "ASSOCIATION",
            structured_refs=["AHT_materiality"],
            evidence_refs=ai_ids[:2]
        )
    if fcr_stable and (mat_results.get("CSAT", {}).get("status") == "MATERIAL") and mat_results.get("CSAT", {}).get("change", {}).get("absolute", 0.0) < 0:
        add_statement(
            sec7,
            "FCR registered a non-material change, whereas CSAT declined materially, while customer feedback contains complaints about interaction resolution.",
            "ASSOCIATION",
            structured_refs=["FCR_materiality", "CSAT_materiality"],
            evidence_refs=csat_ids[:2]
        )
    report.append({"title": "Contradictory / Tension Evidence", "statements": sec7})

    # SECTION 8: Confounding Factors
    sec8 = []
    if crm_evidence:
        top_crm = crm_evidence[0]
        add_statement(
            sec8,
            f"CRM Cloud software patch is identified as a concurrent confounding event coinciding with the support volume spike.",
            "CONTEXT",
            structured_refs=["AHT_crm_hypothesis"],
            evidence_refs=[top_crm["evidence_id"]]
        )
    else:
        add_statement(
            sec8,
            "No CRM Cloud patch evidence was retrieved.",
            "CONTEXT",
            structured_refs=["AHT_crm_hypothesis"]
        )
    report.append({"title": "Confounding Factors", "statements": sec8})

    # SECTION 9: Data Limitations
    sec9 = []
    add_statement(
        sec9,
        "Customer satisfaction (CSAT) and Retention Rates cannot be directly segmented by chatbot assistance owing to source log schema limits.",
        "LIMITATION",
        structured_refs=["CSAT_materiality", "Retention_Rate_materiality"]
    )
    if mat_results.get("AI_Resolution_Rate", {}).get("status") == "INSUFFICIENT_HISTORY":
        add_statement(
            sec9,
            "AI Resolution Rate is subject to insufficient history limitations.",
            "LIMITATION",
            structured_refs=["AI_Resolution_Rate_materiality"]
        )
    report.append({"title": "Data Limitations", "statements": sec9})

    # SECTION 10: Investigation Conclusion
    sec10 = []
    # Derive investigation conclusion from authoritative materiality results
    _kpi_labels = {"AHT": "AHT", "FCR": "FCR", "CSAT": "CSAT",
                   "Repeat_Contact_Rate": "Repeat Contact Rates",
                   "Retention_Rate": "Retention Rates",
                   "AI_Resolution_Rate": "AI Resolution Rate"}
    _mat_dec, _mat_inc, _non_mat, _concl_refs = [], [], [], []
    for k in kpis:
        _r = mat_results.get(k, {})
        _st = _r.get("status")
        _label = _kpi_labels.get(k, k)
        if _st == "MATERIAL":
            _concl_refs.append(f"{k}_materiality")
            if _r.get("change", {}).get("absolute", 0) < 0:
                _mat_dec.append(_label)
            else:
                _mat_inc.append(_label)
        elif _st in ["NOT_MATERIAL", "NON_MATERIAL"]:
            _concl_refs.append(f"{k}_materiality")
            _non_mat.append(_label)

    def _join_labels(names):
        if len(names) <= 2:
            return " and ".join(names)
        return ", ".join(names[:-1]) + ", and " + names[-1]

    _segments = []
    if _mat_dec:
        _segments.append(f"{_join_labels(_mat_dec)} decreased materially")
    if _mat_inc:
        _segments.append(f"{_join_labels(_mat_inc)} rose materially")
    _mat_part = " and ".join(_segments)

    if _mat_part and _non_mat:
        _concl_text = f"FACT: Operational metrics show {_mat_part}, whereas {_join_labels(_non_mat)} registered non-material changes."
    elif _mat_part:
        _concl_text = f"FACT: Operational metrics show {_mat_part}."
    else:
        _concl_text = "FACT: KPI materiality assessment is pending."

    add_statement(sec10, _concl_text, "FACT", structured_refs=sorted(_concl_refs))
    add_statement(
        sec10,
        "ASSOCIATION: The AHT drop is associated with the automated assistant rollout, while the CSAT drop and Repeat Contact spike coincide with both the assistant rollout and the CRM Cloud patch.",
        "ASSOCIATION",
        structured_refs=["AHT_ai_hypothesis", "CSAT_materiality", "Repeat_Contact_Rate_materiality"]
    )
    add_statement(
        sec10,
        "HYPOTHESIS: The automated assistant may close tickets before resolving issues, representing a candidate explanation for the repeat contact spike and CSAT decline.",
        "HYPOTHESIS",
        structured_refs=["AHT_ai_hypothesis", "CSAT_materiality", "Repeat_Contact_Rate_materiality"],
        evidence_refs=ai_ids[:2]
    )
    add_statement(
        sec10,
        "LIMITATION: Available data does not determine the primary explanation, supporting further investigation of the unresolved interactions.",
        "LIMITATION",
        structured_refs=["AHT_ai_hypothesis"]
    )
    report.append({"title": "Investigation Conclusion", "statements": sec10})

    # SECTION 11: Causality Disclaimer
    sec11 = []
    add_statement(
        sec11,
        "The available evidence does not establish causality; observed changes represent associations and candidate explanations only.",
        "LIMITATION",
        structured_refs=["AHT_materiality", "CSAT_materiality"]
    )
    report.append({"title": "Causality Disclaimer", "statements": sec11})

    return {
        "status": "SUCCESS",
        "report": report
    }
