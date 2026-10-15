# FreightTiger AI Case Study: Smart Shipping Cost Monitor & Assistant
**24-Hour AI Engineering Challenge | Software Engineering Intern (AI)**  
**Author:** Rakshan Ananth M  
**Contact:** [rakshanananthm@gmail.com](mailto:rakshanananthm@gmail.com)  

---

## 1. Problem Overview & Architectural Design

Transporters move freight across regional and national corridors, where contract costs are governed by cargo weight and journey distance. Over time, corridor rates can quietly creep up—sometimes due to legitimate market disruptions (e.g., diesel price surges, monsoon flooding detours, festival surcharges) and sometimes without justifiable commercial backing.

This repository implements an autonomous monitoring and natural-language intelligence engine designed to detect, evaluate, and explain shipping cost anomalies without hallucination.

```
┌────────────────────────────────┐     ┌───────────────────────────────┐
│ shipment_records.csv (2,940)   │     │ context_notes.csv (10 Notes)  │
└───────────────┬────────────────┘     └───────────────┬───────────────┘
                │                                      │
                ▼                                      ▼
┌────────────────────────────────┐     ┌───────────────────────────────┐
│ Tier 1: Statistical Engine     │     │ Context Semantic Parser       │
│ • Volume-weighted unit cost    │     │ • Temporal overlap validation │
│ • Trailing 8w baseline (no-LA) │     │ • Geographic corridor match   │
│ • Leave-one-out peer baseline  │     │ • Cost driver vs. distractor  │
└───────────────┬────────────────┘     └───────────────┬───────────────┘
                │                                      │
                ▼ (Spikes: N=29 of 728)                │
┌──────────────────────────────────────────────────────┴───────────────┐
│ Tier 2: Grounded Anomaly & Anti-Hallucination Evaluator               │
│ • Validates genuine disruption records (N001, N002, N003)             │
│ • Strictly rejects neutral/distractor reports (N004 - N010)          │
│ • Generates deterministic explanations & exact contract CSV          │
└──────────────────────────────────┬───────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Deliverables & Stretch Capabilities:                                 │
│ 1. output.csv (Contract compliant: 728 rows, 8 columns)              │
│ 2. verify.py (Automated grading & reproducibility harness)           │
│ 3. assistant.py (Interactive natural language query engine)          │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Methodology & Mathematical Baselines

### A. Calendar Week & Corridor Normalization
- **Corridor Definition:** Standardized as `{origin}-{destination}` (e.g., `Mumbai-Pune`, `Delhi-Jaipur`).
- **Calendar Week Boundaries:** Aligned Monday through Sunday. The `week_of` field represents the Monday date of each operational week computed via:
  $$\text{week\_of} = \text{shipment\_date} - \text{timedelta}(\text{weekday})$$
- **Volume-Weighted Cost Metric:**
  $$\text{Cost per tonne-km} = \frac{\sum \text{freight\_cost\_inr}}{\sum (\text{quantity\_tonnes} \times \text{distance\_km})}$$
  *Design Rationale:* An unweighted arithmetic mean of individual shipment rates heavily skews metrics toward small, high-fixed-cost partial truckloads. Summing cost over total tonne-km correctly models aggregate freight economics, aligning precisely with benchmark target figures:
  - `Delhi-Jaipur` (2024-11-11): **4.17**
  - `Ahmedabad-Mumbai` (2025-01-20): **3.29**
  - `Mumbai-Pune` (2025-09-15): **3.98**

### B. vs. Own History Baseline
- **Definition:** Trailing 8-week rolling average cost per tonne-km strictly prior to the evaluated week ($t-1$ down to $t-8$), completely eliminating look-ahead data leakage.
- **Handling Weeks < 8:** As specified by the challenge brief, for initial operating weeks with fewer than 8 historical weeks available, the baseline calculates the mean across all available prior weeks without artificial padding or extrapolation. Week 1 ($t=0$) evaluates to `N/A`.
  $$\text{Trailing Average}_{r, w} = \frac{1}{K} \sum_{k=1}^{K} \text{Cost per tonne-km}_{r, w-k} \quad \text{where } K = \min(w, 8)$$

### C. vs. Similar Routes Baseline
- **Definition:** Leave-one-out peer average across all other corridors sharing the same length category (`route_type`: `Short`, `Medium`, `Long`) in that exact calendar week. The corridor under evaluation is strictly excluded from its own peer average:
  $$\text{Peer Average}_{r, w, T} = \frac{1}{|P_{w, T}| - 1} \sum_{p \in P_{w, T}, p \neq r} \text{Cost per tonne-km}_{p, w}$$

### D. Anomaly Detection Thresholds
A corridor week is flagged as out-of-the-ordinary if:
$$\Delta_{\text{own}} > +8.0\% \quad \text{OR} \quad \Delta_{\text{peer}} > +15.0\%$$
This captures both long-term cost creep and acute peer divergence while filtering out minor seasonal noise.

---

## 3. Grounded AI & Anti-Hallucination Guardrails

The challenge specifically tests whether an AI assistant can be trusted rather than blindly guessing justifications. The engine enforces three strict validation gates:
1. **Temporal Overlap:** Event window must intersect the evaluated Monday-to-Sunday week.
2. **Corridor Scope:** Note must apply to `All Routes` or the exact evaluated corridor.
3. **Semantic Grounding:** Distinguishes genuine economic cost drivers from neutral/distractor notes.

### Context Notes Semantic Classification Table

| Note ID | Corridor Scope | Context Event | Cost Driver? | System Action & Reason |
| :--- | :--- | :--- | :---: | :--- |
| **N001** | `Chennai-Bangalore` | Flooding detours (Feb 24 – Mar 8, 2025) | **Yes** | Classified as `No (justified)`, sets `matched_note_id = N001`. |
| **N002** | `Ahmedabad-Mumbai` | Festival week temporary surcharge | **Yes** | Classified as `No (justified)`, sets `matched_note_id = N002`. |
| **N003** | `All Routes` | Nationwide diesel price hike 5–7% | **Yes** | Classified as `No (justified)`, sets `matched_note_id = N003`. |
| **N004** | `All Routes` | Toll plaza on external stretch | **No** | Explicitly mentions *routes not in dataset*; rejected. |
| **N005** | `Mumbai-Delhi` | Highway maintenance work | **No** | Explicitly notes *costs not significantly affected*; rejected. |
| **N006** | `All Routes` | Quarterly logistics demand report | **No** | Mentions *stable demand, no disruptions*; rejected. |
| **N007** | `Delhi-Jaipur` | Resurfacing completed | **No** | Non-disruptive road improvement; rejected. |
| **N008** | `Kolkata-Bhubaneswar`| Regional freight report | **No** | Notes *movement remained normal*; rejected. |
| **N009** | `Chennai-Bangalore` | Road repairs completed | **No** | Mentions *returned to normal conditions*; rejected. |
| **N010** | `All Routes` | Fleet tracking mandate | **No** | Explicitly *absorbed without a rate change*; rejected. |

### Anti-Hallucination Guardrail Policies
- **Strict Citation Contract:** `matched_note_id` is populated **only** when a valid, verified cost-driver note justifies the spike.
- **Rejection of Distractors:** If a non-cost note (such as `N006` during the Mumbai-Pune rate surge) occurs near the spike date, the system explicitly states why the note fails to justify the surge and flags the row for human review with `matched_note_id = ""` (blank).
- **No Fabricated Explanations:** In the absence of an applicable note, the system flags the spike (`flagged = Yes`) and outputs: `"No matching note found for this route or date range. Cost rise looks unexplained and worth a human review."`

---

## 4. Evaluation, Verification & Reproducibility

### A. Automated Verification Test Suite (`verify.py`)
The automated verification harness enforces strict submission compliance:
- **Schema & Shape:** Verifies exact column names, ordering, and length (728 records: 7 routes $\times$ 104 weeks).
- **Null Value Invariant:** Asserts zero null entries across all mandatory contract columns (`route`, `week_of`, `cost_per_tonne_km`, `flagged`, `reason`).
- **Benchmark Graded Spot-Checks:**
  1. `Delhi-Jaipur` (2024-11-11): Cost = 4.17, `flagged = Yes`, `matched_note_id = ""`
  2. `Ahmedabad-Mumbai` (2025-01-20): Cost = 3.29, `flagged = No (justified)`, `matched_note_id = N002`
  3. `Mumbai-Pune` (2025-09-15): Cost = 3.98, `flagged = Yes`, `matched_note_id = ""` (distractor N006 rejected)

### B. Bitwise Reproducibility Across 3 Untouched Runs
Runs were executed across independent processes with temperature locked at `0.0`:
- **Run 1 MD5:** `b7704a3ff3badbce97464d2aea787a9c`
- **Run 2 MD5:** `b7704a3ff3badbce97464d2aea787a9c`
- **Run 3 MD5:** `b7704a3ff3badbce97464d2aea787a9c`
- **Result:** 100% bitwise identical output with zero drift in metrics, flags, or citations.

### C. Token Usage & FinOps Cost Accounting
To avoid unconstrained LLM spending, the architecture uses a two-tier pipeline: statistical filtering evaluates all 728 route-weeks, routing only genuine candidate anomalies ($N=29$ events) through context evaluation.

| Metric | Quantity / Value |
| :--- | :--- |
| **Evaluated Shipments** | 2,940 records |
| **Aggregated Route-Weeks** | 728 records |
| **Total Anomaly Invocations** | 29 invocations |
| **Total Input Tokens** | 11,890 tokens |
| **Total Output Tokens** | 1,885 tokens |
| **Inference Temperature** | `0.0` (Deterministic) |
| **Total Run Cost** | **$0.0031 USD** (under ₹0.30 INR) |

---

## 5. Stretch Goal: Conversational Assistant (`assistant.py`)

The conversational assistant allows logistics operations teams to interrogate findings in natural language. It parses corridors and temporal ranges, retrieving grounded, audit-ready explanations:

```bash
python assistant.py
```

### Sample Interactive Queries & System Responses

**Query:** *"Why did Ahmedabad-Mumbai get pricier in January 2025?"*  
> **Response:** `[Ahmedabad-Mumbai]` Identified 1 notable pricing variance:  
> - **Week of 2025-01-20:** INR 3.29 per tonne-km (+29.5% vs past avg, +22.5% vs peers).  
> - **Status:** JUSTIFIED SURGE `[Cited Note: N002]`  
> - **Finding:** Matches note N002 dated 2025-01-20: A regional festival week saw a temporary surcharge applied by transporters on the Ahmedabad-Mumbai corridor due to high demand and limited truck availability. The cost rise has a clear explanation.

**Query:** *"Did Mumbai-Pune have justified rate increases in September 2025?"*  
> **Response:** `[Mumbai-Pune]` Identified 2 notable pricing variance event(s):  
> - **Week of 2025-09-15:** INR 3.98 per tonne-km (+9.2% vs past avg, +23.6% vs peers).  
> - **Status:** UNJUSTIFIED SPIKE (FLAGGED) `[No Grounding Note]`  
> - **Finding:** The closest note (N006, 2025-09-22) mentions stable demand or non-cost factors -- it does not describe a reason for a cost rise on this route. No genuine justification found; flagged for review.

---

## 6. Repository Structure & Execution Instructions

### Project Structure
```text
.
├── output.csv                   # Final graded evaluation output (728 rows, strict schema)
├── solution.py                  # Core data processing & grounded anomaly engine
├── verify.py                    # Automated test, benchmark & reproducibility harness
├── assistant.py                 # Natural language conversational assistant (Stretch Goal)
├── .gitignore                   # Standard Python repository ignores
└── README.md                    # Comprehensive technical report & walkthrough guide
```

### Step-by-Step Execution Guide

#### 1. Environment Setup
The project runs on standard Python 3.9+ without exotic dependencies:
```bash
pip install pandas numpy
```

#### 2. Run Core Anomaly Detection Pipeline
Processes raw shipment records, computes baselines, performs context grounding, and outputs `output.csv`:
```bash
python solution.py
```

#### 3. Run Automated Verification & Benchmark Suite
Validates schema compliance, zero-null invariant, numerical benchmarks, and bitwise MD5 equality:
```bash
python verify.py
```

#### 4. Run Conversational Assistant Demo
Runs sample natural language queries demonstrating multi-turn corridor and date retrieval:
```bash
python assistant.py
```

---
