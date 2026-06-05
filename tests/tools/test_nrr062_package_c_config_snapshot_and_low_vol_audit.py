from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[2]
    file_path = (
        repo_root
        / "artifacts"
        / "_tmp"
        / "phenix_nrr062_package_c_config_snapshot_and_low_vol_audit.py"
    )
    spec = importlib.util.spec_from_file_location(
        "nrr062_package_c", file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load package C helper module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helper = _load_module()


def test_find_paths_by_key_discovers_nested_low_vol_gate() -> None:
    payload = {
        "decision_making": {
            "low_vol_cost_floor_gate": {
                "enabled": True,
                "thresholds": {"min_direction_confidence_by_regime": {"LOW_VOLATILITY": 0.25}},
            }
        }
    }

    paths = helper.find_paths_by_key(payload, "low_vol_cost_floor_gate")

    assert paths == [("decision_making", "low_vol_cost_floor_gate")]
    assert helper.value_at_path(payload, paths[0])["enabled"] is True


def test_summarize_class_counts_marks_no_evidence_for_empty_rows() -> None:
    counts = helper.summarize_class_counts([])

    assert counts[helper.NO_LOW_VOL_ACCEPTED_EVIDENCE] == 1
    assert counts["CANONICAL_ACCEPTED_LOW_VOL_CLOSE"] == 0


def test_determine_comparison_status_blocks_without_accepted_rows() -> None:
    status, reason = helper.determine_comparison_status(
        {
            "CANONICAL_ACCEPTED_LOW_VOL_CLOSE": 0,
            "ACCEPTED_LOW_VOL_DECISION_NO_CLOSE": 0,
            "LOW_VOL_CLOSE_NON_CANONICAL": 0,
            "LOW_VOL_SIDE_CAR_CLOSE_ONLY": 0,
            "LOW_VOL_DIAGNOSTIC_ONLY": 3,
            helper.NO_LOW_VOL_ACCEPTED_EVIDENCE: 0,
        }
    )

    assert status == helper.ACCEPTED_LOW_VOL_COMPARISON_BLOCKED
    assert "No accepted LOW_VOL" in reason


def test_extract_nrr_config_reference_reads_low_vol_gate() -> None:
    parsed = {
        "config/aurora/domains.yaml": {
            "parsed_payload": {
                "decision_making": {
                    "directional_sanity": {
                        "nrr027_enabled": False,
                        "min_regime_confidence": 0.35,
                    },
                    "low_vol_cost_floor_gate": {
                        "enabled": True,
                        "enforce_in_modes": ["testnet"],
                        "observe_only_in_modes": ["live"],
                        "regimes": ["LOW_VOLATILITY"],
                        "thresholds": {
                            "min_regime_confidence_by_regime": {"LOW_VOLATILITY": 0.39},
                            "min_direction_confidence_by_regime": {"LOW_VOLATILITY": 0.25},
                            "min_raw_score_by_regime": {"LOW_VOLATILITY": 0.25},
                        },
                        "direction_confidence": {
                            "raw_signed_score_sources": ["signal_score"],
                            "normalized_confidence_sources": ["strategy_confidence"],
                        },
                    },
                }
            },
            "parse_status": "PARSED_MAPPING",
            "top_level_keys": ["decision_making"],
            "parse_error": None,
        }
    }

    payload = helper.extract_nrr_config_reference(
        repo_root=Path("."),
        parsed_payloads=parsed,
        reference_manifest_path=Path(
            "calibrators/datasets/config_snapshot_reference_post_03u/config_snapshot_reference_manifest.json"),
    )

    gate = payload["nrr062_low_vol_cost_floor_gate"]
    assert gate["enabled"] is True
    assert gate["thresholds"]["min_regime_confidence_by_regime"]["LOW_VOLATILITY"] == 0.39
    assert payload["nrr027_030_reference"]["NRR-027"]["current_reference_state"] is False


def test_reject_objective_rows_are_not_treated_as_accepted_comparison_evidence() -> None:
    status, reason = helper.determine_comparison_status(
        {
            "CANONICAL_ACCEPTED_LOW_VOL_CLOSE": 0,
            "ACCEPTED_LOW_VOL_DECISION_NO_CLOSE": 0,
            "LOW_VOL_CLOSE_NON_CANONICAL": 0,
            "LOW_VOL_SIDE_CAR_CLOSE_ONLY": 0,
            "LOW_VOL_DIAGNOSTIC_ONLY": 1,
            helper.NO_LOW_VOL_ACCEPTED_EVIDENCE: 0,
        }
    )

    assert status == helper.ACCEPTED_LOW_VOL_COMPARISON_BLOCKED
    assert "accepted LOW_VOL close or accepted-decision evidence" in reason
