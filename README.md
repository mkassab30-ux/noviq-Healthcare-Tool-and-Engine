# NOVIQ Engine — Clinical Coding Intelligence Platform

**AR-DRG V11.0 · ICD-10-AM Twelfth Edition · FHIR R4 Compatible**

NOVIQ Engine is an AI-powered clinical coding intelligence platform that reads a patient's complete EHR before any claim is submitted and produces accurate, ethically justified medical codes (ICD-10-AM, ACHI, AR-DRG), protecting against both upcoding and revenue leakage simultaneously.

The engine implements the full **AR-DRG V11.0 Chain of Truth** — the official IHACPA pipeline from diagnosis exclusions through ECCS computation to final DRG assignment — as a clean, modular, JSON-In/JSON-Out Python system ready to plug into any hospital HMIS via FHIR R4 or HL7 v2.

---

## Architecture

```
EHR Documents (FHIR R4 / HL7 v2)
         │
         ▼
┌─────────────────────────────────────────────┐
│            NOVIQ Engine                     │
│                                             │
│  ┌─────────────────┐  ┌──────────────────┐  │
│  │  ACS Scoring    │  │  AR-DRG Grouper  │  │
│  │  Engine         │→ │  (V11.0)         │  │
│  │  (ACS 0001/0002)│  │  5-step pipeline │  │
│  └─────────────────┘  └──────────────────┘  │
│           │                    │            │
│           ▼                    ▼            │
│  ┌─────────────────────────────────────┐    │
│  │      Validation Rules Module        │    │
│  │  DCL exclusions · Upcoding risk     │    │
│  │  ECCS · COVID routing · FHIR out    │    │
│  └─────────────────────────────────────┘    │
│                     │                       │
└─────────────────────┼───────────────────────┘
                      ▼
         Physician Approval Gate
         (non-negotiable before submission)
                      │
                      ▼
         NPHIES / UHI Portal / Payer
```

### Design principles

- **JSON-In / JSON-Out** — every module accepts a `PatientEpisode` dict and returns a typed result dict. Zero UI coupling. Zero DB calls inside modules.
- **FastAPI-ready** — any module wraps in 3 lines: `@app.post("/validate") async def validate(ep: dict) -> dict: return validate_episode(ep)`
- **Physician approval gate** — non-negotiable architectural requirement. No claim exits without physician sign-off.
- **Clinical Truth Preservation** — anchored to ACS score, not the Discharge Summary. Two-sided protection: flags both upcoding risk and revenue leakage.
- **Version-aware** — immutable KB per AR-DRG version. V12.0 (July 2026) is a config swap, not a code rewrite.

---

## Repository structure

```
NOVIQ-Clinical-Coding-Intelligence-Platform/
│
├── engine/
│   ├── grouper.py                    # AR-DRG V11.0 grouper — 5-step pipeline
│   ├── validation_rules.py           # DCL exclusion module + ECCS utilities
│   └── statistical_simulation.py    # RID, L3H3 trimming, threshold simulation
│
├── knowledge_base/
│   ├── ar_drg_kb_seed_v11_new_adrgs.json   # B08, F25, G13 seed data
│   ├── dcl_exclusions.json                  # Appendix C exclusion KB
│   └── keyword_dictionary_v11_new_adrgs.json # ACHI trigger codes
│
├── docs/
│   └── GROUPER_PSEUDOCODE.md         # Approved pseudocode — Phase 3 Deliverable 3.1
│
├── tests/
│   └── test_grouper.py               # 18-assertion test suite — ALL GREEN
│
└── README.md
```

---

## Modules

### `engine/grouper.py`
The AR-DRG V11.0 grouper. Single entry point: `ARDRGGrouper.group_episode(episode_dict) → dict`.

**5-step pipeline:**

| Step | Name | Key logic |
|------|------|-----------|
| 1 | Demographic & Clinical Edits | Validates all inputs. Sex conflict → FLAG only (V11.0 change). Strips invalid codes non-fatally. Exits to 960Z / 961Z / 963Z on failure. |
| 2 | Pre-MDC Override | Checks for very high-cost intervention triggers that bypass MDC assignment. |
| 3 | MDC Assignment | Routes PDX to Major Diagnostic Category. `R10.2` is the only remaining sex-routing PDX in V11.0. |
| 4 | ADRG Assignment | Walks intervention hierarchy positionally. First ACHI trigger match wins. Falls back to medical partition then ADRG 801. |
| 5 | DRG Assignment | Applies Appendix C exclusions → DCL lookup → ECCS (0.86 decay) → threshold comparison → suffix A/B/C/D/Z. |

**V11.0 confirmed hierarchy positions (Final Report Table 3):**
- MDC 01: B02 (pos 1) > B08 (pos 2) — ECR episode with cranial ACHI routes to B02
- MDC 05: F25 (pos 13) — all cardiac valve surgery ADRGs rank above
- MDC 06: G13 (pos 1) — wins over all other MDC 06 intervention ADRGs

```python
from engine.grouper import ARDRGGrouper

grouper = ARDRGGrouper()
result  = grouper.group_episode({
    "episode_id":    "EP-001",
    "patient_age":   58,
    "patient_sex":   "Female",
    "pdx":           "C48.1",
    "adx":           ["E11.9", "E61.1"],
    "achi_codes":    ["96211-00"],
    "los_days":      12,
    "same_day":      False,
    "separation_mode": "discharge_home",
    "care_type":     "01"
})
# result["ar_drg_code"]  → "G13Z"
# result["eccs"]         → 0.0  (DCL table stub — see open items)
# result["ar_drg_version"] → "V11.0"
```

---

### `engine/validation_rules.py`
DCL exclusion module. Validates all ICD-10-AM codes in a `PatientEpisode` against the AR-DRG V11.0 exclusion Knowledge Base. Flags upcoding risk before grouping.

**Three public functions:**

```python
from engine.validation_rules import validate_episode, validate_dcl_eligibility, get_exclusion_reason

# Primary entry point
result = validate_episode(episode_dict)
# result["validation_status"]          → "WARN"
# result["summary"]["upcoding_risk_count"] → 2
# result["excluded_codes"][0]["code"]  → "E61.1"
# result["covid_routing"]["target_adrg"] → "T63"

# Single-code check
check = validate_dcl_eligibility("E61.1", adrg="G13")
# check["eligible"] → False
# check["upcoding_risk"] → True

# Plain-language reason
reason = get_exclusion_reason("D89.82")
# reason["reason"] → "Reflects a background clinical state..."
```

**ECCS utilities (confirmed from Technical Specifications Section 4.5):**

```python
from engine.validation_rules import compute_eccs, compute_eccs_with_trace

eccs  = compute_eccs([4, 3, 2, 1, 0])       # → 8.6953
trace = compute_eccs_with_trace([4, 3, 2, 1])
# trace["formula_string"] → "4×(0.86)^0 + 3×(0.86)^1 + ..."
```

---

### `engine/statistical_simulation.py`
Development/validation module. Not called by the runtime grouper. Use for threshold simulation, RID calculation, and outlier trimming when real cost data is available.

```python
from engine.statistical_simulation import (
    compute_rid,
    apply_l3h3_trim,
    simulate_eccs_thresholds,
    modified_park_test
)

# Simulate optimal ECCS threshold for an ADRG
result = simulate_eccs_thresholds(eccs_values, costs)
# result["best_threshold"] → optimal cutoff
# result["rid_gain_pct"]   → RID improvement vs unsplit

# L3H3 inlier/outlier classification
df = apply_l3h3_trim(df, drg_col="ar_drg", los_col="los_days")
```

---

## Knowledge Base

### `knowledge_base/ar_drg_kb_seed_v11_new_adrgs.json`
Seed data for the three new ADRGs introduced in V11.0, plus global V11.0 flags.

| ADRG | Description | MDC | Split | Hierarchy pos | ECCS threshold |
|------|-------------|-----|-------|---------------|----------------|
| B08 | Endovascular Clot Retrieval | 01 | A/B | 2 | ≥ 3.0 ✓ |
| F25 | Percutaneous Heart Valve Replacement with Bioprosthesis | 05 | A/B | 13 | **null** ⚠ |
| G13 | Peritonectomy for Gastrointestinal Disorders | 06 | Z (unsplit) | 1 | N/A ✓ |

Also encodes: Chain of Truth pipeline reference · FHIR output schema · R-code exclusion logic · DRG splitting principles · confirmed ECCS thresholds (B70A=4.0, B08A=3.0, V62=3.5) · versioning with V12.0 warning · Errata 1 (2023-04-01) applied.

### `knowledge_base/dcl_exclusions.json`
Appendix C exclusion Knowledge Base. Unconditional (Table C1) and conditional (Table C2) exclusions for the ECC Model. Currently seeded with 7 confirmed unconditional codes from V11.0 Final Report Appendix A Table A5, plus all 4 COVID-19 DCL inclusion codes.

### `knowledge_base/keyword_dictionary_v11_new_adrgs.json`
ACHI trigger and modifier codes for B08, F25, and G13, sourced from V11.0 Final Report Appendix A. Includes clinical context, device brand keyword hints for F25 (TAVI/TAVR), and valvuloplasty exclusion terms.

---

## ECCS formula

Confirmed from AR-DRG V11.0 Technical Specifications, Section 4.5:

```
ECCS(e) = Σ [ DCL(xᵢ, A) × (0.86)^(i-1) ]   for i = 1..n

where:
  DCLs sorted descending before summation
  0.86 = global decay factor (tested range 0.83–0.88; V10.0 and V11.0)
  Principal diagnosis IS included
  DCL range: 0–5 integer, ADRG-specific, pre-computed (not derived at runtime)
```

**Verified example:**
```
DCLs = [4, 3, 2, 1, 0]
ECCS = 4×1 + 3×0.86 + 2×0.7396 + 1×0.636056 + 0 = 8.695
```

---

## Test suite

18 assertions, all passing:

| # | Test | Result |
|---|------|--------|
| T1 | G13Z assigned for peritonectomy | PASS |
| T1 | E61.1 (iron deficiency) excluded — upcoding risk | PASS |
| T1 | Z59.0 (homelessness) excluded — socioeconomic | PASS |
| T1 | `errata_applied` present on every output | PASS |
| T1 | `ar_drg_version=V11.0` on every output | PASS |
| T2 | B08 assigned for ECR (ACHI 35414-00) | PASS |
| T2 | B08B fallback when DCL table is stub (ECCS=0) | PASS |
| T2 | `threshold_used=None` on fallback suffix | PASS |
| T2 | partition=intervention | PASS |
| T3 | 961Z for invalid PDX | PASS |
| T4 | 960Z for missing PDX | PASS |
| T5 | R10.2 Male → MDC 12 | PASS |
| T6 | R10.2 Female → MDC 13 | PASS |
| T7 | F25 raises `KnowledgeBaseIncompleteError` (null threshold) | PASS |
| T8 | ECCS formula [4,3,2,1,0] = 8.6953 | PASS |
| T9 | D89.82 (immunocompromised status) excluded | PASS |
| T10 | All FHIR output fields present | PASS |
| T10 | `ar_drg_version=V11.0` confirmed | PASS |

---

## Open items (purchase-blocked)

Three items require the AR-DRG V11.0 Definitions Manual (Volumes 1–3, Lane Print, `ar-drg.laneprint.com.au`):

| Item | Impact | Status |
|------|--------|--------|
| F25 ECCS threshold | F25A/F25B assignment blocked — `KnowledgeBaseIncompleteError` raised | Populate `eccs_threshold.value` in KB once obtained |
| Full DCL lookup table (~6.8M pairs) | All ECCS values currently 0.0 (stub) — DRG suffix defaults to lowest complexity | Load `dcl_table.json` via `DCLTable(table_path=...)` |
| Appendix C full Table C1+C2 | 7 of 47 unconditional exclusions confirmed; conditional exclusions empty | Add remaining codes to `dcl_exclusions.json` — no code changes required |

The production gate (`KnowledgeBaseIncompleteError`) prevents any incorrect DRG assignment from reaching the physician review layer. The engine is safe to run in stub mode.

---

## Build history

| Phase | Deliverables | Status |
|-------|-------------|--------|
| **Phase 0** | ACS Scoring Engine · Folder structure · README · Keyword Dictionary (Lap Chole) · AR-DRG V11.0 JSON schema | ✅ Complete |
| **Phase 1** | `keyword_dictionary_v11_new_adrgs.json` · `ar_drg_kb_seed_v11_new_adrgs.json` · B08/F25/G13 hierarchy + split corrections | ✅ Complete |
| **Phase 2** | `dcl_exclusions.json` · `validation_rules.py` · ECCS utilities · Statistical simulation module | ✅ Complete |
| **Phase 3** | `GROUPER_PSEUDOCODE.md` · `grouper.py` · 18-assertion test suite | ✅ Complete |
| **Phase 4** | `models.py` · ACS Engine → Grouper handoff · Physician approval gate · `CodingSuggestion` with provenance | 🔄 Next |

---

## V12.0 readiness

AR-DRG V12.0 is proposed to go live **1 July 2026**. The engine is version-aware by design:
- Each KB version is immutable (never modified in-place)
- `ar_drg_version` field on every output record
- `errata_applied[]` tracked per output
- Upgrade path: create `ar_drg_kb_seed_v12_new_adrgs.json`, instantiate `ARDRGGrouper(kb_path=v12_path)`

---

## Source authority

| Document | Access |
|----------|--------|
| AR-DRG V11.0 Final Report (January 2023) | Free — ihacpa.gov.au |
| AR-DRG V11.0 Technical Specifications | Free — ihacpa.gov.au |
| AR-DRG V11.0 Definitions Manual (Volumes 1–3) | Purchase — ar-drg.laneprint.com.au |
| ICD-10-AM/ACHI/ACS Twelfth Edition | Purchase — ihacpa.gov.au |
| ACS 0001/0002 Australian Coding Standards | Purchase — ihacpa.gov.au |

---

## Founder

**Dr. Mohamed Kassab** — General Surgeon · Healthcare Operations · Insurance/TPA (MetLife, MedNet/Munich Re) · Python · Power BI · Power Automate

*NOVIQ Engine is built to close the gap between clinical documentation and revenue integrity — preserving clinical truth at the point of coding, not after the claim is rejected.*
