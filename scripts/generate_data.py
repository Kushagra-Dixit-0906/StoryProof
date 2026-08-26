import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def main():
    # 1. Setup paths and seed
    np.random.seed(42)
    
    data_dir = "data"
    unstructured_dir = os.path.join(data_dir, "unstructured")
    os.makedirs(unstructured_dir, exist_ok=True)
    
    # Simulation range: 2026-01-01 to 2026-06-30 (181 days)
    start_date = datetime(2026, 1, 1)
    end_date = datetime(2026, 6, 30)
    total_days = (end_date - start_date).days + 1
    date_list = [start_date + timedelta(days=x) for x in range(total_days)]
    
    regions = ['North', 'South', 'East', 'West']
    products = ['Core ERP', 'CRM Cloud', 'Analytics Suite']
    segments = ['Enterprise', 'Mid-Market', 'SMB']
    teams = ['Alpha', 'Beta', 'Gamma']
    
    # --- SOURCE 1: SUPPORT OPERATIONS (DAILY) ---
    daily_records = []
    
    # Loop over dates
    for d in date_list:
        date_str = d.strftime('%Y-%m-%d')
        is_weekend = d.weekday() >= 5
        
        # AI Rollout probability check
        # Starts gradually after April 1st, 2026
        if d < datetime(2026, 4, 1):
            rollout_prob = 0.0
        elif d < datetime(2026, 5, 1):
            # April: ~30% rollout
            rollout_prob = 0.30
        elif d < datetime(2026, 6, 1):
            # May: ~60% rollout
            rollout_prob = 0.60
        else:
            # June: ~85% rollout
            rollout_prob = 0.85
            
        for reg in regions:
            for prod in products:
                for seg in segments:
                    for team in teams:
                        # Define contact volume based on segment
                        if seg == 'Enterprise':
                            base_contacts = np.random.randint(3, 8)
                        elif seg == 'Mid-Market':
                            base_contacts = np.random.randint(12, 28)
                        else: # SMB
                            base_contacts = np.random.randint(35, 75)
                            
                        # Apply weekend seasonality (70% lower on weekends)
                        if is_weekend:
                            base_contacts = int(base_contacts * 0.3)
                            
                        # Apply regional scale
                        if reg == 'North':
                            base_contacts = int(base_contacts * 1.2)
                        elif reg == 'East':
                            base_contacts = int(base_contacts * 0.8)
                            
                        # Small random variation
                        contacts = max(1, base_contacts + np.random.randint(-2, 3))
                        
                        # Determine AI vs non-AI split using binomial
                        if rollout_prob > 0:
                            ai_contacts = np.random.binomial(contacts, rollout_prob)
                        else:
                            ai_contacts = 0
                            
                        non_ai_contacts = contacts - ai_contacts
                        
                        # We create two records if both exist
                        buckets = []
                        if non_ai_contacts > 0:
                            buckets.append((non_ai_contacts, False))
                        if ai_contacts > 0:
                            buckets.append((ai_contacts, True))
                            
                        for c_count, is_ai in buckets:
                            # 98% resolved rate
                            resolved = max(1, c_count - np.random.binomial(c_count, 0.02))
                            
                            # AHT Baseline calculation (seconds)
                            # ERP is simpler, Analytics is complex
                            if prod == 'Core ERP':
                                base_aht = 450
                            elif prod == 'CRM Cloud':
                                base_aht = 600
                            else: # Analytics Suite
                                base_aht = 780
                                
                            # AI reduces AHT by approx 51% (multiplier 0.49)
                            if is_ai:
                                AHT = base_aht * 0.49
                            else:
                                AHT = base_aht
                                
                            # Add team variance
                            if team == 'Beta':
                                AHT *= 0.95
                            elif team == 'Gamma':
                                AHT *= 1.05
                                
                            # Add some random normal noise to AHT
                            AHT = max(60.0, np.random.normal(AHT, 30.0))
                            total_handling_seconds = int(AHT * resolved)
                            
                            # First Contact Resolution (FCR)
                            # Base FCR: ERP=75%, CRM=70%, Analytics=60%
                            if prod == 'Core ERP':
                                fcr_rate = 0.75
                            elif prod == 'CRM Cloud':
                                fcr_rate = 0.70
                            else:
                                fcr_rate = 0.60
                                
                            # AI has roughly flat FCR (no improvement)
                            if is_ai:
                                fcr_rate -= 0.01 # slight drop
                                
                            fcr_count = np.random.binomial(c_count, fcr_rate)
                            fcr_count = min(fcr_count, resolved)
                            
                            # Repeat Contacts
                            # Base Repeat Contact Rate: ERP=12%, CRM=15%, Analytics=22%
                            if prod == 'Core ERP':
                                repeat_rate = 0.12
                            elif prod == 'CRM Cloud':
                                repeat_rate = 0.15
                            else:
                                repeat_rate = 0.22
                                
                            # AI support increases Repeat Contact Rate dramatically (approx doubles)
                            if is_ai:
                                repeat_rate *= 2.0
                                
                            repeat_count = np.random.binomial(c_count, min(0.9, repeat_rate))
                            
                            daily_records.append({
                                'date': date_str,
                                'region': reg,
                                'product': prod,
                                'customer_segment': seg,
                                'agent_team': team,
                                'ai_assisted': is_ai,
                                'contacts': c_count,
                                'resolved_contacts': resolved,
                                'first_contact_resolutions': fcr_count,
                                'repeat_contacts': repeat_count,
                                'total_handling_seconds': total_handling_seconds
                            })
                            
    support_df = pd.DataFrame(daily_records)
    support_df.to_csv(os.path.join(data_dir, "support_daily.csv"), index=False)
    print(f"Generated support_daily.csv: {len(support_df)} rows")
    
    # --- SOURCE 2: CUSTOMER EXPERIENCE (WEEKLY) ---
    # Group daily support data to get weekly aggregates for computing CSAT
    support_df['date_dt'] = pd.to_datetime(support_df['date'])
    # Monday of the week
    support_df['week_start'] = support_df['date_dt'] - pd.to_timedelta(support_df['date_dt'].dt.weekday, unit='D')
    
    weekly_groups = support_df.groupby(['week_start', 'region', 'product', 'customer_segment'])
    
    cx_records = []
    for (wk, reg, prod, seg), group in weekly_groups:
        total_contacts = group['contacts'].sum()
        ai_contacts = group.loc[group['ai_assisted'] == True, 'contacts'].sum()
        ai_prop = ai_contacts / total_contacts if total_contacts > 0 else 0.0
        
        # 10% response rate for CSAT surveys
        survey_responses = max(1, int(np.random.normal(total_contacts * 0.12, total_contacts * 0.02)))
        
        # Base CSAT: ERP=84%, CRM=80%, Analytics=74%
        if prod == 'Core ERP':
            base_csat = 84.0
        elif prod == 'CRM Cloud':
            base_csat = 80.0
        else:
            base_csat = 74.0
            
        # Segment CSAT offset (Enterprise has higher expectations, SMB lower, etc.)
        if seg == 'Enterprise':
            base_csat += 1.0
        elif seg == 'SMB':
            base_csat -= 1.5
            
        # AI drop on CSAT: drops by up to 9 percentage points if 100% AI
        ai_drop = ai_prop * 9.0
        
        # Confounding factor: CRM Cloud has an unrelated buggy software update in May/June
        confounding_drop = 0.0
        if prod == 'CRM Cloud' and wk >= pd.Timestamp('2026-05-01'):
            confounding_drop = 6.5 # drops CSAT independently
            
        # Compute CSAT score with normal noise
        noise = np.random.normal(0, 1.5)
        csat_score = base_csat - ai_drop - confounding_drop + noise
        csat_score = min(100.0, max(20.0, csat_score))
        
        cx_records.append({
            'week_start': wk.strftime('%Y-%m-%d'),
            'region': reg,
            'product': prod,
            'customer_segment': seg,
            'survey_responses': survey_responses,
            'csat_score': round(csat_score, 1)
        })
        
    cx_df = pd.DataFrame(cx_records)
    cx_df.to_csv(os.path.join(data_dir, "cx_weekly.csv"), index=False)
    print(f"Generated cx_weekly.csv: {len(cx_df)} rows")
    
    # --- SOURCE 3: CRM (MONTHLY) ---
    # Group CX data by month, region, segment to calculate monthly CSAT-driven retention
    cx_df['week_start_dt'] = pd.to_datetime(cx_df['week_start'])
    cx_df['month'] = cx_df['week_start_dt'].dt.strftime('%Y-%m')
    
    # Calculate monthly average CSAT per region & segment
    monthly_csat = cx_df.groupby(['month', 'region', 'customer_segment'])['csat_score'].mean().reset_index()
    
    crm_records = []
    months = sorted(list(support_df['date_dt'].dt.strftime('%Y-%m').unique()))
    
    for m in months:
        for reg in regions:
            for seg in segments:
                # Active customers base
                if seg == 'Enterprise':
                    active_base = 120
                elif seg == 'Mid-Market':
                    active_base = 650
                else: # SMB
                    active_base = 3200
                    
                # Region multiplier
                if reg == 'North':
                    active_base = int(active_base * 1.25)
                elif reg == 'East':
                    active_base = int(active_base * 0.85)
                    
                # Fluctuate monthly active customers (some growth)
                month_idx = months.index(m)
                active_customers = int(active_base * (1.0 + 0.008 * month_idx) + np.random.randint(-10, 11))
                
                # Base retention rate: Enterprise=99.2%, Mid-Market=97.8%, SMB=95.5%
                if seg == 'Enterprise':
                    base_ret = 0.992
                elif seg == 'Mid-Market':
                    base_ret = 0.978
                else:
                    base_ret = 0.955
                    
                # Find matching CSAT for this month, region, segment
                match_csat = monthly_csat[(monthly_csat['month'] == m) & 
                                          (monthly_csat['region'] == reg) & 
                                          (monthly_csat['customer_segment'] == seg)]
                
                if len(match_csat) > 0:
                    avg_csat = match_csat['csat_score'].values[0]
                else:
                    avg_csat = 80.0 # fallback
                    
                # CSAT impact on retention:
                # CSAT baseline is around 81%. For every 1 percentage point CSAT drops below 81%, 
                # retention drops by 0.15 percentage points (0.0015).
                csat_diff = avg_csat - 81.0
                retention_rate = base_ret + (csat_diff * 0.0012)
                
                # Cap retention rate
                retention_rate = min(0.999, max(0.80, retention_rate))
                
                retained_customers = int(active_customers * retention_rate)
                # Random tiny noise in count
                retained_customers = min(active_customers, max(0, retained_customers + np.random.randint(-2, 3)))
                
                crm_records.append({
                    'month': m,
                    'region': reg,
                    'customer_segment': seg,
                    'active_customers': active_customers,
                    'retained_customers': retained_customers
                })
                
    crm_df = pd.DataFrame(crm_records)
    crm_df.to_csv(os.path.join(data_dir, "crm_monthly.csv"), index=False)
    print(f"Generated crm_monthly.csv: {len(crm_df)} rows")
    
    # --- SOURCE 5: SPARSE-HISTORY SCENARIO (AI RESOLUTION RATE) ---
    # 21 days of history: 2026-06-10 to 2026-06-30
    sparse_records = []
    sparse_start = datetime(2026, 6, 10)
    sparse_days = (end_date - sparse_start).days + 1
    sparse_date_list = [sparse_start + timedelta(days=x) for x in range(sparse_days)]
    
    for sd in sparse_date_list:
        sd_str = sd.strftime('%Y-%m-%d')
        for reg in regions:
            for prod in products:
                # AI resolution rate is a newly measured metric
                # Fluctuate around 72% to 80%
                rate = round(np.random.normal(76.0, 2.5), 2)
                sparse_records.append({
                    'date': sd_str,
                    'region': reg,
                    'product': prod,
                    'ai_resolution_rate': rate
                })
                
    sparse_df = pd.DataFrame(sparse_records)
    sparse_df.to_csv(os.path.join(data_dir, "ai_resolution_rate.csv"), index=False)
    print(f"Generated ai_resolution_rate.csv: {len(sparse_df)} rows")
    
    # --- SOURCE 4: UNSTRUCTURED EVIDENCE (TXT FILES) ---
    
    # A) support_transcripts.txt
    transcripts = """[TRANSCRIPT - 2026-04-12] Support ID: MM-9801
Agent: Auto-Assistant-v1.2 (AI)
Customer Segment: Mid-Market
Product: CRM Cloud
Query: Customer wants to add three new licenses to CRM Cloud account.
Auto-Assistant-v1.2: I have found your account details. To add licenses, please navigate to Account Settings > Billing > Manage Licenses. Is there anything else I can help with?
Customer: Wait, I tried that but the Billing tab is greyed out.
Auto-Assistant-v1.2: To manage licenses, navigate to Billing. Thank you for contacting customer support. Session closed.
[EXPLANATORY NOTE: Total handling time was 35 seconds (FCR logged: Yes, but customer called back 5 minutes later).]

[TRANSCRIPT - 2026-04-28] Support ID: ENT-3204
Agent: Team Alpha - Sarah
Customer Segment: Enterprise
Product: Core ERP
Query: Severe system crash during ERP batch export.
Sarah: Hello, I see you are having trouble with your ERP database export. Let me pull up your database replication records.
Customer: Yes, we are locked out of the inventory table.
Sarah: Understood. Let me execute a manual table release. This should clear the lock. Please try now.
Customer: Yes! It works now. Thank you, Sarah. That was fast.
Sarah: Happy to help! FCR recorded. Total handling time: 420 seconds.

[TRANSCRIPT - 2026-05-14] Support ID: SMB-4412
Agent: Auto-Assistant-v1.2 (AI)
Customer Segment: SMB
Product: Analytics Suite
Query: Need to connect Analytics dashboard to PostgreSQL database.
Auto-Assistant-v1.2: To connect to PostgreSQL, select 'Add Data Source', select PostgreSQL, and input host, port, username, password. This is a common setup. Closing ticket.
Customer: But it is throwing error code 403. I need to know if it is a firewall issue on your side.
Auto-Assistant-v1.2: I have answered your question. Closing ticket.
[EXPLANATORY NOTE: Handling time: 18 seconds. Customer logged repeat contact under ID SMB-4415 within 10 minutes.]

[TRANSCRIPT - 2026-05-22] Support ID: MM-1049
Agent: Auto-Assistant-v1.2 (AI)
Customer Segment: Mid-Market
Product: CRM Cloud
Query: CRM contact sync fails with error "Entity is too large".
Auto-Assistant-v1.2: Please ensure your payload size is under 5MB. If you are syncing contact records, clean the database.
Customer: I tried cleaning but we have custom fields. Does the AI assistant know about CRM Cloud bug 2026-05?
Auto-Assistant-v1.2:payload size under 5MB is required. Resolving ticket.
Customer: This is useless. I need a human agent.
[EXPLANATORY NOTE: Handling time: 45 seconds. Ticket closed automatically. Customer opened repeat ticket.]

[TRANSCRIPT - 2026-06-05] Support ID: ENT-4110
Agent: Team Gamma - Marcus
Customer Segment: Enterprise
Product: CRM Cloud
Query: Bug in CRM contact upload since the May system update.
Marcus: Hello, Marcus here. Yes, we are aware of a software issue introduced in the May CRM Cloud core patch. It's affecting contact sync.
Customer: Good, at least a human knows. The chatbot told me to clean my database, which wasted 3 hours of my team's time.
Marcus: Apologies for that. The automated assistant follows a standard size-limit protocol and is not aware of current patches. We are testing a bug fix this week.
Customer: Okay. Please transfer us to manual support in the future.
Marcus: I will flag your enterprise account. FCR: No. Handling time: 820 seconds.
"""
    with open(os.path.join(unstructured_dir, "support_transcripts.txt"), "w", encoding="utf-8") as f:
        f.write(transcripts.strip())
        
    # B) customer_feedback.txt
    feedback = """CSAT Survey Comment - Date: 2026-01-15 - Segment: SMB - Rating: 5/5
"Support was quick and solved my ERP issue immediately. Great job."

CSAT Survey Comment - Date: 2026-04-18 - Segment: Mid-Market - Rating: 2/5
"The new instant chat tool responds in seconds, but it just closes the chat without actually fixing the problem. I had to open three separate tickets for the same issue."

CSAT Survey Comment - Date: 2026-05-09 - Segment: Enterprise - Rating: 1/5
"Extremely disappointed. Our ERP connection went down. We got instant bot replies that didn't understand the database locking mechanism. We need manual engineering support for Enterprise accounts, not AI wrappers."

CSAT Survey Comment - Date: 2026-05-28 - Segment: Mid-Market - Rating: 2/5
"CRM Cloud has been buggy since the May release. The support bot tried to close the ticket instantly by telling us to clear our cache. Wasted a lot of time."

CSAT Survey Comment - Date: 2026-06-12 - Segment: SMB - Rating: 3/5
"Chat response is very fast now. But the answers are too generic. Often have to contact support multiple times to get a working solution."

CSAT Survey Comment - Date: 2026-06-25 - Segment: Enterprise - Rating: 2/5
"Why can't we bypass the automated chat assistant? For complex analytical issues, it has a 0% success rate. FCR is flat because it claims it resolved it, but we have to call back."
"""
    with open(os.path.join(unstructured_dir, "customer_feedback.txt"), "w", encoding="utf-8") as f:
        f.write(feedback.strip())
        
    # C) rollout_report.txt
    rollout_report = """PROJECT QUICKRESOLVE: OPERATIONAL ROLLOUT STATUS REPORT
Document Ref: QR-2026-Q2
Date: June 30, 2026
Prepared By: Support Operations & Automation Team

EXECUTIVE SUMMARY:
Project QuickResolve was initiated in Q1 2026 to address rising support volumes and optimize operational cost structures. The core initiative involves deploying Auto-Assistant-v1.2 (AI) across all regions, products, and customer segments.

TIMELINE & ADOPTION SCHEDULE:
- January - February 2026: Pre-rollout baseline monitoring. Support operations fully manual.
- March 2026: Alpha testing (pilot phase) with a restricted 1% customer cohort.
- April 1st, 2026: Official Phase 1 Launch. Target adoption: 30% of incoming contacts.
- May 1st, 2026: Phase 2 Launch. Target adoption: 60% of incoming contacts.
- June 1st, 2026: Phase 3 Launch (Full Rollout). Target adoption: 85% of incoming contacts.

OPERATIONAL IMPACT METRICS (Q2 AGGREGATE):
1. Average Handling Time (AHT):
   AHT has decreased dramatically from a baseline of ~10.2 minutes (612s) to ~5.6 minutes (336s) for AI-assisted contacts, representing a 45% reduction in handling time. Overall queue times have dropped by 60%.
2. First Contact Resolution (FCR):
   FCR remains stable near the historical baseline of 70%. The Auto-Assistant logs a "resolution" status once standard troubleshooting instructions are supplied.
3. Repeat Contact Volume:
   Operations has noted a 2x increase in the volume of repeat contact tickets within 48 hours of initial closure.
4. Confounding Factors:
   Separately, a CRM Cloud product software patch deployed on May 4th, 2026, has introduced a known contact-sync issue, which has driven a volume surge in May and June.
"""
    with open(os.path.join(unstructured_dir, "rollout_report.txt"), "w", encoding="utf-8") as f:
        f.write(rollout_report.strip())
        
    print("Generated all simulated datasets successfully!")

if __name__ == "__main__":
    main()
