# NOVIQ Engine
### AI-Powered Clinical Coding Intelligence — Upstream Revenue Cycle Optimization

> Built by **Noviq Health** | Founded by Dr. Mohamed Kassab, MD

---

## What is NOVIQ Engine?

NOVIQ Engine reads a patient's **complete EHR before any claim is submitted**, and produces accurate, ethical, fully justified medical codes — ICD-10-AM, ACHI, AR-DRG.

It is not a billing tool. It is a **Clinical Truth Preservation Engine.**

The surgeon who documents well carries less risk.  
NOVIQ makes sure that truth is fully captured in code.

---

## Core Principles

| Principle | Description |
|-----------|-------------|
| **Zero Upcoding** | Medical ethics is non-negotiable |
| **Zero Revenue Leakage** | Every documented complexity must be captured |
| **Score-Based Coding** | Every diagnosis earns its code through evidence (ACS 0001/0002) |
| **Full Provenance** | Every code cites its source from the RAG knowledge base |
| **Physician Always Decides** | Engine suggests, physician approves before submission |

---

## System Architecture

```
Hospital HMIS / EHR
        │
  New document uploaded
        │
        ▼
┌──────────────────────────┐
│    NOVIQ CONNECTOR       │
│  FHIR R4 / HL7 v2 / DB  │
│  → Unified JSON Format   │
└───────────┬──────────────┘
            │
            ▼
┌──────────────────────────┐
│   DOCUMENT CLASSIFIER    │
│  - Initial Medical Report│
│  - Admission Report      │
│  - Progress Notes        │
│  - Operation Notes       │
│  - Nursing Notes         │
│  - Discharge Summary     │
└───────────┬──────────────┘
            │
            ▼
┌────────────────────────────────────────────┐
│         SEQUENTIAL READING ENGINE          │
│                                            │
│  Doc 1-2: Initial + Admission Report       │
│  → Candidate Principal Diagnosis           │
│  → Admission reason captured               │
│                                            │
│  Doc 3: Progress Notes (daily)             │
│  → ACS 0002 scoring per new condition      │
│  → Management changes tracked             │
│  → Investigations specifically ordered?    │
│                                            │
│  Doc 4: Operation Notes                    │
│  → Base ACHI code detected                 │
│  → Keyword scan → Modifier assigned        │
│  → "New procedure or normal step?"         │
│  → Complications → ICD flags               │
│                                            │
│  Doc 5: Nursing Notes                      │
│  → Increased clinical care evidence        │
│  → New observations flagged               │
│                                            │
│  Doc 6: Discharge Summary                  │
│  → Cross-validation only                  │
│  → Score is source of truth, not DS        │
└───────────┬────────────────────────────────┘
            │
            ▼
┌────────────────────────────────────────────┐
│           ACS SCORING ENGINE               │
│                                            │
│  ACS 0001 — Principal Diagnosis            │
│  ├── Confirmed by investigation    +3      │
│  ├── Documented by physician       +2      │
│  └── Admission reason              +2      │
│                                            │
│  ACS 0002 — Additional Diagnoses           │
│  ├── C1: Therapeutic treatment     +3      │
│  ├── C2: Diagnostic procedure      +3      │
│  └── C3: Increased clinical care   +2      │
│                                            │
│  Score ≥ 5  → ✅ CODE IT                  │
│  Score 3-4  → ⚠️  PHYSICIAN REVIEW        │
│  Score < 3  → ❌ DO NOT CODE              │
└───────────┬────────────────────────────────┘
            │
            ▼
┌────────────────────────────────────────────┐
│          INTELLIGENCE LAYER                │
│                                            │
│  Agent 1: Intent                           │
│  → Case type (1/2/3/4)                     │
│  → Elective / Emergency                    │
│  → Specialty confirmed                     │
│                                            │
│  Agent 2: Medical Logic                    │
│  → RAG: Keyword Dictionaries               │
│  → Two-part code: Base (00000) + (-00)     │
│  → ACHI code assembly                      │
│  → Bundling rules enforced                 │
│                                            │
│  Agent 3: AR-DRG Engine                    │
│  → DCL calculated from all scored ICDs     │
│  → DRG weight assigned                     │
│  → Revenue estimate calculated             │
│                                            │
│  Agent 4: Critique & Ethics                │
│  → Anti-upcoding guard                     │
│  → Anti-leakage guard                      │
│  → ACS 0001/0002 compliance verified       │
│  → Confidence score assigned               │
│  → Human review triggered if needed        │
└───────────┬────────────────────────────────┘
            │
            ▼
┌────────────────────────────────────────────┐
│       PRE-SUBMISSION OUTPUT PACKAGE        │
│                                            │
│  Principal ICD-10-AM  [Score: X/7]         │
│  Secondary ICDs       [Score per each]     │
│  ACHI Code            [Base-Modifier]      │
│  AR-DRG Code + Weight + DCL                │
│  Justification per code (RAG cited)        │
│  Documentation gaps flagged                │
│  Revenue estimate                          │
│  Confidence: [0-100%]                      │
│  Physician approval: [ ]                   │
└───────────┬────────────────────────────────┘
            │
      Physician approves
            │
            ▼
┌────────────────────────────────────────────┐
│          SUBMISSION LAYER                  │
│  → NPHIES (KSA)                            │
│  → UHI Portal (Egypt)                      │
│  → Insurance Company API                   │
└────────────────────────────────────────────┘
```

---

## EHR Document Hierarchy

| Document | Role in Engine | Priority |
|----------|---------------|----------|
| Initial Medical Report | Principal diagnosis candidate | High |
| Admission Report | Patient ID + context | Medium |
| Progress Notes | ACS 0002 scoring source | High |
| Operation Notes | ACHI code source | Critical |
| Nursing Notes | ACS 0002 C3 (Increased care) | Medium |
| Discharge Summary | Cross-validation only | Low |

> **Note:** The ACS Score is the source of truth — not the Discharge Summary.
> A diagnosis missed in the DS but scored ≥5 from other documents will still be coded.

---

## ACHI Two-Part Code Logic

```
Every ACHI code has two parts:

    30445  -  00
      │         │
  Base Code   Modifier
      │         │
 Detected     Detected
 from OT Note from Keywords

Engine Flow:
  Step 1 → Read OT Note → Detect Base Code
  Step 2 → Scan Keywords → Assign Modifier
  Step 3 → Assemble: 30445-00
  Step 4 → Ethics check → Leakage? Upcoding?
  Step 5 → Revenue impact calculated
```

---

## Case Classification

| Type | Description | Volume | Engine Mode |
|------|-------------|--------|-------------|
| **Type 1** | Straightforward — clear Dx + agreed management | 40-50% | Auto-code (high confidence) |
| **Type 2** | Single surgical procedure — AR-DRG logic | 25-30% | Auto-code + modifier logic |
| **Type 3** | Complex multi-procedure — high risk | 5-10% | Suggest + mandatory review |
| **Type 4** | Long stay — ICU, oncology, daily coding | ~10% | Daily assistant, physician-in-loop |

---

## Tech Stack

| Component | Technology | Reason |
|-----------|-----------|--------|
| Agent Orchestration | LangGraph | Sequential control flow |
| RAG Framework | LlamaIndex | Native provenance/citation |
| Vector Store | Qdrant | Fast, local or cloud |
| LLM | Claude API (claude-sonnet-4-20250514) | Best medical reasoning |
| Retrieval | Hybrid: Dense + BM25 + Knowledge Graph | Medical term precision |
| EHR Integration | FHIR R4 / HL7 v2 | Universal compatibility |
| Backend | Python 3.11+ / FastAPI | |

---

## Knowledge Base Sources

| Source | Purpose | Status |
|--------|---------|--------|
| ACS 0002 — 11th Edition (WA Health) | Additional diagnosis rules | ✅ Loaded |
| ACHI Chronicle — 12th Edition (IHACPA) | Procedure codes | ✅ Loaded |
| AR-DRG Guidelines | DRG weight + DCL calculation | ⏳ Pending |
| Egypt UHI Payer Rules | Local coding rules | ⏳ Pending |
| KSA CCHI / NPHIES Rules | KSA payer rules | ⏳ Pending |
| Dr. Kassab Keyword Dictionaries | Procedure-level medical logic | 🔄 In Progress |

---

## Repository Structure

```
noviq-engine/
├── README.md
├── requirements.txt
├── .env.template
├── .gitignore
├── setup_github.sh
│
├── knowledge-base/
│   ├── guidelines/           # ACS PDFs, ACHI PDFs
│   └── payer-rules/
│       ├── egypt-uhi/
│       ├── ksa-cchi/
│       └── uae-dha/
│
├── docs/
│   ├── architecture/         # System design docs
│   ├── templates/            # Procedure documentation template
│   └── medical-logic/
│       └── general-surgery/
│           ├── type1-straightforward/
│           ├── type2-single-procedure/
│           ├── type3-complex/
│           └── type4-long-stay/
│
├── src/
│   ├── connector/            # FHIR / HL7 adapters
│   ├── ingestion/            # OCR, classifier, entity extraction
│   ├── rag/                  # RAG pipeline (indexer + retriever)
│   ├── intelligence-layer/   # 4 agents
│   ├── scoring/              # ACS 0001/0002 scoring engine ✅
│   └── output/               # Output formatting + provenance
│
├── data/
│   ├── keyword-dictionaries/
│   │   └── general-surgery/  # Per-procedure keyword → ACHI mapping
│   ├── synthetic-cases/      # Training cases by Dr. Kassab
│   └── anonymized-cases/     # Real de-identified cases
│
└── tests/
    ├── type1/
    ├── type2/
    └── type3/
```

---

## MVP Success Metrics — General Surgery

| Metric | Target |
|--------|--------|
| Type 1 coding accuracy | ≥ 90% |
| Type 2 coding accuracy | ≥ 85% |
| Type 3 coding accuracy | ≥ 80% (with human review) |
| Upcoding violations | 0% |
| Provenance on every code | 100% |
| Response time | < 10 seconds |
| Validated test cases | 200+ |

---

## Contribution

| Area | Owner |
|------|-------|
| Medical Logic, Clinical Rules, Keyword Dictionaries | Dr. Mohamed Kassab — Noviq Health |
| Technical Architecture, Code, RAG | NOVIQ Engineering |
| Validation & QA | Both |

---

## Phase Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| **Phase 0** | Foundation, Architecture, GitHub | ✅ Complete |
| **Phase 1** | Type 1 — Straightforward (General Surgery) | 🔄 Next |
| **Phase 2** | Type 2 — Single Procedure + AR-DRG | ⏳ Pending |
| **Phase 3** | Type 3 — Complex Multi-Procedure | ⏳ Pending |
| **Phase 4** | Type 4 — Long Stay (post-MVP) | ⏳ Pending |

---

*NOVIQ Engine — Clinical Truth, Preserved.*
*Noviq Health © 2025*
