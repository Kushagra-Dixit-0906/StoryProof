# StoryProof

> **"Don't just tell the story. Verify it."**

StoryProof is an evidence-first KPI intelligence-to-action engine built as a working prototype for the **Accenture Innovation Challenge 2026, Track 3: BusinessIntelligence.ai**.

Traditional BI primarily answers **what changed**. StoryProof adds an evidence-verification and decision-readiness layer that evaluates whether a plausible explanation is actually supported by available quantitative and qualitative evidence before an operational recommendation is made.

---

## 1. What StoryProof Does

StoryProof is designed around a simple principle:

> **A KPI movement is not automatically an explanation, and an explanation is not automatically a decision.**

The system therefore moves through five analytical stages:

1. **Observe** KPI movements and detect material changes.
2. **Explain** changes through deterministic driver decomposition.
3. **Challenge** the leading explanation using competing hypotheses and confounders.
4. **Verify** the explanation against heterogeneous evidence and detect cross-KPI tensions.
5. **Decide** whether the available evidence is sufficient for an operational recommendation.

The prototype is deliberately evidence-first. It does not require a live external LLM API to execute its analytical workflow.

---

## 2. Why StoryProof Is Different

### Traditional BI

Traditional BI is strong at:

- KPI monitoring
- Trend visualization
- Aggregation
- Filtering
- Reporting

However, a dashboard can make a correlation or plausible story appear more certain than the underlying evidence warrants.

### StoryProof

StoryProof adds:

- KPI semantic contracts
- Materiality and baseline-volatility checks
- Deterministic driver attribution
- Competing hypotheses
- Confounder detection
- Unstructured evidence retrieval
- Cross-KPI tension detection
- Explicit uncertainty and abstention
- Decision-readiness scoring
- Evidence-gated recommendations
- Role-based access simulation
- Human analyst feedback and governance history
- Auditable execution history

The goal is not to generate a more persuasive story.

The goal is to determine **whether the story is sufficiently supported to act on**.

---

## 3. Demonstrated Business Scenario

The prototype models a customer-support operation undergoing an automated-assistant rollout while other operational events occur concurrently.

The central business tension is:

- **AHT improves sharply**
- **FCR is broadly stable with a slight decline**
- **CSAT deteriorates materially**
- **Repeat Contact Rate increases materially**
- **Retention deteriorates**
- **AI Resolution Rate lacks sufficient history for a reliable conclusion**

This creates a realistic BI failure mode: a decision-maker could celebrate the large AHT improvement while missing evidence that customer outcomes are deteriorating.

StoryProof is designed to surface that tension before recommending an intervention.

---

## 4. Representative KPI Findings

The current validated scenario contains the following representative movements:

- **AHT:** 10.16 min → 5.77 min, approximately **-43.2%**
- **FCR:** 68.4% → 67.5%, approximately **-0.86 percentage points**
- **CSAT:** 78.0 → 68.9, approximately **-9.1 points**
- **Repeat Contact Rate:** 16.4% → 30.4%, approximately **+14.0 percentage points**
- **Retention Rate:** 95.59% → 94.49%, approximately **-1.10 percentage points**
- **AI Resolution Rate:** insufficient historical depth for a reliable materiality conclusion

These values are used to demonstrate how an apparently positive operational efficiency movement can coexist with negative customer outcomes.

---

## 5. Analytical Pipeline

```text
┌───────────────────────────┐
│ 1. Traditional BI         │
│ Reports KPI movements     │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ 2. KPI Tension Detection  │
│ Finds conflicting signals │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ 3. Evidence & Hypotheses  │
│ Tests competing stories   │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ 4. Decision Readiness     │
│ Measures evidence quality │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ 5. Recommended Action     │
│ Applies evidence gates    │
└───────────────────────────┘
```

### Stage 1 — Traditional BI

Displays KPI trends and establishes the observed change.

### Stage 2 — KPI Semantics & Materiality

Evaluates metrics against configured units, thresholds, baseline volatility, and available history.

### Stage 3 — Driver Decomposition & Competing Hypotheses

Separates measurable contribution patterns and evaluates competing explanations such as:

- Automated-assistant rollout
- CRM system patch
- Volume or customer-mix shift

### Stage 4 — Evidence Verification & Tension Detection

Cross-references quantitative movements with unstructured evidence such as:

- Support transcripts
- Customer feedback
- Operational reports

The system highlights situations where efficiency gains coexist with customer dissatisfaction or repeat-contact signals.

### Stage 5 — Decision Readiness & Action

Evaluates evidence sufficiency and emits recommendations only when the corresponding evidence gates are satisfied.

---

## 6. Deterministic Analytical Core

The analytical core is intentionally deterministic and has **no live external LLM dependency**.

### KPI Calculations

Aggregations, ratio calculations, unit normalization, and comparison metrics are calculated directly from the underlying data.

Implementation:

`src/engine/materiality.py`

### Materiality & Volatility

Materiality threshold crossings and standardized baseline Z-scores are computed mathematically.

Implementation:

`src/engine/materiality.py`

### Driver Attribution

Driver contribution analysis uses mathematical mix-rate variance decomposition and is designed to reconcile to the observed total change.

Implementation:

`src/engine/drivers.py`

### Hypothesis Evaluation

Competing hypotheses are evaluated through deterministic criteria including:

- Pre/post concentration differences
- Volume-weighted comparisons
- Rollout-phase trends
- Concurrent system events

Implementation:

`src/engine/hypotheses.py`

### Evidence Ingestion

Unstructured evidence is parsed into structured records with reproducible source identifiers.

Implementation:

`src/engine/evidence.py`

### Evidence Retrieval

Evidence is retrieved using deterministic keyword, metadata, and matching logic.

Implementation:

`src/engine/retrieval.py`

### Narrative Synthesis

The synthesis layer combines quantitative findings, hypothesis results, qualitative evidence, and KPI tensions using controlled templates.

Implementation:

`src/engine/synthesis.py`

### Action Gating

Recommendations are generated through explicit rule-based triggers. System-level interventions require the relevant authoritative hypothesis evidence.

Implementation:

`src/engine/actions.py`

### Governance

Analyst reviews are stored and aggregated into governance signals without modifying the underlying KPI truth.

Implementation:

`src/feedback/handler.py`

---

## 7. Causality Policy

StoryProof deliberately separates observed facts from explanations.

### FACT

A directly measured quantitative observation.

Example:

> AHT changed from 10.16 to 5.77 minutes.

### ASSOCIATION

A statistically observed relationship without a causal claim.

Example:

> The handling-time reduction is associated with the automated-assistant rollout.

### HYPOTHESIS

A candidate explanation currently under evaluation.

Example:

> The automated assistant may close tickets before the underlying issue is resolved, representing a candidate explanation for increased repeat contacts.

### CONTEXT / CONFOUNDER

A concurrent external factor that may provide an alternative explanation.

Example:

> A CRM Cloud software patch is identified as a concurrent operational event.

### LIMITATION

A data or history constraint that prevents a stronger conclusion.

Example:

> A KPI may not be directly segmentable by chatbot assistance because of source-log schema limitations.

All synthesized views use a causality disclaimer:

> **"The available evidence does not establish causality; observed changes represent associations and candidate explanations only."**

This policy is central to StoryProof's evidence-first design.

---

## 8. Decision Readiness

StoryProof does not treat every analytical result as immediately actionable.

The readiness layer considers factors such as:

- Data sufficiency
- Historical depth
- Active confounders
- Evidence quality
- Cross-KPI tension
- Unverified material changes

Representative readiness flags include:

- `insufficient_history`
- `high_ambiguity`
- `metric_tension_detected`
- `unverified_material_change`

The purpose is to make **abstention a valid analytical outcome**.

For example, the AI Resolution Rate series contains insufficient historical depth in the demonstrated scenario. StoryProof therefore avoids presenting a false level of confidence.

---

## 9. Driver Analysis

StoryProof uses deterministic contribution analysis to investigate observed KPI movement.

The driver layer is intended to answer:

> **Which measurable mix or operational components contributed to the observed change?**

The implementation includes mix-rate variance analysis and Shapley-style contribution decomposition.

The contribution results are used as analytical evidence, not as automatic causal proof.

---

## 10. Competing Hypotheses

The prototype evaluates multiple candidate explanations rather than accepting the first plausible narrative.

Current hypothesis categories include:

### AI Rollout

Evaluates whether KPI movements align with the rollout phases of the automated assistant.

### CRM Patch

Evaluates whether a concurrent CRM software change overlaps with KPI movements.

### Mix Shift

Evaluates whether changes in customer or operational mix can explain part of the observed movement.

This structure helps prevent a single intervention from receiving automatic causal credit merely because its timeline overlaps with the KPI change.

---

## 11. Evidence Layer

StoryProof combines structured KPI data with unstructured operational evidence.

Current evidence sources include:

- Support transcripts
- Customer feedback comments
- Program or operational reports

Each evidence record retains provenance information so that a surfaced statement can be traced back to its source.

The retrieval layer uses deterministic matching rather than a live generative retrieval system.

This supports the project's central requirement:

> **The explanation should remain traceable to evidence.**

---

## 12. Cross-KPI Tension Detection

A major StoryProof capability is detecting situations where individual KPI improvements hide broader business deterioration.

The demonstrated scenario contains a strong example:

```text
AHT
↓ significantly

while

CSAT
↓ significantly

Repeat Contact Rate
↑ significantly

Retention
↓

FCR
↓ slightly
```

A traditional efficiency dashboard may emphasize the AHT improvement.

StoryProof instead asks whether the improvement is accompanied by evidence of degraded resolution quality or customer experience.

This is the core **"verify the story"** moment in the demonstration.

---

## 13. Action Recommendation Engine

Recommendations are structured across seven operational dimensions.

### WHY / DRIVER

The observed KPI movement or evidence tension that triggered the recommendation.

### WHAT LEVER

The business lever available to the responsible manager.

Examples:

- Bot routing rules
- Software release isolation
- Data ingestion window

### WHAT ACTION

The concrete operational guidance.

### WHO OWNS IT

The accountable role, such as:

- Support Operations Manager
- CX Manager

### EXPECTED IMPACT

The intended operational outcome.

### EVIDENCE CONFIDENCE

A structured confidence treatment derived from the evidence state.

Representative states include:

- `LOW_BASELINE_CONFIDENCE`
- `MODERATE_ASSOCIATION`
- `HIGH_TENSION_RISK`
- `VERIFIED_READY`

### HOW TO MONITOR

Leading indicators and monitoring cadence to evaluate the intervention.

---

## 14. Action Types

### `STABILIZE_BASELINE`

Used when insufficient historical baseline data exists.

Example:

Sparse AI Resolution Rate history can cause StoryProof to recommend stabilizing the measurement baseline before scaling a decision.

### `SYSTEM_PATCH`

Used when a concurrent system release may be contributing to a KPI movement.

This recommendation is strictly gated by supporting CRM-hypothesis evidence.

### `RESOLUTION_GUARDRAIL`

Used when operational efficiency improvements conflict with customer-quality signals such as complaints or repeat contacts.

Potential controls include:

- Auto-closure guardrails
- Routing controls
- Resolution-quality monitoring

### `OPERATIONAL_OPTIMIZATION`

Used only when the relevant improvement is sufficiently verified and active risk flags do not block the recommendation.

---

## 15. Persona Views

StoryProof provides role-oriented views so that different managers can focus on the information relevant to their decisions.

### CX Manager

Focuses on:

- AHT
- FCR
- CSAT
- Repeat Contact Rate
- Retention
- Customer evidence

The internal AI Resolution Rate metric is restricted.

### Operations Manager

Focuses on:

- AHT
- FCR
- CSAT
- Repeat Contact Rate
- AI Resolution Rate
- Operational drivers
- System and process evidence

Retention is restricted in the prototype's entitlement model.

### Guest

Receives read-only access to the common operational KPI subset.

Administrative functions are disabled.

### Administrator

Receives full access to:

- All six KPIs
- Audit history
- Execution history
- Feedback records
- Observability information

---

## 16. Prototype Role & Entitlement Simulation

Role-based access is simulated from the semantic KPI contract in:

`config/kpi_definitions.yaml`

Backend access enforcement is implemented through:

- `get_accessible_kpis()`
- `check_kpi_access()`

The restriction is applied at the computation and retrieval layer rather than being only a visual UI restriction.

Role switching demonstrates the authorization contract. In an enterprise deployment, this layer could connect to an SSO/IAM provider.

---

## 17. Human-in-the-Loop Governance

StoryProof includes an auditable analyst-feedback mechanism backed by SQLite.

Analyst reviews can be:

- `APPROVED`
- `REJECTED`
- `FLAGGED`

Historical feedback is aggregated into governance treatment for matching recommendations.

Representative governance outcomes include:

- `STANDARD_REVIEW`
- `HISTORICAL_SUPPORT`
- `CONTEXTUAL_REVIEW`
- `HEIGHTENED_REVIEW`
- `ESCALATED_REVIEW`

An important design rule is maintained:

> **Governance feedback does not modify data truth.**

Historical reviews do not change:

- KPI calculations
- Materiality
- Evidence truth
- Driver decomposition
- Analytical confidence

They only influence the governance treatment applied to future matching recommendations.

---

## 18. Audit Trail & Observability

The Administrator Audit Console separates actual runtime measurements from simulated economic projections.

### Actual Runtime Telemetry

The prototype records or exposes:

- Deterministic engine execution latency
- SQLite audit-store status
- Execution-run counts
- Feedback-record counts
- Historical execution runs
- Parameter restoration information

### Simulated Economic Projection

The prototype also contains an illustrative token-cost model:

- 8,500 input tokens per run
- 1,200 output tokens per run
- $0.005 per 1k input tokens
- $0.015 per 1k output tokens

These figures are **simulated/projected economics**, not measured LLM consumption.

The prototype itself executes without external LLM API calls.

---

## 19. Execution Run IDs

Each analytical execution receives a `run_id`.

The identifier is used to connect:

- Execution parameters
- Analytical results
- Audit records
- Governance history

This provides a point-in-time reference for reviewing how an analytical result was produced.

The runtime SQLite audit database is generated locally and is intentionally excluded from source control.

---

## 20. Repository Structure

```text
storyproof/
│
├── config/
│   ├── kpi_definitions.yaml
│   ├── evidence_sources.yaml
│   └── simulation_config.yaml
│
├── data/
│   ├── support_daily.csv
│   ├── cx_weekly.csv
│   ├── crm_monthly.csv
│   ├── ai_resolution_rate.csv
│   └── unstructured/
│       ├── support_transcripts.txt
│       ├── customer_feedback.txt
│       └── rollout_report.txt
│
├── scripts/
│   ├── generate_data.py
│   └── validate_data.py
│
├── src/
│   ├── engine/
│   │   ├── actions.py
│   │   ├── drivers.py
│   │   ├── evidence.py
│   │   ├── hypotheses.py
│   │   ├── materiality.py
│   │   ├── personas.py
│   │   ├── readiness.py
│   │   ├── retrieval.py
│   │   └── synthesis.py
│   │
│   └── feedback/
│       └── handler.py
│
├── tests/
│   ├── test_actions.py
│   ├── test_dashboard_integration.py
│   ├── test_dashboard_layout.py
│   ├── test_drivers.py
│   ├── test_evidence.py
│   ├── test_feedback.py
│   ├── test_hypotheses.py
│   ├── test_materiality.py
│   ├── test_personas.py
│   ├── test_readiness.py
│   ├── test_retrieval.py
│   └── test_synthesis.py
│
├── app.py
├── requirements.txt
└── README.md
```

### Runtime-only files

The following are intentionally not part of the source repository:

- `.venv/`
- Python cache files
- `.pytest_cache/`
- `.env`
- Streamlit secrets
- `data/storyproof_audit.db`

The SQLite audit database is generated by the application at runtime.

---

## 21. Configuration

The prototype keeps key semantic definitions in configuration files rather than scattering them throughout the application.

### `config/kpi_definitions.yaml`

Defines KPI semantics, units, thresholds, and lineage.

### `config/evidence_sources.yaml`

Defines structured metadata for evidence sources.

### `config/simulation_config.yaml`

Defines simulation scenario metadata and rollout phases.

The checked-in business datasets represent the validated demonstration scenario.

---

## 22. Running the Application

### Step 1 — Create a virtual environment

```bash
python -m venv .venv
```

### Step 2 — Activate the environment

#### Windows PowerShell

```powershell
.venv\Scripts\Activate.ps1
```

#### Linux / macOS

```bash
source .venv/bin/activate
```

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 4 — Start the dashboard

```bash
streamlit run app.py
```

The application opens the interactive StoryProof dashboard in the browser.

---

## 23. Testing

Run the automated test suite with:

### Windows

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```

### Linux / macOS

```bash
python -m pytest tests/ -q
```

The latest project validation run reported **226 passing tests** across the analytical, evidence, governance, dashboard, and integration layers.

---

## 24. Authoritative Data Validation

The repository includes a validation utility covering the business-data and semantic checks used by the prototype.

### Windows PowerShell

```powershell
$env:PYTHONPATH="."
.venv\Scripts\python.exe scripts/validate_data.py
```

### Linux / macOS

```bash
export PYTHONPATH=.
python scripts/validate_data.py
```

The validation workflow checks:

- Dataset structure
- KPI semantic contracts
- Expected business patterns
- Evidence-layer consistency
- Historical sufficiency
- Materiality inputs

---

## 25. Validation Snapshot

The latest validated scenario contains:

- `support_daily.csv`: 27,539 rows
- `cx_weekly.csv`: 972 rows
- `crm_monthly.csv`: 72 rows
- `ai_resolution_rate.csv`: 252 rows
- AI Resolution Rate unique calendar days: 21

Representative analytical results:

- AHT: material change
- FCR: not material
- CSAT: material change
- Repeat Contact Rate: material change
- Retention Rate: material change
- AI Resolution Rate: insufficient history

The validation also confirms the intended business pattern: a major efficiency improvement occurs alongside deterioration in several customer-facing outcomes.

---

## 26. Design Principles

StoryProof follows several principles throughout the implementation.

### Evidence before explanation

A plausible story is treated as a hypothesis until evidence supports it.

### Determinism before generation

The analytical core relies on explicit calculations and rules rather than requiring a generative model.

### Abstention is valid

Insufficient data or unresolved ambiguity should prevent overconfident conclusions.

### Causality must be earned

Temporal overlap or correlation alone does not establish causality.

### Governance is separate from truth

Human feedback affects governance treatment, not the underlying KPI facts.

### Recommendations require gates

A recommendation should be tied to a defined evidence state and operational owner.

### Traceability matters

Analytical outputs should be traceable to data, evidence, rules, and execution history.

---

## 27. Intended Demo Narrative

The StoryProof demonstration is designed around one central question:

> **"AHT improved by more than 40%. Should we celebrate the rollout and scale it?"**

A conventional dashboard could stop at the improvement.

StoryProof continues:

1. Detects the large AHT improvement.
2. Checks other customer-facing KPIs.
3. Surfaces the CSAT and Repeat Contact deterioration.
4. Examines competing explanations.
5. Retrieves supporting qualitative evidence.
6. Detects the cross-KPI tension.
7. Checks decision readiness.
8. Abstains where history is insufficient.
9. Gates the resulting operational recommendation.
10. Records the execution and governance context.

This turns a dashboard from a reporting surface into an **evidence-verification workflow**.

---

## 28. Project Scope

### Implemented in the prototype

- Interactive Streamlit dashboard
- KPI semantic contracts
- Materiality analysis
- Driver decomposition
- Competing hypotheses
- Confounder handling
- Unstructured evidence ingestion
- Evidence retrieval
- Narrative synthesis
- Cross-KPI tension detection
- Decision-readiness scoring
- Evidence-gated action recommendations
- Persona views
- Role and entitlement simulation
- Analyst feedback
- Governance aggregation
- Execution audit history
- Runtime observability

### Potential production evolution

The prototype can later be extended with enterprise infrastructure such as:

- SSO/IAM integration
- Production data connectors
- Enterprise metadata catalogs
- More advanced statistical testing
- Production-grade vector or semantic retrieval
- Optional governed generative-language assistance
- Enterprise observability and monitoring

These are future production considerations, not dependencies of the current prototype.

---

## 29. Technology Stack

- **Python**
- **Streamlit**
- **Pandas**
- **NumPy**
- **Plotly**
- **PyYAML**
- **SQLite**
- **Pytest**

The architecture intentionally keeps the analytical core lightweight and inspectable.

---

## 30. Project Status

StoryProof is a working hackathon prototype demonstrating an evidence-first approach to Business Intelligence.

The project is focused on the distinction between:

**"What changed?"**

and

**"Is the story we are telling about that change actually supported by the available evidence?"**

That distinction is the foundation of StoryProof.

---

## 31. Challenge Context

**Accenture Innovation Challenge 2026**

**Track:** 3 — BusinessIntelligence.ai

**StoryProof tagline:**

> **"Don't just tell the story. Verify it."**
