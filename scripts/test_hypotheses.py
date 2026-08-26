import os
import sys
from src.engine.hypotheses import synthesize_hypotheses
from src.engine.materiality import load_yaml

CONFIG_PATH = "config/kpi_definitions.yaml"
DATA_DIR = "data"

def print_hypothesis_report(result):
    kpi = result["kpi"]
    h1 = result["hypotheses"]["ai_rollout"]
    h2 = result["hypotheses"]["crm_patch"]
    h3 = result["hypotheses"]["mix_shift"]

    print("=" * 60)
    print(f"STORYPROOF INVESTIGATION ENGINE — 3B.2")
    print(f"KPI: {kpi}")
    print("=" * 60)

    # Hypothesis 1: AI Rollout
    print("\nHYPOTHESIS 1 — AI ROLLOUT")
    print("-" * 35)
    if h1["status"] == "NOT_AVAILABLE":
        print(f"Status:          {h1['status']}")
        print(f"Reason:          {h1['reason']}")
        print(f"Limitations:     {', '.join(h1['limiting_signals'])}")
    else:
        for phase_name, phase_data in h1["phases"].items():
            print(f"Phase: {phase_name}")
            if phase_data["status"] == "NO_AI_BASELINE":
                print(f"  AI KPI:          N/A")
                print(f"  AI observations: 0")
                print(f"  Manual KPI:      {phase_data['non_ai_assisted']['kpi']:.4f}")
                print(f"  Difference:      N/A")
                print(f"  Status:          {phase_data['status']}")
            elif phase_data["status"] == "SUCCESS":
                ai = phase_data["ai_assisted"]
                non_ai = phase_data["non_ai_assisted"]
                comp = phase_data["comparison"]
                print(f"  AI KPI:          {ai['kpi']:.4f}")
                print(f"  AI observations: {ai['contacts']}")
                print(f"  Manual KPI:      {non_ai['kpi']:.4f}")
                print(f"  Difference:      Abs = {comp['absolute_difference']:+.4f} | Rel = {comp['relative_difference']:+.2%}")
                print(f"  AI share:        {ai['contact_share']:.2%}")
            else:
                print(f"  Status:          {phase_data['status']}")
                print(f"  Reason:          {phase_data.get('reason')}")
            print()
        print(f"Association:     {h1['direction_consistency']}")
        print(f"Avg Rel Diff:    {h1['avg_relative_difference']:+.2%}" if h1['avg_relative_difference'] is not None else "Avg Rel Diff:    N/A")
        print(f"Strength:        {h1['evidence_strength']}")
        print(f"Supporting:      {', '.join(h1['supporting_signals'])}")
        print(f"Limitations:     {', '.join(h1['limiting_signals'])}")

    # Hypothesis 2: CRM Cloud Patch
    print("\nHYPOTHESIS 2 — CRM CLOUD PATCH")
    print("-" * 35)
    if h2["status"] == "NOT_AVAILABLE":
        print(f"Status:          {h2['status']}")
        print(f"Reason:          {h2['reason']}")
    else:
        print(f"Pre-patch (CRM):  {h2['crm_pre']:.4f}")
        print(f"Post-patch (CRM): {h2['crm_post']:.4f}")
        print(f"CRM Cloud change: {h2['crm_change']:+.4f}")
        print(f"Control change:   {h2['control_change']:+.4f}")
        print(f"Differential association signal: {h2['differential_signal']:+.4f}")
        print(f"Classification:   {h2['classification']}")
        print(f"Strength:        {h2['evidence_strength']}")
        print(f"Supporting:      {', '.join(h2['supporting_signals'])}")
        print(f"Limitations:     {', '.join(h2['limiting_signals'])}")

    # Hypothesis 3: Mix Shift
    print("\nHYPOTHESIS 3 — MIX SHIFT")
    print("-" * 35)
    if h3["status"] == "NOT_AVAILABLE":
        print(f"Status:          {h3['status']}")
        print(f"Reason:          {h3['reason']}")
    else:
        print(f"Dimension:        {h3['dimension']}")
        print(f"Overall change:   {h3['overall_change']:+.4f}")
        print(f"Rate effect:      {h3['total_rate_effect']:+.4f}")
        print(f"Mix effect:       {h3['total_mix_effect']:+.4f}")
        print(f"Mix share:        {h3['mix_share']:.2%}")
        print(f"Classification:   {h3['classification']}")
        print(f"Strength:        {h3['evidence_strength']}")
        print(f"Supporting:      {', '.join(h3['supporting_signals'])}")
        print(f"Limitations:     {', '.join(h3['limiting_signals'])}")

    # Hypothesis Synthesis & Overall State
    print("\nHYPOTHESIS SYNTHESIS")
    print("-" * 35)
    print(f"AI rollout:       {h1['evidence_strength']}")
    print(f"CRM patch:        {h2['evidence_strength']}")
    print(f"Mix shift:        {h3['evidence_strength']}")
    print(f"\nOVERALL EVIDENCE STATE: {result['overall_evidence_state']}")
    print(f"REASON:\n{result['reason']}")
    print("=" * 60 + "\n")

def main():
    if not os.path.exists(CONFIG_PATH):
        print(f"Error: configuration file '{CONFIG_PATH}' not found.")
        sys.exit(1)
        
    config = load_yaml(CONFIG_PATH)
    
    baseline = ("2026-01-01", "2026-03-31")
    comparison = ("2026-06-01", "2026-06-30")

    # Run for key operational KPIs
    aht_res = synthesize_hypotheses("AHT", DATA_DIR, config, baseline, comparison, "product")
    print_hypothesis_report(aht_res)

    fcr_res = synthesize_hypotheses("FCR", DATA_DIR, config, baseline, comparison, "customer_segment")
    print_hypothesis_report(fcr_res)

    repeat_res = synthesize_hypotheses("Repeat_Contact_Rate", DATA_DIR, config, baseline, comparison, "region")
    print_hypothesis_report(repeat_res)

    # Run for CSAT (outcome KPI)
    csat_res = synthesize_hypotheses("CSAT", DATA_DIR, config, baseline, comparison, "product")
    print_hypothesis_report(csat_res)

if __name__ == "__main__":
    main()
