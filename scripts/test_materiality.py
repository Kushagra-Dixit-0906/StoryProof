import os
import sys
from src.engine.materiality import analyze_kpi_change, load_yaml

BASELINE_PERIOD = ("2026-01-01", "2026-03-31")
COMPARISON_PERIOD = ("2026-06-01", "2026-06-30")
CONFIG_PATH = "config/kpi_definitions.yaml"
DATA_DIR = "data"

def format_value(kpi_name, val):
    if val is None:
        return "N/A"
    if kpi_name == "AHT":
        return f"{val:.2f} minutes"
    elif kpi_name == "CSAT":
        return f"{val:.1f} points"
    elif kpi_name in ["FCR", "Repeat_Contact_Rate", "Retention_Rate", "AI_Resolution_Rate"]:
        # Keep fractions displayed as percentages
        return f"{val * 100.0:.2f}%" if kpi_name == "Retention_Rate" else f"{val * 100.0:.1f}%"
    return f"{val:.2f}"

def format_change(kpi_name, abs_change, rel_change_pct):
    if abs_change is None or rel_change_pct is None:
        return "N/A"
    
    if kpi_name == "CSAT":
        return f"{abs_change:+.1f} points ({rel_change_pct:+.1f}%)"
    elif kpi_name == "AHT":
        return f"{abs_change:+.2f} minutes ({rel_change_pct:+.1f}%)"
    elif kpi_name == "Retention_Rate":
        return f"{abs_change * 100.0:+.2f} percentage points ({rel_change_pct:+.1f}%)"
    elif kpi_name in ["FCR", "Repeat_Contact_Rate", "AI_Resolution_Rate"]:
        return f"{abs_change * 100.0:+.1f} percentage points ({rel_change_pct:+.1f}%)"
    
    return f"{abs_change:+.2f} ({rel_change_pct:+.1f}%)"

def main():
    print("==================================================")
    print("STORYPROOF MATERIALITY ENGINE — 3A")
    print("==================================================")
    
    try:
        kpi_definitions = load_yaml(CONFIG_PATH)
    except Exception as e:
        print(f"Failed to load KPI definitions: {e}")
        sys.exit(1)
        
    kpis = ["AHT", "FCR", "CSAT", "Repeat_Contact_Rate", "Retention_Rate", "AI_Resolution_Rate"]
    
    for kpi in kpis:
        try:
            res = analyze_kpi_change(kpi, kpi_definitions, DATA_DIR, BASELINE_PERIOD, COMPARISON_PERIOD)
            
            if res["status"] == "INSUFFICIENT_HISTORY":
                print(f"KPI: {res['kpi_name']}")
                print(f"Status: {res['status']}")
                reason = res["warnings"][0] if res["warnings"] else "Insufficient baseline observations."
                print(f"Reason: {reason}")
            else:
                print(f"KPI: {res['kpi_name']}")
                baseline_val = format_value(kpi, res['baseline']['value'])
                comp_val = format_value(kpi, res['comparison']['value'])
                change_str = format_change(kpi, res['change']['absolute'], res['change']['relative_percent'])
                
                print(f"Baseline: {baseline_val}")
                print(f"Current: {comp_val}")
                print(f"Change: {change_str}")
                print(f"Materiality: {res['status']}")
                
                # Format statistical signal
                z_val = res['statistical_signal']['z_score']
                z_str = f"{z_val:.2f}" if z_val is not None else "N/A"
                unusual_str = "YES" if res['statistical_signal']['unusual'] else "NO"
                print(f"Statistical Signal: Z-score = {z_str}, Unusual = {unusual_str}")
                
                history_str = "SUFFICIENT" if res['history']['sufficient'] else "INSUFFICIENT"
                print(f"History: {history_str}")
                
            print("-" * 50)
            
        except Exception as e:
            print(f"KPI: {kpi}")
            print(f"Error executing analysis: {e}")
            print("-" * 50)
            
    print("==================================================")

if __name__ == "__main__":
    main()
