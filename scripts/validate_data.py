import os
import pandas as pd
import numpy as np
import yaml

def load_csv(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing file: {path}")
    return pd.read_csv(path)

def load_yaml(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing file: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def run_data_quality_checks():
    print("\n--- [1] DATA QUALITY CHECKS ---")
    passed = True
    
    # Define schemas
    schemas = {
        "data/support_daily.csv": {
            "columns": ["date", "region", "product", "customer_segment", "agent_team", "ai_assisted", "contacts", "resolved_contacts", "first_contact_resolutions", "repeat_contacts", "total_handling_seconds"],
            "grain": ["date", "region", "product", "customer_segment", "agent_team", "ai_assisted"]
        },
        "data/cx_weekly.csv": {
            "columns": ["week_start", "region", "product", "customer_segment", "survey_responses", "csat_score"],
            "grain": ["week_start", "region", "product", "customer_segment"]
        },
        "data/crm_monthly.csv": {
            "columns": ["month", "region", "customer_segment", "active_customers", "retained_customers"],
            "grain": ["month", "region", "customer_segment"]
        },
        "data/ai_resolution_rate.csv": {
            "columns": ["date", "region", "product", "ai_resolution_rate"],
            "grain": ["date", "region", "product"]
        }
    }
    
    for path, meta in schemas.items():
        try:
            df = load_csv(path)
            print(f"[OK] Loaded {path} successfully ({len(df)} rows).")
            
            # Check columns
            missing_cols = [c for c in meta["columns"] if c not in df.columns]
            if missing_cols:
                print(f"[FAIL] {path} is missing columns: {missing_cols}")
                passed = False
            else:
                print(f"  - Column schema verification: PASS")
                
            # Check duplicates at intended grain
            grain_cols = meta["grain"]
            dup_count = df.duplicated(subset=grain_cols).sum()
            if dup_count > 0:
                print(f"[FAIL] {path} has {dup_count} duplicate rows at grain {grain_cols}")
                passed = False
            else:
                print(f"  - Granularity constraint verification: PASS")
                
            # Check negative values in numeric columns
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            neg_counts = {col: (df[col] < 0).sum() for col in numeric_cols}
            any_neg = any(v > 0 for v in neg_counts.values())
            if any_neg:
                print(f"[FAIL] {path} contains negative values: {neg_counts}")
                passed = False
            else:
                print(f"  - Non-negativity constraint verification: PASS")
                
            # Internal consistency checks
            if path == "data/support_daily.csv":
                c_fcr = (df["first_contact_resolutions"] > df["contacts"]).sum()
                c_repeat = (df["repeat_contacts"] > df["contacts"]).sum()
                c_resolved = (df["resolved_contacts"] > df["contacts"]).sum()
                if c_fcr > 0 or c_repeat > 0 or c_resolved > 0:
                    print(f"[FAIL] {path} has inconsistent counts: FCR>Contacts ({c_fcr}), Repeat>Contacts ({c_repeat}), Resolved>Contacts ({c_resolved})")
                    passed = False
                else:
                    print(f"  - Internal counts consistency: PASS")
            elif path == "data/crm_monthly.csv":
                c_retained = (df["retained_customers"] > df["active_customers"]).sum()
                if c_retained > 0:
                    print(f"[FAIL] {path} has inconsistent counts: Retained > Active ({c_retained})")
                    passed = False
                else:
                    print(f"  - Internal counts consistency: PASS")
            elif path == "data/cx_weekly.csv":
                invalid_csat = ((df["csat_score"] < 0) | (df["csat_score"] > 100)).sum()
                if invalid_csat > 0:
                    print(f"[FAIL] {path} contains CSAT score out of 0-100 range: {invalid_csat} rows")
                    passed = False
                else:
                    print(f"  - Value boundaries (CSAT in 0-100): PASS")
            elif path == "data/ai_resolution_rate.csv":
                invalid_rate = ((df["ai_resolution_rate"] < 0) | (df["ai_resolution_rate"] > 100)).sum()
                if invalid_rate > 0:
                    print(f"[FAIL] {path} contains AI Resolution Rate out of 0-100 range: {invalid_rate} rows")
                    passed = False
                else:
                    print(f"  - Value boundaries (Resolution Rate in 0-100): PASS")
                    
        except Exception as e:
            print(f"[FAIL] Failed during data quality check for {path}: {e}")
            passed = False
            
    # Verify AI adoption progresses plausibly
    try:
        support = load_csv("data/support_daily.csv")
        support['date_dt'] = pd.to_datetime(support['date'])
        
        jan_mar_ai = support[support['date_dt'] < '2026-04-01']['ai_assisted'].mean()
        apr_ai = support[(support['date_dt'] >= '2026-04-01') & (support['date_dt'] < '2026-05-01')]['ai_assisted'].mean()
        may_ai = support[(support['date_dt'] >= '2026-05-01') & (support['date_dt'] < '2026-06-01')]['ai_assisted'].mean()
        jun_ai = support[support['date_dt'] >= '2026-06-01']['ai_assisted'].mean()
        
        print(f"  - AI Adoption Progression: Q1={jan_mar_ai:.1%}, Apr={apr_ai:.1%}, May={may_ai:.1%}, Jun={jun_ai:.1%}")
        if jan_mar_ai > 0.05 or not (apr_ai < may_ai < jun_ai):
            print(f"[FAIL] AI adoption progression is not plausible.")
            passed = False
        else:
            print(f"  - AI Adoption Progression verification: PASS")
            
        # Verify sufficient pre-rollout history (Jan 1 to Mar 31 is 90 days)
        pre_days = support[support['date_dt'] < '2026-04-01']['date'].nunique()
        print(f"  - Pre-rollout baseline days count: {pre_days} days")
        if pre_days < 90:
            print(f"[FAIL] Insufficient pre-rollout history ({pre_days} days, expected >= 90)")
            passed = False
        else:
            print(f"  - Baseline history volume verification: PASS")
            
        # Check no hidden causality fields exist
        prohibited_cols = ["true_cause", "hidden_driver", "causal_answer", "target_driver_percentage", "story_answer"]
        for col in prohibited_cols:
            if col in support.columns:
                print(f"[FAIL] support_daily contains hidden causality field '{col}'")
                passed = False
        print("  - Absence of hidden causality fields: PASS")
            
    except Exception as e:
        print(f"[FAIL] Failed during adoption/history check: {e}")
        passed = False
        
    return passed

def run_semantic_contract_checks():
    print("\n--- [2] SEMANTIC CONTRACT CHECKS ---")
    passed = True
    
    kpis = ["AHT", "FCR", "CSAT", "Repeat_Contact_Rate", "Retention_Rate", "AI_Resolution_Rate"]
    required_fields = [
        "name", "description", "formula", "unit", "owner", "business_purpose", "expected_drivers", 
        "source", "source_grain", "refresh_cadence", "materiality_threshold", "allowed_roles_personas", 
        "lineage_description", "directionality", "aggregation_method", "numerator_field", "denominator_field", 
        "raw_unit", "display_unit", "evidence_sources", "minimum_history_days", "baseline_method", 
        "confidence_notes", "causal_interpretation_policy"
    ]
    
    try:
        defs = load_yaml("config/kpi_definitions.yaml")
        print("[OK] Loaded config/kpi_definitions.yaml successfully.")
        
        # Check that all KPIs are defined
        missing_kpis = [k for k in kpis if k not in defs]
        if missing_kpis:
            print(f"[FAIL] kpi_definitions.yaml is missing KPI entries: {missing_kpis}")
            passed = False
        else:
            print("  - KPI coverage check: PASS")
            
        for kpi, d in defs.items():
            if kpi not in kpis:
                continue
            
            # Check all fields exist
            missing_fields = [f for f in required_fields if f not in d]
            if missing_fields:
                print(f"[FAIL] KPI '{kpi}' is missing fields in configuration: {missing_fields}")
                passed = False
            else:
                print(f"  - Schema check for '{kpi}': PASS")
                
            # Logical alignment check: source filename validation
            source_file = d.get("source")
            if source_file and not os.path.exists(os.path.join("data", source_file)):
                print(f"[FAIL] KPI '{kpi}' references missing source file '{source_file}'")
                passed = False
            else:
                print(f"  - Source file linkage check for '{kpi}': PASS")
                
            # Lineage description check
            lineage = d.get("lineage_description", "")
            formula = d.get("formula", "")
            # Basic sanity check that formula fields are mentioned in lineage
            if kpi == "AHT" and "total_handling_seconds" not in lineage:
                print(f"[WARN] AHT lineage description might not match formula fields.")
            elif kpi == "Retention_Rate" and "active_customers" not in lineage:
                print(f"[WARN] Retention Rate lineage description might not match formula fields.")
                
    except Exception as e:
        print(f"[FAIL] Failed during semantic contract validation: {e}")
        passed = False
        
    return passed

def run_evidence_layer_checks():
    print("\n--- [3] EVIDENCE LAYER CHECKS ---")
    passed = True
    
    unstructured_files = [
        "data/unstructured/support_transcripts.txt",
        "data/unstructured/customer_feedback.txt",
        "data/unstructured/rollout_report.txt"
    ]
    
    # 1. Check unstructured files exist and are not empty
    for path in unstructured_files:
        if not os.path.exists(path):
            print(f"[FAIL] Missing unstructured file: {path}")
            passed = False
        elif os.path.getsize(path) == 0:
            print(f"[FAIL] Unstructured file is empty: {path}")
            passed = False
        else:
            print(f"[OK] Unstructured file '{path}' is present and non-empty ({os.path.getsize(path)} bytes).")
            
    # 2. Check evidence sources yaml
    try:
        sources_meta = load_yaml("config/evidence_sources.yaml")
        print("[OK] Loaded config/evidence_sources.yaml successfully.")
        
        required_sources = ["support_daily", "cx_weekly", "crm_monthly", "ai_resolution_rate", "support_transcripts", "customer_feedback", "rollout_report"]
        missing_sources = [s for s in required_sources if s not in sources_meta.get("sources", {})]
        
        if missing_sources:
            print(f"[FAIL] evidence_sources.yaml is missing source metadata: {missing_sources}")
            passed = False
        else:
            print("  - Evidence sources metadata coverage: PASS")
            
        # Validate fields inside evidence_sources
        fields_to_check = ["name", "path", "source_type", "is_structured", "grain", "authority_level", "allowed_use", "provenance_requirements"]
        for src_name, src_data in sources_meta.get("sources", {}).items():
            missing_fields = [f for f in fields_to_check if f not in src_data]
            if missing_fields:
                print(f"[FAIL] Source '{src_name}' in evidence_sources.yaml is missing fields: {missing_fields}")
                passed = False
            else:
                print(f"  - Source schema check for '{src_name}': PASS")
                
    except Exception as e:
        print(f"[FAIL] Failed during evidence sources check: {e}")
        passed = False
        
    return passed

def run_sparse_history_checks():
    print("\n--- [4] SPARSE HISTORY CHECKS ---")
    passed = True
    
    try:
        ai_res = load_csv("data/ai_resolution_rate.csv")
        unique_dates = ai_res['date'].nunique()
        print(f"  - AI Resolution Rate unique calendar days count: {unique_dates}")
        if unique_dates != 21:
            print(f"[FAIL] AI Resolution Rate has {unique_dates} days of history (expected exactly 21)")
            passed = False
        else:
            print("  - Sparse history duration verification: PASS")
            
    except Exception as e:
        print(f"[FAIL] Failed during sparse history check: {e}")
        passed = False
        
    return passed

def run_business_pattern_checks():
    print("\n--- [5] BUSINESS PATTERN CHECKS ---")
    passed = True
    
    try:
        support = load_csv("data/support_daily.csv")
        cx = load_csv("data/cx_weekly.csv")
        crm = load_csv("data/crm_monthly.csv")
        
        support['date_dt'] = pd.to_datetime(support['date'])
        cx['week_start_dt'] = pd.to_datetime(cx['week_start'])
        
        # Split pre-rollout (Q1: Jan-Mar) vs. peak rollout (June)
        pre_support = support[support['date_dt'] < '2026-04-01']
        post_support = support[support['date_dt'] >= '2026-06-01']
        
        pre_cx = cx[(cx['week_start_dt'] >= '2026-01-01') & (cx['week_start_dt'] <= '2026-03-31')]
        post_cx = cx[(cx['week_start_dt'] >= '2026-06-01') & (cx['week_start_dt'] <= '2026-06-30')]
        
        crm_pre = crm[crm['month'].isin(['2026-01', '2026-02', '2026-03'])]
        crm_post = crm[crm['month'] == '2026-06']
        
        # AHT
        pre_aht = (pre_support['total_handling_seconds'].sum() / pre_support['resolved_contacts'].sum()) / 60
        post_aht = (post_support['total_handling_seconds'].sum() / post_support['resolved_contacts'].sum()) / 60
        aht_diff_pct = (post_aht - pre_aht) / pre_aht * 100
        
        # FCR
        pre_fcr = pre_support['first_contact_resolutions'].sum() / pre_support['contacts'].sum() * 100
        post_fcr = post_support['first_contact_resolutions'].sum() / post_support['contacts'].sum() * 100
        fcr_diff = post_fcr - pre_fcr
        
        # CSAT (weighted average: sum(csat_score * survey_responses) / sum(survey_responses))
        pre_csat_num = (pre_cx['csat_score'] * pre_cx['survey_responses']).sum()
        pre_csat_den = pre_cx['survey_responses'].sum()
        post_csat_num = (post_cx['csat_score'] * post_cx['survey_responses']).sum()
        post_csat_den = post_cx['survey_responses'].sum()
        
        if pre_csat_den == 0:
            print("[FAIL] CSAT Pattern: Q1 CSAT denominator (survey_responses sum) is zero.")
            passed = False
            pre_csat = float('nan')
        else:
            pre_csat = float(pre_csat_num / pre_csat_den)
            
        if post_csat_den == 0:
            print("[FAIL] CSAT Pattern: June CSAT denominator (survey_responses sum) is zero.")
            passed = False
            post_csat = float('nan')
        else:
            post_csat = float(post_csat_num / post_csat_den)
            
        if pre_csat_den != 0 and post_csat_den != 0:
            csat_diff = post_csat - pre_csat
        else:
            csat_diff = float('nan')
        
        # Repeat Contacts
        pre_repeat = pre_support['repeat_contacts'].sum() / pre_support['contacts'].sum() * 100
        post_repeat = post_support['repeat_contacts'].sum() / post_support['contacts'].sum() * 100
        repeat_diff = post_repeat - pre_repeat
        
        # Retention
        pre_ret = crm_pre['retained_customers'].sum() / crm_pre['active_customers'].sum() * 100
        post_ret = crm_post['retained_customers'].sum() / crm_post['active_customers'].sum() * 100
        ret_diff = post_ret - pre_ret
        
        print("\n[KPI COMPARISON SUMMARY]")
        print(f"AHT (minutes):          Pre = {pre_aht:.2f} | Post = {post_aht:.2f} | Change = {aht_diff_pct:+.1f}%")
        print(f"FCR (%):                Pre = {pre_fcr:.1f}% | Post = {post_fcr:.1f}% | Change = {fcr_diff:+.2f}%")
        print(f"CSAT Score:             Pre = {pre_csat:.1f} | Post = {post_csat:.1f} | Change = {csat_diff:+.1f} pts")
        print(f"Repeat Contact Rate (%): Pre = {pre_repeat:.1f}% | Post = {post_repeat:.1f}% | Change = {repeat_diff:+.1f}%")
        print(f"Retention Rate (%):     Pre = {pre_ret:.2f}% | Post = {post_ret:.2f}% | Change = {ret_diff:+.2f}%")
        
        print("\n[Business Pattern Validation Ranges]")
        
        # Validate ranges
        # AHT target: -30% to -50%
        if -50.0 <= aht_diff_pct <= -30.0:
            print(f"[PASS] AHT Pattern: {aht_diff_pct:.1f}% drop (Expected -30% to -50%)")
        else:
            print(f"[FAIL] AHT Pattern: {aht_diff_pct:.1f}% drop (Expected -30% to -50%)")
            passed = False
            
        # FCR target: within ±3%
        if abs(fcr_diff) <= 3.0:
            print(f"[PASS] FCR Pattern: {fcr_diff:+.2f}% change (Expected within +/-3%)")
        else:
            print(f"[FAIL] FCR Pattern: {fcr_diff:+.2f}% change (Expected within +/-3%)")
            passed = False
            
        # CSAT target: -5 to -12 points
        import math
        if math.isnan(csat_diff):
            print("[FAIL] CSAT Pattern: Cannot validate CSAT change due to zero denominator.")
            passed = False
        elif -12.0 <= csat_diff <= -5.0:
            print(f"[PASS] CSAT Pattern: {csat_diff:+.1f} pts change (Expected -5 to -12)")
        else:
            print(f"[FAIL] CSAT Pattern: {csat_diff:+.1f} pts change (Expected -5 to -12)")
            passed = False
            
        # Repeat contact: clearly higher (> +5%)
        if repeat_diff >= 5.0:
            print(f"[PASS] Repeat Contact Rate Pattern: {repeat_diff:+.1f}% change (Expected >= +5%)")
        else:
            print(f"[FAIL] Repeat Contact Rate Pattern: {repeat_diff:+.1f}% change (Expected >= +5%)")
            passed = False
            
        # Retention target: modest deterioration (< 0%)
        if ret_diff < 0:
            print(f"[PASS] Retention Rate Pattern: {ret_diff:+.2f}% change (Expected < 0%)")
        else:
            print(f"[FAIL] Retention Rate Pattern: {ret_diff:+.2f}% change (Expected < 0%)")
            passed = False
            
    except Exception as e:
        print(f"[FAIL] Failed during business pattern validation: {e}")
        passed = False
        
    return passed

def main():
    print("========================================")
    print("       STORYPROOF DATA AUDIT ENGINE     ")
    print("========================================")
    
    dq_passed = run_data_quality_checks()
    sc_passed = run_semantic_contract_checks()
    ev_passed = run_evidence_layer_checks()
    sh_passed = run_sparse_history_checks()
    bp_passed = run_business_pattern_checks()
    
    overall_passed = dq_passed and sc_passed and ev_passed and sh_passed and bp_passed
    
    print("\n========================================")
    print("           AUDIT SUMMARY REPORT         ")
    print("========================================")
    print(f"DATA QUALITY:       {'PASS' if dq_passed else 'FAIL'}")
    print(f"SEMANTIC CONTRACT:  {'PASS' if sc_passed else 'FAIL'}")
    print(f"EVIDENCE LAYER:     {'PASS' if ev_passed else 'FAIL'}")
    print(f"SPARSE HISTORY:     {'PASS' if sh_passed else 'FAIL'}")
    print(f"BUSINESS PATTERN:   {'PASS' if bp_passed else 'FAIL'}")
    print("----------------------------------------")
    print(f"OVERALL STATUS:     {'PASS' if overall_passed else 'FAIL'}")
    print("========================================")
    
    if not overall_passed:
        exit(1)

if __name__ == "__main__":
    main()
