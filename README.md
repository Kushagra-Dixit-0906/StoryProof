# StoryProof

> **"Don't just tell the story. Verify it."**

StoryProof is an evidence-first KPI intelligence-to-action engine built as a working prototype for the **Accenture Innovation Challenge 2026, Track 3: BusinessIntelligence.ai**. 

Traditional BI tells a business user *what* changed and may generate a plausible explanation. StoryProof adds a rigorous **evidence-verification layer** to authenticate explanations and quantify uncertainty before business decisions are made.

---

## 🏗️ Proposed Architecture

StoryProof is designed around the core principle that **Large Language Models (LLMs) must NOT be the source of quantitative truth**. All calculations, materiality checks, driver analyses, and confidence scoring are performed using deterministic Python code. The LLM's role is restricted to natural-language interpretation, narrative synthesis, and persona-specific communication using *only* the verified evidence provided.

Below is the modular project structure:

```text
storyproof/
│
├── .venv/                      # Python virtual environment
├── requirements.txt            # Project dependencies
├── README.md                   # Architecture and milestones documentation
├── app.py                      # Streamlit main entrypoint
│
└── src/                        # Core codebase
    ├── __init__.py
    │
    ├── data/                   # Data Simulation & Loading
    │   ├── __init__.py
    │   ├── simulator.py        # Illustrative Customer Support performance simulation
    │   └── loader.py           # Multi-source data reconciliation (Support, CX, CRM)
    │
    ├── engine/                 # Deterministic Analytics Engine
    │   ├── __init__.py
    │   ├── semantics.py        # KPI semantic definitions and formulas
    │   ├── materiality.py      # Statistical materiality & anomaly detection
    │   └── drivers.py          # Contribution & driver analysis (quantitative attribution)
    │
    ├── verification/           # Verification & Evidence Layer
    │   ├── __init__.py
    │   └── verifier.py         # Cross-references structured data with unstructured logs
    │
    ├── narrative/              # Narrative & Persona-Specific Synthesis
    │   ├── __init__.py
    │   ├── personas.py         # Persona configurations (CX vs. Operations)
    │   ├── generator.py        # Safe narrative synthesis (templated or LLM-driven)
    │   └── actions.py          # Action recommendation engine based on verified proof
    │
    └── feedback/               # Analyst Feedback & Observability
        ├── __init__.py
        └── handler.py          # Logging feedback to SQLite and tracking runtime metadata
```

---

## 📈 Core Analytical Flow

1. **DATA**: Daily support operations, weekly CX metrics, monthly CRM data, and unstructured logs.
2. **KPI SEMANTICS**: Structured relationship models connecting KPIs (AHT, FCR, CSAT, Repeat Contacts, Retention).
3. **MATERIAL CHANGE**: Detection of significant KPI shifts using statistical baselines.
4. **DRIVER ANALYSIS**: Attribution of changes to competing hypotheses (e.g., AI rollout, resolution quality, customer mix).
5. **EVIDENCE VERIFICATION**: Checking explanations against unstructured logs (e.g., customer transcripts).
6. **PERSONA-SPECIFIC STORY**: Formulating tailored narratives for different roles (CX Manager vs. Operations Manager).
7. **CONFIDENCE / ABSTENTION**: Emphasizing uncertainty and abstaining when evidence is conflicting or sparse.
8. **ACTION**: Recommending verified corrective actions.
9. **USER FEEDBACK**: Logging analyst corrections to improve the system.

---

## ⚖️ Causality Policy & Analytical Principles

StoryProof makes a strict distinction between quantitative correlations and causal claims. The analytics engine is designed to prevent hasty causal assertions:

*   **OBSERVATION (Fact)**: High-resolution quantitative changes measured directly (e.g., *"AI-assisted support contacts show a 51% drop in handling time."*).
*   **ASSOCIATION (Correlation)**: A statistical overlap between two patterns (e.g., *"An increase in AI-assisted contact share correlates with a drop in CSAT."*).
*   **HYPOTHESIS (Potential Driver)**: A candidate explanation under investigation (e.g., *"Reduced resolution quality from AI containment may drive CSAT deterioration."*).
*   **CONFOUNDING FACTOR (Alternative Explanation)**: Independent external forces (e.g., *"CRM Cloud release bug in May represents a competing explanation for CSAT decline."*).
*   **CAUSAL CLAIM (Unverified)**: Observational data alone is insufficient to assert causality. StoryProof demands cross-validation of structured metrics against unstructured transcripts and status reports before classifying an explanation.

---

## 🏁 Development Milestones

- [x] **Milestone 1: Project Architecture & Skeleton (v0.1)**
  - Establish modular folder structure.
  - Create standard Streamlit entrypoint and requirements.
- [x] **Milestone 2: Data Simulation & KPI Semantics (v0.2)**
  - Generate simulated multi-source customer support datasets containing the baseline and AI-assisted rollout periods.
  - Write deterministic KPI calculation and materiality baseline tests.
- [x] **Milestone 3A: Materiality & Change Detection Engine (v0.3a)**
  - Implement a deterministic, math-only KPI parser and materiality detector in `src/engine/materiality.py`.
  - Calculate period changes respecting ratio-aggregation semantics and configured units (minutes for AHT, percentage points for FCR,CSAT,Repeat,Retention).
  - Model historical variation at the natural grain (daily/weekly/monthly) and standard deviation/z-scores.
  - Separate business materiality from statistical volatility.
  - Enforce minimum history requirements (abstaining on sparse data like AI Resolution Rate).
- [ ] **Milestone 3B: Driver Analysis**
- [ ] **Milestone 3C: Evidence Verification**
- [ ] **Milestone 4: Persona Narratives & Decision Flags (v0.4)**
  - Add narrative generation engine matching CX Manager (customer health focus) and Operations Manager (cost/efficiency focus).
  - Implement the three-tier decision readiness flag: `GREEN` (Decision-Ready), `YELLOW` (Investigation Required), `RED` (Not Justified).
- [ ] **Milestone 5: Interactive Dashboard & Polish (v1.0)**
  - Design the visual comparison: Traditional BI View vs. StoryProof Verification View.
  - Embed feedback collection, security/access controls simulation, and observability dashboard (latency, LLM cost projection).
## ⚖️ Milestone 3A — Materiality & Change Detection Engine

StoryProof's Materiality Engine is a deterministic analytical layer that acts as the first gate in decision intelligence: determining whether a KPI change is meaningful and whether there is sufficient history to analyze it.

### Core Concepts

1. **Business Materiality**: Determined by comparing the change against configured business thresholds from `kpi_definitions.yaml`. If the KPI change crosses the threshold, it is classified as `MATERIAL`; otherwise, it is `NOT_MATERIAL`.
2. **Statistical Unusualness**: Measures whether a change is standard behavior or an anomaly relative to historical volatility. The engine builds a time series of baseline data grouped at the KPI's natural grain and computes the historical standard deviation. The standardized deviation of the comparison period value (Z-score) is calculated. If $|Z| \ge 2.0$, the change is flagged as `unusual`.
3. **Isolation of Concepts**: Materiality and Statistical Unusualness are kept separate:
   - **Material & Unusual** (e.g. CSAT): High confidence signal of meaningful shift.
   - **Material & Not Unusual** (e.g. highly volatile metric crossing a low threshold): Shift crossed the business line but lies within normal historical variance.
   - **Not Material & Unusual** (e.g. stable metric with a tiny shift): Statistically anomalous movement, but too small to matter to the business.
4. **Natural KPI Grain Grouping**: Standard deviation calculations respect the KPI grain rather than raw transaction rows:
   - *Daily* grain for AHT, FCR, Repeat Contact Rate, and AI Resolution Rate.
   - *Weekly* grain for CSAT.
   - *Monthly* grain for Retention Rate.
5. **History Validation and Abstention**: The engine enforces the `minimum_history_days` contract. KPIs with sparse data (e.g., AI Resolution Rate with only 21 days out of 60 required) are marked as `INSUFFICIENT_HISTORY` and the engine abstains from making decisions.
6. **No Causal Assumptions**: This layer is strictly quantitative. It reports numerical change facts, thresholds, and statistical significance. It does *not* query LLMs, read textual reports, or make causal inferences (e.g., it will not state that the AI rollout *caused* a CSAT decline).

---

## 🚀 Running the App (v0.1)

### 1. Set Up Environment
```bash
python -m venv .venv
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Streamlit
```bash
streamlit run app.py
```
