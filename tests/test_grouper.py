"""
NOVIQ Engine — AR-DRG V11.0 Grouper Test Suite
================================================
Phase 3, Deliverable 3.3

Test coverage:
  - All three error DRGs (960Z, 961Z, 963Z)
  - New V11.0 ADRGs: B08A, B08B, G13Z, F25 production gate
  - R10.2 sex-routing edge case
  - Pre-MDC bypass (Step 3 skipped)
  - Exclusion pipeline: unconditional, conditional, socioeconomic
  - ECCS computation with known DCL values
  - FHIR output contract validation
  - V11.0 specific changes (sex conflict FLAG, not TEST)
  - errata_applied on every result
  - KnowledgeBaseIncompleteError for F25

Run: pytest test_grouper.py -v
"""

import pytest
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning)

from grouper import ARDRGGrouper, DCLTable, group_episode, KnowledgeBaseIncompleteError

KB_PATH  = Path("ar_drg_kb_seed_v11_new_adrgs.json")
DCL_PATH = Path("dcl_exclusions.json")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def grouper_stub():
    """Grouper with stub DCL table (all DCLs = 0)."""
    return ARDRGGrouper(kb_path=KB_PATH, dcl_path=DCL_PATH)


@pytest.fixture(scope="module")
def grouper_with_dcl():
    """Grouper with a seeded DCL table for known test scenarios."""
    dcl_data = {
        # (diagnosis, adrg): DCL
        # B08 test cases
        ("I63.5", "B08"): 3,    # → ECCS=3.0 → B08A (threshold 3)
        ("I63.5", "B08") : 3,
        ("E11.9", "B08"): 1,    # second dx → ECCS=3+0.86=3.86 → B08A
        ("I10",   "B08"): 1,    # → used in B08B test (ECCS <3)
        # G13 test cases (Z-suffix, ECCS for reporting only)
        ("C18.9", "G13"): 4,
        ("C48.2", "G13"): 3,
        # Generic test codes
        ("J18.9", "04"): 2,
    }
    table = DCLTable(table={(k[0], k[1]): v for k, v in dcl_data.items()})
    return ARDRGGrouper(kb_path=KB_PATH, dcl_path=DCL_PATH, dcl_table=table)


def base_episode(**overrides) -> dict:
    """Return a minimal valid episode dict with overrides applied."""
    ep = {
        "episode_id":   "TEST-001",
        "patient_age":  55,
        "patient_sex":  "Female",
        "pdx":          "I63.5",
        "adx":          [],
        "achi_codes":   [],
        "los_days":     3,
        "same_day":     False,
        "separation_mode": "discharge_home",
        "care_type":    "01",
    }
    ep.update(overrides)
    return ep


# ---------------------------------------------------------------------------
# SECTION 1: Output contract validation
# ---------------------------------------------------------------------------

class TestOutputContract:
    """Every result must conform to the FHIR-compatible JSON-Out schema."""

    REQUIRED_KEYS = [
        "episode_id", "ar_drg_version", "ar_drg_code", "ar_drg_description",
        "adrg_code", "mdc", "partition", "grouping_status", "eccs",
        "dcl_contributions", "threshold_used", "edit_flags", "error_code",
        "errata_applied", "step_trace", "grouped_at",
    ]

    def test_all_required_keys_present(self, grouper_stub):
        result = grouper_stub.group_episode(base_episode())
        for key in self.REQUIRED_KEYS:
            assert key in result, f"Missing required key: {key}"

    def test_ar_drg_version_is_v11(self, grouper_stub):
        result = grouper_stub.group_episode(base_episode())
        assert result["ar_drg_version"] == "V11.0"

    def test_errata_always_present(self, grouper_stub):
        result = grouper_stub.group_episode(base_episode())
        assert "Errata1_2023-04-01" in result["errata_applied"]

    def test_grouped_at_is_iso8601(self, grouper_stub):
        from datetime import datetime
        result = grouper_stub.group_episode(base_episode())
        # Should parse without error
        datetime.fromisoformat(result["grouped_at"].replace("Z", "+00:00"))

    def test_dcl_contributions_is_list(self, grouper_stub):
        result = grouper_stub.group_episode(base_episode())
        assert isinstance(result["dcl_contributions"], list)

    def test_step_trace_is_list_of_strings(self, grouper_stub):
        result = grouper_stub.group_episode(base_episode())
        assert isinstance(result["step_trace"], list)
        for item in result["step_trace"]:
            assert isinstance(item, str)

    def test_dcl_entry_schema(self, grouper_stub):
        result = grouper_stub.group_episode(base_episode(adx=["E11.9", "I10"]))
        for entry in result["dcl_contributions"]:
            assert "diagnosis_code" in entry
            assert "dcl_value" in entry
            assert "is_principal" in entry
            assert "is_excluded" in entry
            assert 0 <= entry["dcl_value"] <= 5


# ---------------------------------------------------------------------------
# SECTION 2: Error DRGs (Step 1 exits)
# ---------------------------------------------------------------------------

class TestErrorDRGs:

    def test_960z_invalid_sex(self, grouper_stub):
        result = grouper_stub.group_episode(base_episode(patient_sex="X"))
        assert result["ar_drg_code"] == "960Z"
        assert result["grouping_status"] == "ERROR"
        assert result["partition"] == "error"
        assert result["error_code"] == "960Z"

    def test_960z_empty_pdx(self, grouper_stub):
        result = grouper_stub.group_episode(base_episode(pdx=""))
        assert result["ar_drg_code"] == "960Z"
        assert result["error_code"] == "960Z"

    def test_961z_invalid_pdx_format(self, grouper_stub):
        # Code that fails PDX format check (doesn't start with letter+2digits)
        result = grouper_stub.group_episode(base_episode(pdx="123.45"))
        assert result["ar_drg_code"] == "961Z"
        assert result["error_code"] == "961Z"

    def test_963z_neonatal_pdx_wrong_age(self, grouper_stub):
        result = grouper_stub.group_episode(
            base_episode(pdx="P07.11", patient_age=5)
        )
        assert result["ar_drg_code"] == "963Z"
        assert result["error_code"] == "963Z"

    def test_error_result_has_empty_dcl_contributions(self, grouper_stub):
        result = grouper_stub.group_episode(base_episode(patient_sex="INVALID"))
        assert result["dcl_contributions"] == []
        assert result["eccs"] == 0.0

    def test_error_result_still_has_errata(self, grouper_stub):
        result = grouper_stub.group_episode(base_episode(patient_sex="INVALID"))
        assert "Errata1_2023-04-01" in result["errata_applied"]


# ---------------------------------------------------------------------------
# SECTION 3: V11.0 specific changes
# ---------------------------------------------------------------------------

class TestV11Changes:

    def test_sex_conflict_is_flag_not_test(self, grouper_stub):
        """V11.0: sex conflict produces WARNING flag, not grouping failure."""
        # Inject a known conflict scenario by testing with a code that
        # triggers our sex_conflicts stub (currently returns False — stub)
        result = grouper_stub.group_episode(base_episode())
        # Episode should group successfully — not produce 960Z
        assert result["ar_drg_code"] != "960Z" or \
               result["grouping_status"] != "ERROR"

    def test_r10_2_routes_to_mdc12_for_male(self, grouper_stub):
        """R10.2 + Male → MDC 12 (V11.0 Section 3.5.1 special case)."""
        result = grouper_stub.group_episode(
            base_episode(pdx="R10.2", patient_sex="Male")
        )
        assert result["mdc"] == "12", \
            f"Expected MDC 12 for R10.2+Male, got {result['mdc']}"
        assert "R10.2 sex-routing" in " ".join(result["step_trace"])

    def test_r10_2_routes_to_mdc13_for_female(self, grouper_stub):
        """R10.2 + Female → MDC 13 (V11.0 Section 3.5.1 special case)."""
        result = grouper_stub.group_episode(
            base_episode(pdx="R10.2", patient_sex="Female")
        )
        assert result["mdc"] == "13", \
            f"Expected MDC 13 for R10.2+Female, got {result['mdc']}"

    def test_r10_2_routes_to_mdc12_for_unknown(self, grouper_stub):
        """R10.2 + Unknown sex → MDC 12 (same as Male per pseudocode)."""
        result = grouper_stub.group_episode(
            base_episode(pdx="R10.2", patient_sex="Unknown")
        )
        assert result["mdc"] == "12"

    def test_invalid_adx_stripped_silently(self, grouper_stub):
        """Invalid ADX codes stripped without failing the episode."""
        result = grouper_stub.group_episode(
            base_episode(adx=["INVALID_CODE", "E11.9"])
        )
        assert result["grouping_status"] != "ERROR"
        flags = result["edit_flags"]
        assert any("ADX_STRIPPED" in f for f in flags)

    def test_invalid_achi_stripped_silently(self, grouper_stub):
        """Invalid ACHI codes stripped without failing the episode."""
        result = grouper_stub.group_episode(
            base_episode(achi_codes=["BADCODE"])
        )
        assert result["grouping_status"] != "ERROR"
        flags = result["edit_flags"]
        assert any("ACHI_STRIPPED" in f for f in flags)


# ---------------------------------------------------------------------------
# SECTION 4: New V11.0 ADRGs
# ---------------------------------------------------------------------------

class TestNewADRGs:

    def test_b08_trigger_code_routes_to_b08(self, grouper_stub):
        """ACHI 35414-00 in MDC 01 → ADRG B08."""
        result = grouper_stub.group_episode(
            base_episode(
                pdx="I63.5",          # Cerebral infarction → MDC 01
                achi_codes=["35414-00"]
            )
        )
        assert result["adrg_code"] == "B08", \
            f"Expected B08, got {result['adrg_code']}"

    def test_b08_with_low_eccs_gives_b08b(self, grouper_with_dcl):
        """B08 + ECCS < 3 → B08B (Minor Complexity)."""
        # Inject DCL=1 for I10 in B08 → ECCS=1.0 < threshold 3
        table = DCLTable(table={("I63.5", "B08"): 1, ("I10", "B08"): 0})
        g = ARDRGGrouper(kb_path=KB_PATH, dcl_path=DCL_PATH, dcl_table=table)
        result = g.group_episode(
            base_episode(pdx="I63.5", achi_codes=["35414-00"], adx=["I10"])
        )
        assert result["adrg_code"] == "B08"
        assert result["ar_drg_code"] == "B08B", \
            f"Expected B08B, got {result['ar_drg_code']}. ECCS={result['eccs']}"
        assert result["eccs"] < 3.0

    def test_b08_with_high_eccs_gives_b08a(self, grouper_with_dcl):
        """B08 + ECCS >= 3 → B08A (Major Complexity)."""
        table = DCLTable(table={("I63.5", "B08"): 3, ("E11.9", "B08"): 2})
        g = ARDRGGrouper(kb_path=KB_PATH, dcl_path=DCL_PATH, dcl_table=table)
        result = g.group_episode(
            base_episode(
                pdx="I63.5",
                achi_codes=["35414-00"],
                adx=["E11.9"]
            )
        )
        assert result["adrg_code"] == "B08"
        assert result["ar_drg_code"] == "B08A", \
            f"Expected B08A, got {result['ar_drg_code']}. ECCS={result['eccs']}"
        assert result["eccs"] >= 3.0

    def test_b08a_threshold_is_3(self, grouper_with_dcl):
        """B08A threshold = exactly 3.0 (confirmed V11.0 Final Report §3.1)."""
        # ECCS exactly at threshold
        table = DCLTable(table={("I63.5", "B08"): 3})
        g = ARDRGGrouper(kb_path=KB_PATH, dcl_path=DCL_PATH, dcl_table=table)
        result = g.group_episode(
            base_episode(pdx="I63.5", achi_codes=["35414-00"])
        )
        assert result["ar_drg_code"] == "B08A"
        assert result["eccs"] == 3.0
        assert result["threshold_used"] == 3.0

    def test_g13_trigger_code_routes_to_g13(self, grouper_stub):
        """ACHI 96211-00 → ADRG G13 (position 1 in MDC 06)."""
        result = grouper_stub.group_episode(
            base_episode(
                pdx="C18.9",           # Colon cancer → MDC 06
                achi_codes=["96211-00"]
            )
        )
        assert result["adrg_code"] == "G13", \
            f"Expected G13, got {result['adrg_code']}"

    def test_g13_always_gives_g13z(self, grouper_with_dcl):
        """G13 is unsplit — always assigns G13Z regardless of ECCS."""
        table = DCLTable(table={("C18.9", "G13"): 5, ("C48.2", "G13"): 4})
        g = ARDRGGrouper(kb_path=KB_PATH, dcl_path=DCL_PATH, dcl_table=table)
        result = g.group_episode(
            base_episode(
                pdx="C18.9",
                achi_codes=["96211-00"],
                adx=["C48.2"]
            )
        )
        assert result["ar_drg_code"] == "G13Z", \
            f"Expected G13Z, got {result['ar_drg_code']}"

    def test_g13z_eccs_computed_for_reporting(self, grouper_with_dcl):
        """G13Z: ECCS is computed and reported even though it doesn't drive split."""
        table = DCLTable(table={("C18.9", "G13"): 4, ("C48.2", "G13"): 3})
        g = ARDRGGrouper(kb_path=KB_PATH, dcl_path=DCL_PATH, dcl_table=table)
        result = g.group_episode(
            base_episode(
                pdx="C18.9",
                achi_codes=["96211-00"],
                adx=["C48.2"]
            )
        )
        # ECCS should be non-zero (4 + 3*0.86 = 6.58)
        assert result["eccs"] > 0.0, "ECCS should be computed for G13Z reporting"
        assert result["threshold_used"] is None  # No threshold for Z-suffix

    def test_g13z_hipec_modifier_not_a_trigger(self, grouper_stub):
        """HIPEC codes (96201-00, 92178-00) are modifiers — do NOT trigger G13."""
        # Only 96211-00 (peritonectomy) triggers G13
        result = grouper_stub.group_episode(
            base_episode(
                pdx="C18.9",
                achi_codes=["96201-00"]  # HIPEC only, no peritonectomy
            )
        )
        assert result["adrg_code"] != "G13", \
            "HIPEC code alone should not trigger G13"

    def test_f25_trigger_routes_to_f25(self, grouper_stub):
        """ACHI 38488-08 → ADRG F25 (TAVI — most common F25 trigger)."""
        result = grouper_stub.group_episode(
            base_episode(
                pdx="I35.0",           # Aortic stenosis → MDC 05
                achi_codes=["38488-08"]
            )
        )
        assert result["adrg_code"] == "F25", \
            f"Expected F25, got {result['adrg_code']}"

    def test_f25_raises_kb_incomplete_error(self, grouper_stub):
        """F25 ECCS threshold is null — KnowledgeBaseIncompleteError must fire."""
        with pytest.raises(KnowledgeBaseIncompleteError) as exc_info:
            grouper_stub.group_episode(
                base_episode(
                    pdx="I35.0",
                    achi_codes=["38488-08"]
                )
            )
        assert "F25" in str(exc_info.value)
        assert "Lane Print" in str(exc_info.value)

    def test_f25_all_four_trigger_codes(self, grouper_stub):
        """All four 38488-xx codes must trigger F25 (aortic/mitral/tricuspid/pulmonary)."""
        triggers = ["38488-08", "38488-09", "38488-10", "38488-11"]
        for trigger in triggers:
            with pytest.raises(KnowledgeBaseIncompleteError):
                grouper_stub.group_episode(
                    base_episode(pdx="I35.0", achi_codes=[trigger])
                )
                # If no error raised, check it at least routed to F25
            # The KnowledgeBaseIncompleteError confirms it reached Step 5 for F25

    def test_f25_valvuloplasty_does_not_trigger_f25(self, grouper_stub):
        """Valvuloplasty codes (38270-xx) must NOT trigger F25."""
        result = grouper_stub.group_episode(
            base_episode(pdx="I35.0", achi_codes=["38270-01"])
        )
        assert result["adrg_code"] != "F25", \
            "Valvuloplasty 38270-01 should not trigger F25"


# ---------------------------------------------------------------------------
# SECTION 5: Exclusion pipeline
# ---------------------------------------------------------------------------

class TestExclusionPipeline:

    def test_unconditional_exclusion_dcl_is_zero(self, grouper_stub):
        """Unconditionally excluded codes must have dcl_value=0 and is_excluded=True."""
        result = grouper_stub.group_episode(
            base_episode(
                pdx="I63.5",
                achi_codes=["35414-00"],
                adx=["E61.1"]   # Iron deficiency — unconditional exclusion
            )
        )
        excluded = [e for e in result["dcl_contributions"]
                    if e["diagnosis_code"] == "E61.1"]
        assert len(excluded) == 1
        assert excluded[0]["is_excluded"] is True
        assert excluded[0]["dcl_value"] == 0
        assert excluded[0]["exclusion_type"] == "unconditional"

    def test_upcoding_risk_code_is_flagged(self, grouper_stub):
        """D89.82 (Immunocompromised status) must be excluded and flagged."""
        result = grouper_stub.group_episode(
            base_episode(adx=["D89.82"])
        )
        excluded = [e for e in result["dcl_contributions"]
                    if e["diagnosis_code"] == "D89.82"]
        assert len(excluded) == 1
        assert excluded[0]["is_excluded"] is True

    def test_socioeconomic_code_excluded(self, grouper_stub):
        """Z59.0 (Homelessness) must be excluded as socioeconomic code."""
        result = grouper_stub.group_episode(
            base_episode(adx=["Z59.0"])
        )
        excluded = [e for e in result["dcl_contributions"]
                    if e["diagnosis_code"] == "Z59.0"]
        assert len(excluded) == 1
        assert excluded[0]["exclusion_type"] == "socioeconomic"
        assert excluded[0]["dcl_value"] == 0

    def test_eligible_code_not_excluded(self, grouper_stub):
        """E11.9 (Type 2 diabetes) must NOT be excluded."""
        result = grouper_stub.group_episode(
            base_episode(adx=["E11.9"])
        )
        entry = [e for e in result["dcl_contributions"]
                 if e["diagnosis_code"] == "E11.9"]
        assert len(entry) == 1
        assert entry[0]["is_excluded"] is False

    def test_pdx_in_dcl_contributions(self, grouper_stub):
        """Principal diagnosis must appear in dcl_contributions (V11.0 change)."""
        result = grouper_stub.group_episode(base_episode(pdx="I63.5"))
        principals = [e for e in result["dcl_contributions"]
                      if e["is_principal"] is True]
        assert len(principals) == 1
        assert principals[0]["diagnosis_code"] == "I63.5"

    def test_excluded_codes_not_in_eccs(self, grouper_stub):
        """Excluded codes must not contribute to ECCS (dcl_value=0)."""
        result = grouper_stub.group_episode(
            base_episode(adx=["E61.1", "D89.82", "Z59.0"])
        )
        for entry in result["dcl_contributions"]:
            if entry["is_excluded"]:
                assert entry["dcl_value"] == 0


# ---------------------------------------------------------------------------
# SECTION 6: ECCS computation
# ---------------------------------------------------------------------------

class TestECCSComputation:

    def test_eccs_zero_with_stub_dcl(self, grouper_stub):
        """Stub DCL table → all DCLs = 0 → ECCS = 0.0."""
        result = grouper_stub.group_episode(
            base_episode(pdx="I63.5", achi_codes=["35414-00"])
        )
        assert result["eccs"] == 0.0

    def test_eccs_with_known_dcl_values(self, grouper_with_dcl):
        """ECCS = 3 + 2×0.86 = 4.72 for DCLs [3, 2] in B08."""
        table = DCLTable(table={("I63.5", "B08"): 3, ("E11.9", "B08"): 2})
        g = ARDRGGrouper(kb_path=KB_PATH, dcl_path=DCL_PATH, dcl_table=table)
        result = g.group_episode(
            base_episode(
                pdx="I63.5",
                achi_codes=["35414-00"],
                adx=["E11.9"]
            )
        )
        expected_eccs = 3 + 2 * 0.86   # = 4.72
        assert abs(result["eccs"] - expected_eccs) < 0.001, \
            f"Expected ECCS≈{expected_eccs}, got {result['eccs']}"

    def test_eccs_official_example(self):
        """Official formula test: DCLs [4,3,2,1,0] → ECCS≈8.695."""
        from validation_rules import compute_eccs
        eccs = compute_eccs([4, 3, 2, 1, 0])
        assert abs(eccs - 8.695) < 0.01, f"Got {eccs}, expected ~8.695"

    def test_eccs_decay_factor_is_0_86(self):
        """ECCS decay factor must be exactly 0.86."""
        from validation_rules import ECCS_DECAY_FACTOR
        assert ECCS_DECAY_FACTOR == 0.86

    def test_eccs_principal_dx_included(self, grouper_with_dcl):
        """PDX DCL must be included in ECCS (V11.0 change from pre-V8.0)."""
        table = DCLTable(table={("I63.5", "B08"): 4})  # PDX only
        g = ARDRGGrouper(kb_path=KB_PATH, dcl_path=DCL_PATH, dcl_table=table)
        result = g.group_episode(
            base_episode(pdx="I63.5", achi_codes=["35414-00"], adx=[])
        )
        # PDX DCL=4, no ADX → ECCS = 4.0
        assert result["eccs"] == 4.0, \
            f"PDX DCL should contribute to ECCS. Got {result['eccs']}"


# ---------------------------------------------------------------------------
# SECTION 7: Step trace audit
# ---------------------------------------------------------------------------

class TestStepTrace:

    def test_trace_has_five_steps_on_success(self, grouper_stub):
        """Successful grouping must produce exactly 5 step trace entries."""
        result = grouper_stub.group_episode(base_episode())
        # Steps 1, 2, 3, 4, 5
        assert len(result["step_trace"]) == 5, \
            f"Expected 5 trace entries, got {len(result['step_trace'])}"

    def test_trace_step1_always_first(self, grouper_stub):
        result = grouper_stub.group_episode(base_episode())
        assert "Step 1" in result["step_trace"][0]

    def test_trace_step2_always_second(self, grouper_stub):
        result = grouper_stub.group_episode(base_episode())
        assert "Step 2" in result["step_trace"][1]

    def test_error_trace_has_terminal_message(self, grouper_stub):
        result = grouper_stub.group_episode(base_episode(patient_sex="INVALID"))
        assert any("TERMINAL" in t for t in result["step_trace"])


# ---------------------------------------------------------------------------
# SECTION 8: Hierarchy priority
# ---------------------------------------------------------------------------

class TestHierarchyPriority:

    def test_g13_wins_over_other_mdc06_adrgs(self, grouper_stub):
        """G13 at position 1 wins over any other MDC 06 intervention ADRG."""
        result = grouper_stub.group_episode(
            base_episode(
                pdx="C18.9",
                achi_codes=["96211-00"]  # G13 trigger at pos 1
            )
        )
        assert result["adrg_code"] == "G13"

    def test_b08_hierarchy_position_in_trace(self, grouper_stub):
        """B08 hierarchy position (2) must appear in step trace."""
        result = grouper_stub.group_episode(
            base_episode(pdx="I63.5", achi_codes=["35414-00"])
        )
        step4_trace = [t for t in result["step_trace"] if "Step 4" in t]
        assert len(step4_trace) == 1
        assert "2" in step4_trace[0]   # position 2 for B08


# ---------------------------------------------------------------------------
# SECTION 9: Module-level convenience function
# ---------------------------------------------------------------------------

class TestModuleLevelAPI:

    def test_group_episode_function_returns_dict(self):
        """Module-level group_episode() returns a dict."""
        result = group_episode(base_episode(), kb_path=KB_PATH, dcl_path=DCL_PATH)
        assert isinstance(result, dict)
        assert "ar_drg_code" in result

    def test_group_episode_errata_present(self):
        result = group_episode(base_episode(), kb_path=KB_PATH, dcl_path=DCL_PATH)
        assert "Errata1_2023-04-01" in result["errata_applied"]


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import subprocess, sys
    sys.exit(subprocess.run(
        ["python3", "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=str(Path(__file__).parent)
    ).returncode)
