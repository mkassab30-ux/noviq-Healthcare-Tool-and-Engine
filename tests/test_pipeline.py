"""
NOVIQ Engine — End-to-End Integration Tests
=============================================
Phase 4, Deliverable 4.4

Tests the full pipeline:
  EpisodeRecord → ACS Scoring → Validation → Grouper → CodingSuggestion

Covers:
  - Type 1: straightforward episode (G13Z peritonectomy)
  - Type 2: single surgical with ACHI trigger (B08 ECR)
  - Physician gate: blocks submission until approved
  - Upcoding risk detection end-to-end
  - ACS score threshold routing
  - Provenance chain completeness
  - to_dict() serialisation (FHIR-compatible output)

Run: python test_pipeline.py
"""

import warnings
warnings.filterwarnings("ignore")

from models import (
    EpisodeRecord, CodingSuggestion, ACSScore,
    ACS_THRESHOLD_CODE, ACS_THRESHOLD_REVIEW,
    APPROVAL_PENDING, APPROVAL_APPROVED, APPROVAL_REJECTED,
)
from noviq_engine import NOVIQEngine, process
from validation_rules import KnowledgeBaseIncompleteError

results = []


def check(name: str, got, expected):
    ok = got == expected
    results.append((name, ok))
    status = "PASS" if ok else "FAIL"
    print(f"  {status}  {name}")
    if not ok:
        print(f"         got={got!r}")
        print(f"    expected={expected!r}")


def check_true(name: str, condition: bool):
    check(name, condition, True)


# ---------------------------------------------------------------------------
engine = NOVIQEngine()

# ---------------------------------------------------------------------------
print("\n=== Phase 4 Integration Tests ===\n")

# ── T1: Type 1 — Straightforward peritonectomy (G13Z) ─────────────────────
print("T1  Type 1 — Peritonectomy G13Z")
ep1 = {
    "episode_id":    "T1-G13",
    "patient_age":   58,
    "patient_sex":   "Female",
    "admission_weight": None,
    "same_day":      False,
    "separation_mode": "discharge_home",
    "los_days":      12,
    "pdx":           "C48.1",
    "adx":           ["E11.9", "E61.1", "Z59.0"],
    "achi_codes":    ["96211-00"],
    "hours_mech_vent": None,
    "care_type":     "01",
    "ehr_documents": ["Operation Notes", "Discharge Summary"],
    "acs_pdx_score": 6,
}
s1 = engine.process_episode(ep1)
check("T1  AR-DRG = G13Z", s1.ar_drg_code, "G13Z")
check("T1  approval = PENDING", s1.approval_status, APPROVAL_PENDING)
check("T1  upcoding risk detected", s1.upcoding_risk_count, 1)
check("T1  DCL excluded ≥ 2", s1.dcl_excluded_count >= 2, True)
check("T1  ACHI trigger present", "96211-00" in s1.achi_trigger, True)
check("T1  ACS PDX score = 6", s1.acs_pdx_score, 6)
check("T1  EHR docs recorded", len(s1.ehr_documents_read), 2)
check_true("T1  upcoding flag present", any("E61.1" in f for f in s1.flags))
check("T1  engine_version = V11.0", s1.engine_version, "V11.0")
check_true("T1  suggestion_id is UUID", len(s1.suggestion_id) == 36)

# ── T2: Type 2 — Single surgical, B08 ECR ─────────────────────────────────
print("\nT2  Type 2 — Endovascular Clot Retrieval B08")
ep2 = {
    "episode_id":    "T2-B08",
    "patient_age":   72,
    "patient_sex":   "Male",
    "admission_weight": None,
    "same_day":      False,
    "separation_mode": "discharge_home",
    "los_days":      4,
    "pdx":           "I63.3",
    "adx":           ["I10", "E11.9"],
    "achi_codes":    ["35414-00"],
    "hours_mech_vent": None,
    "care_type":     "01",
    "ehr_documents": ["Admission Report", "Operation Notes", "Discharge Summary"],
    "acs_pdx_score": 7,
}
s2 = engine.process_episode(ep2)
check("T2  AR-DRG starts with B08", s2.ar_drg_code.startswith("B08"), True)
check("T2  partition = intervention",
      s2.grouper_result.get("partition"), "intervention")
check("T2  approval = PENDING", s2.approval_status, APPROVAL_PENDING)
check("T2  ACS PDX score = 7", s2.acs_pdx_score, 7)
check_true("T2  ACHI trigger contains 35414-00",
           "35414-00" in s2.achi_trigger)
check("T2  proposed_pdx = I63.3", s2.proposed_pdx, "I63.3")
check("T2  proposed_achi present", "35414-00" in s2.proposed_achi, True)

# ── T3: Physician gate blocks submission before approval ───────────────────
print("\nT3  Physician approval gate")
try:
    s1.assert_approved()
    check("T3  gate blocks PENDING", False, True)
except PermissionError:
    check("T3  gate blocks PENDING", True, True)

s1.approve("DR-KASSAB-001")
check("T3  approval_status = APPROVED", s1.approval_status, APPROVAL_APPROVED)
check("T3  approved_by set", s1.approved_by, "DR-KASSAB-001")
check_true("T3  approved_at set", s1.approved_at is not None)
s1.assert_approved()   # should not raise
check("T3  assert_approved passes after approve()", True, True)

# ── T4: Physician rejection ────────────────────────────────────────────────
print("\nT4  Physician rejection")
s2.reject("DR-KASSAB-001", reason="Incorrect ACHI code — use 35300-00")
check("T4  approval_status = REJECTED", s2.approval_status, APPROVAL_REJECTED)
check_true("T4  rejection reason in flags",
           any("35300-00" in f for f in s2.flags))
try:
    s2.assert_approved()
    check("T4  gate blocks REJECTED", False, True)
except PermissionError:
    check("T4  gate blocks REJECTED", True, True)

# ── T5: F25 production gate propagates end-to-end ─────────────────────────
print("\nT5  F25 production gate (null threshold)")
ep5 = {
    "episode_id":    "T5-F25",
    "patient_age":   78,
    "patient_sex":   "Male",
    "admission_weight": None,
    "same_day":      False,
    "separation_mode": "discharge_home",
    "los_days":      5,
    "pdx":           "I35.0",
    "adx":           ["I25.10"],
    "achi_codes":    ["38488-08"],
    "hours_mech_vent": None,
    "care_type":     "01",
    "acs_pdx_score": 7,
}
try:
    s5 = engine.process_episode(ep5)
    check("T5  F25 gate fires", False, True)
except KnowledgeBaseIncompleteError as e:
    check("T5  KnowledgeBaseIncompleteError raised", True, True)
    check_true("T5  error mentions F25", "F25" in str(e))

# ── T6: ACS score thresholds reflected in suggestion ──────────────────────
print("\nT6  ACS score thresholds")
ep6 = {
    "episode_id":    "T6-ACS",
    "patient_age":   45,
    "patient_sex":   "Female",
    "admission_weight": None,
    "same_day":      False,
    "separation_mode": "discharge_home",
    "los_days":      3,
    "pdx":           "C48.1",
    "adx":           ["E11.9"],
    "achi_codes":    ["96211-00"],
    "hours_mech_vent": None,
    "care_type":     "01",
    # Pre-set ACS scores with a review-band ADX
    "acs_pdx_score": 6,
    "acs_adx_scores": [
        {"code": "E11.9", "score": 3, "action": "review",
         "justification": "Score in review band", "is_principal": False, "score_breakdown": {}}
    ],
}
s6 = engine.process_episode(ep6)
check("T6  PDX meets coding threshold (≥5)", s6.acs_pdx_score >= ACS_THRESHOLD_CODE, True)
check_true("T6  review flag for E11.9 ADX",
           any("REVIEW" in f and "E11.9" in f for f in s6.flags))
check("T6  justification mentions ACS score",
      "ACS 0001" in s6.coding_justification, True)

# ── T7: to_dict() output is complete and FHIR-compatible ──────────────────
print("\nT7  FHIR-compatible output schema")
s7 = engine.process_episode({**ep1, "episode_id": "T7-FHIR"})
d = s7.to_dict()
required_keys = [
    "episode_id", "suggestion_id", "approval_status",
    "proposed_codes", "acs_scores", "grouper_result",
    "validation_result", "provenance", "flags",
    "created_at", "engine_version",
]
check("T7  all required keys present", all(k in d for k in required_keys), True)
check("T7  proposed_codes has ar_drg", "ar_drg" in d["proposed_codes"], True)
check("T7  provenance has achi_trigger", "achi_trigger" in d["provenance"], True)
check("T7  grouper_result has step_trace",
      "step_trace" in d["grouper_result"], True)
check("T7  validation_result has summary",
      "summary" in d["validation_result"], True)
check("T7  engine_version = V11.0", d["engine_version"], "V11.0")

# ── T8: EpisodeRecord round-trip ──────────────────────────────────────────
print("\nT8  EpisodeRecord from_dict / to_dict round-trip")
raw = {
    "episode_id": "RT-001", "patient_age": 45, "patient_sex": "Male",
    "pdx": "k80.20", "adx": ["e11.9", "i10"],
    "achi_codes": ["30445-00"],
    "los_days": 3, "same_day": False,
    "separation_mode": "discharge_home",
    "acs_pdx_score": 5,
}
ep = EpisodeRecord.from_dict(raw)
check("T8  PDX uppercased", ep.pdx, "K80.20")
check("T8  ADX uppercased", ep.adx[0], "E11.9")
check("T8  acs_pdx_score preserved", ep.acs_pdx_score, 5)
rt = ep.to_grouper_input()
check("T8  grouper_input has pdx", rt["pdx"], "K80.20")
check_true("T8  grouper_input has achi_codes", "achi_codes" in rt)

# ── T9: process() convenience function ────────────────────────────────────
print("\nT9  process() convenience function")
s9 = process({**ep1, "episode_id": "T9-PROC"})
check("T9  returns CodingSuggestion", isinstance(s9, CodingSuggestion), True)
check("T9  AR-DRG = G13Z", s9.ar_drg_code, "G13Z")

# ── T10: approve() requires non-empty physician_id ────────────────────────
print("\nT10 approve() guard")
s10 = engine.process_episode({**ep1, "episode_id": "T10-GUARD"})
try:
    s10.approve("")
    check("T10 empty physician_id rejected", False, True)
except ValueError:
    check("T10 empty physician_id rejected", True, True)

try:
    s10.approve("   ")
    check("T10 whitespace physician_id rejected", False, True)
except ValueError:
    check("T10 whitespace physician_id rejected", True, True)

# ---------------------------------------------------------------------------
passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)
print(f"\n{passed}/{len(results)} passed  |  {failed} failed")
if failed == 0:
    print("ALL GREEN ✓")
else:
    print("FAILURES — review above")
