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
- [x] **Milestone 3B.1: Deterministic Driver & Contribution Analysis Core (v0.3b)**
  - Implement a deterministic, math-only driver profiler and mix-rate decomposition in `src/engine/drivers.py`.
  - Calculate exposure/denominator share and midpoint/Shapley-style decomposition (reconciling exactly to overall change within $10^{-9}$).
  - Implement driver signal ranking (`contribution_magnitude`) and separate AI-assisted operational comparison across rollout phases.
  - Enforce strict causality policy (avoiding causal verbs; separating Fact, Association, and Hypothesis) and data limitation guards/abstentions.
- [x] **Milestone 3B.2: Confounder & Hypotheses Analysis (v0.3.2)**
  - Implement a deterministic, evidence-synthesis engine in `src/engine/hypotheses.py` evaluating competing hypotheses (AI Rollout, CRM Cloud Patch, and Mix Shift).
  - Define concentration metrics for pre/post patch differential signal using a volume-weighted control group.
  - Implement mix share classification (LOW, MODERATE, HIGH) to isolate structural volume shifts.
  - Formulate a deterministic synthesis module mapping hypothesis strength and data limitations to overall evidence state.
  - Enforce strict Causality Policy, safety guards, and abstentions (CSAT/Retention by AI rollout -> `NOT_AVAILABLE`).
- [x] **Milestone 3C.1: Unstructured Evidence Ingestion & Provenance Layer (v0.3.3)**
  - Implement a deterministic evidence-ingestion layer in `src/engine/evidence.py` to parse qualitative support chat transcripts, survey reviews, and contextual rollout reports.
  - Implement robust path resolution checking relative to workspace and data directories.
  - Parse metadata (dates, segments, products, ratings, support IDs, agents) safely without inventing missing fields.
  - Preserves exact raw text and associates reproducible deterministic IDs (`source_key_index`) and provenance records.
- [x] **Milestone 3C.2: Qualitative Evidence Verification & Alignment (v0.3.4)**
  - Implement a deterministic qualitative evidence retrieval and linking layer in `src/engine/retrieval.py` supporting exact product, segment, and date-window matches.
  - Implement regex-based safe keyword matching (`\b` boundaries) and capped scoring (+3.0 max) to ensure auditable relevance calculation.
- [x] **Milestone 3C.3: Qualitative & Quantitative Narrative Synthesis (v0.3.5)**
  - Implement a deterministic, template-based narrative synthesis layer in `src/engine/synthesis.py` combining materiality (3A), drivers (3B.1), hypotheses (3B.2), and retrieved qualitative evidence (3C.2).
  - Enforce conservative evidence classification (FACT, ASSOCIATION, HYPOTHESIS, CONTEXT, LIMITATION) and strict causality safeguards (neutral verbs only, mandatory causality disclaimer).
  - Implement multi-KPI tension/contradiction detection and reporting to capture divergence between structured speedups and qualitative complaints.
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

---

## 🔬 Milestone 3B.2 — Competing Hypothesis Analysis

Milestone 3B.2 introduces a deterministic evidence-synthesis engine in `src/engine/hypotheses.py` to evaluate competing explanations for KPI shifts.

### Core Concepts

1. **Three Competing Hypotheses**:
   - **Hypothesis 1 — AI Rollout Association**: Analyzes whether the AI rollout is consistently associated with operational changes across phases (Q1, April, May, June). Checks for direction consistency and evaluates relative differences. Bounded by Q1 zero-AI baseline safety checks.
   - **Hypothesis 2 — CRM Cloud May-4 Patch**: Determines whether observed KPI movement was concentrated in CRM Cloud post-patch (`2026-05-04` through `2026-06-30`) compared with a control group of unaffected products. Computes a deterministic pre/post differential signal.
   - **Hypothesis 3 — Mix Shift**: Measures the proportion of the KPI shift mathematically attributable to volume/exposure changes across segments using Shapley-style decomposition. Classifies mix share as `LOW` (< 20%), `MODERATE` (20-50%), or `HIGH` (>= 50%).
2. **Ambiguity Handling**: Rather than choosing a single causal "winner" on observational data, StoryProof explicitly detects confounding. When multiple explanations (e.g. AI rollout and CRM patch) show moderate-to-strong associations or when CSAT cannot be split due to data limitations, the synthesis logic resolves to `INVESTIGATION_REQUIRED`.
3. **Abstention & Safety Guards**: The engine abstains (returning `NOT_AVAILABLE`) if required columns/dimensions are missing, baseline periods have zero observations, control groups are absent, or CSAT/Retention are queried by `ai_assisted` (which they do not support).
4. **Causality Policy**: Enforces non-causal verbs (`"associated with"`, `"consistent with"`, etc.) in all narrative signals and logs.

---

## 📂 Milestone 3C.1 — Unstructured Evidence Ingestion & Provenance Layer

Milestone 3C.1 introduces a deterministic evidence-ingestion layer in `src/engine/evidence.py` to convert qualitative support chat transcripts, survey reviews, and contextual rollout reports into structured evidence records.

### Core Concepts

1. **Deterministic Parsing**:
   - **Support Transcripts**: Splitted by block headers `[TRANSCRIPT - YYYY-MM-DD]`, extracting Date, Support ID, Agent, Customer Segment, and Product.
   - **Customer Feedback Comments**: Splitted by comment headers `CSAT Survey Comment - `, extracting Date, Customer Segment, and Rating.
   - **Rollout Status Report**: Parsed into discrete logical blocks representing Document Metadata, Executive Summary, Timeline & Adoption Schedule, and specific Operational Impact Metrics (including AHT, FCR, Repeat Contact, and Confounding CRM Cloud Patch details).
2. **Provenance Preservation**: Every single record contains a structured `provenance` dictionary mapping it back to its original filename (`file`) and `source_key` from `evidence_sources.yaml`. The original text is preserved exactly without paraphrasing.
3. **Deterministic ID Generation**: Reproducible IDs are generated using the `source_key_index` format, ensuring the same text files always yield the exact same evidence IDs.
4. **Safety & Abstention**: Missing optional metadata fields (e.g., segment or product) default to `None` rather than fabricated values. File absence and empty files are handled safely by returning `NOT_AVAILABLE` status results.
5. **No Causal Inference/LLMs**: Ingestion is strictly deterministic and read-only, laying the data provenance foundation for later qualitative verification. No sentiment analysis, semantic theme extraction, RAG, or causal assumptions are performed.

---

## 📂 Milestone 3C.2 — Qualitative Evidence Retrieval & Linking Layer

Milestone 3C.2 introduces a deterministic retrieval and linking layer in `src/engine/retrieval.py` to link qualitative evidence records to investigation findings.

### Core Concepts

1. **Deterministic Matching**: Filters and scores evidence records based on exact product and segment metadata alignment, target date windows, and complete word-boundary keyword checks.
2. **Deterministic Relevance Scoring**: Computes a transparent, auditable score where:
   - Exact Product Match = `+2.0`
   - Exact Segment Match = `+2.0`
   - Date Window Match = `+1.0`
   - Distinct Keyword Match = `+1.0` per matched term (capped at `+3.0` maximum)
   - Minimum Score Threshold = `1.0` (scores $< 1.0$ are excluded)
3. **Abstention & Ordering**: Excludes mismatching metadata and out-of-range dates, returning `NO_MATCH` if no record meets the minimum score threshold. Results are deterministically sorted by relevance score descending, then evidence ID ascending.
4. **Causality Safety**: Matches and reasons are generated using strictly observational, non-causal verbs, keeping provenance references preserved exactly.

---

## 📂 Milestone 3C.3 — Qualitative & Quantitative Narrative Synthesis

Milestone 3C.3 introduces a deterministic synthesis layer in `src/engine/synthesis.py` that formats materiality, driver, hypothesis, and qualitative findings into a fully traceable investigation report.

### Core Concepts

1. **Structured Narrative Schema**: Statements are formatted as structured dicts containing the narrative text, exactly one classification (`FACT`, `ASSOCIATION`, `HYPOTHESIS`, `CONTEXT`, `LIMITATION`), and references to structured findings (`structured_refs`) and qualitative evidence (`evidence_refs`).
2. **Conflict & Tension Detection**: When structured metrics show efficiency gains but qualitative feedback reports unresolved issues, the layer detects and explicitly details the tension (e.g., AHT operational speedup vs. premature ticket closure complaints) rather than suppressing either finding.
3. **Multi-KPI Synthesis**: Synthesizes findings across AHT, FCR, CSAT, Repeat Contact Rate, Retention Rate, and AI Resolution Rate while respecting their individual units, grains, thresholds, and insufficient history limitations.
4. **Causality Safeguards & Disclaimer**: Implements a strict causality-language guard (verifying no causal verbs like "caused", "resulted in", or "driven by" are present in generated statements) and appends a mandatory **Causality Disclaimer**: `"The available evidence does not establish causality; observed changes represent associations and candidate explanations only."`
5. **No Recalculation**: Preserves the exact values, statuses, and boundaries computed upstream in previous milestones (such as AI Resolution Rate's insufficient-history flag from 3A).
