import os
import sys
from src.engine.drivers import profile_driver, compare_ai_assisted
from src.engine.materiality import load_yaml

CONFIG_PATH = "config/kpi_definitions.yaml"
DATA_DIR = "data"

def print_profile_result(kpi_name, dimension, result):
    print("=" * 60)
    print(f"DRIVER PROFILE: {kpi_name} by {dimension}")
    print("=" * 60)
    
    if result["status"] != "SUCCESS":
        print(f"Status: {result['status']}")
        print(f"Reason: {result.get('reason')}")
        print("-" * 60)
        return
        
    prov = result["provenance"]
    print(f"Dataset:    {prov['source_dataset']}")
    print(f"Baseline:   {prov['baseline_period'][0]} to {prov['baseline_period'][1]}")
    print(f"Comparison: {prov['comparison_period'][0]} to {prov['comparison_period'][1]}")
    print(f"Agg Method: {prov['aggregation_method']}")
    print("-" * 60)
    print(f"Global Baseline:   {result['global_baseline']:.6f}")
    print(f"Global Comparison: {result['global_comparison']:.6f}")
    print(f"Overall Change:    {result['overall_change']:+.6f}")
    print("-" * 60)
    
    print(f"{'Rank':<5} | {'Value':<18} | {'Base Exp':<8} | {'Comp Exp':<8} | {'Rate Eff':<10} | {'Mix Eff':<10} | {'Contrib':<10}")
    print("-" * 80)
    for driver in result["drivers"]:
        print(f"{driver['rank']:<5} | "
              f"{driver['dimension_value']:<18} | "
              f"{driver['baseline_exposure']:<8.3f} | "
              f"{driver['comparison_exposure']:<8.3f} | "
              f"{driver['rate_effect']:<10.6f} | "
              f"{driver['mix_effect']:<10.6f} | "
              f"{driver['total_contribution']:<10.6f}")
              
    print("-" * 60)
    recon = result["reconciliation_info"]
    print(f"Sum of Contributions: {recon['sum_contributions']:.6f}")
    print(f"Reconciliation Error: {recon['reconciliation_error']:.6e}")
    print(f"Reconciled (error <= 1e-9): {recon['is_reconciled']}")
    print("=" * 60 + "\n")

def print_ai_comparison(result):
    print("=" * 60)
    print(f"AI-ASSISTED COMPARISON FOR: {result.get('kpi')}")
    print("=" * 60)
    
    if result["status"] != "SUCCESS":
        print(f"Status: {result['status']}")
        print(f"Reason: {result.get('reason')}")
        print("-" * 60)
        return
        
    for phase, res in result["phases"].items():
        print(f"Phase: {phase}")
        print("-" * 60)
        if res["status"] == "NO_AI_BASELINE":
            ai = res["ai_assisted"]
            non_ai = res["non_ai_assisted"]
            print(f"  AI-Assisted:     KPI = N/A | AI observations = {ai['contacts']} | Denom Exp = {ai['denominator_exposure']:.2%} | Contact Share = {ai['contact_share']:.2%}")
            print(f"  Non-AI-Assisted: KPI = {non_ai['kpi']:.4f} | Denom Exp = {non_ai['denominator_exposure']:.2%} | Contact Share = {non_ai['contact_share']:.2%}")
            print(f"  Difference:      Abs = N/A | Rel = N/A")
            print(f"  Status:          {res['status']}")
            print("-" * 60)
            continue
            
        if res["status"] != "SUCCESS":
            print(f"  Status: {res['status']}")
            print(f"  Reason: {res.get('reason')}")
            print("-" * 60)
            continue
            
        ai = res["ai_assisted"]
        non_ai = res["non_ai_assisted"]
        comp = res["comparison"]
        
        print(f"  AI-Assisted:     KPI = {ai['kpi']:.4f} | Denom Exp = {ai['denominator_exposure']:.2%} | Contact Share = {ai['contact_share']:.2%}")
        print(f"  Non-AI-Assisted: KPI = {non_ai['kpi']:.4f} | Denom Exp = {non_ai['denominator_exposure']:.2%} | Contact Share = {non_ai['contact_share']:.2%}")
        print(f"  Difference:      Abs = {comp['absolute_difference']:+.4f} | Rel = {comp['relative_difference']:+.2%}")
        print("-" * 60)
    print("=" * 60 + "\n")

def main():
    print("==================================================")
    print("STORYPROOF DRIVER RUNNER — MILESTONE 3B.1")
    print("==================================================")
    
    try:
        config = load_yaml(CONFIG_PATH)
    except Exception as e:
        print(f"Failed to load KPI definitions: {e}")
        sys.exit(1)
        
    baseline = ("2026-01-01", "2026-03-31")
    comparison = ("2026-06-01", "2026-06-30")
    
    # A. CSAT by product
    res_csat_prod = profile_driver("CSAT", "product", baseline, comparison, DATA_DIR, config)
    print_profile_result("CSAT", "product", res_csat_prod)
    
    # B. CSAT by customer segment
    res_csat_seg = profile_driver("CSAT", "customer_segment", baseline, comparison, DATA_DIR, config)
    print_profile_result("CSAT", "customer_segment", res_csat_seg)
    
    # C. AHT by AI-assisted state
    res_aht_ai = profile_driver("AHT", "ai_assisted", baseline, comparison, DATA_DIR, config)
    print_profile_result("AHT", "ai_assisted", res_aht_ai)
    
    # D. FCR by AI-assisted state
    res_fcr_ai = profile_driver("FCR", "ai_assisted", baseline, comparison, DATA_DIR, config)
    print_profile_result("FCR", "ai_assisted", res_fcr_ai)
    
    # E. Repeat Contact Rate by AI-assisted state
    res_rpt_ai = profile_driver("Repeat_Contact_Rate", "ai_assisted", baseline, comparison, DATA_DIR, config)
    print_profile_result("Repeat_Contact_Rate", "ai_assisted", res_rpt_ai)
    
    # F. Retention by customer segment
    res_ret_seg = profile_driver("Retention_Rate", "customer_segment", baseline, comparison, DATA_DIR, config)
    print_profile_result("Retention_Rate", "customer_segment", res_ret_seg)

    # G. AI-assisted comparison (Operational AHT)
    res_ai_comp_aht = compare_ai_assisted("AHT", DATA_DIR, config)
    print_ai_comparison(res_ai_comp_aht)
    
    # H. AI-assisted comparison (Operational FCR)
    res_ai_comp_fcr = compare_ai_assisted("FCR", DATA_DIR, config)
    print_ai_comparison(res_ai_comp_fcr)

    # I. AI-assisted comparison (Operational Repeat Contact Rate)
    res_ai_comp_rpt = compare_ai_assisted("Repeat_Contact_Rate", DATA_DIR, config)
    print_ai_comparison(res_ai_comp_rpt)

    # J. Unsupported dimension check (CSAT by ai_assisted -> ABSTAIN)
    res_csat_ai_abstain = profile_driver("CSAT", "ai_assisted", baseline, comparison, DATA_DIR, config)
    print_profile_result("CSAT", "ai_assisted", res_csat_ai_abstain)
    
    # K. Unsupported dimension check (CSAT AI-assisted comparison -> ABSTAIN)
    res_ai_comp_csat = compare_ai_assisted("CSAT", DATA_DIR, config)
    print_ai_comparison(res_ai_comp_csat)

    print("==================================================")
    print("RUN COMPLETED")
    print("==================================================")

if __name__ == "__main__":
    main()
