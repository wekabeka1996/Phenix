"""PKG-3 tests for the Judge notional / qty / leverage contract.

These tests pin the v1 contract so any drift fails loudly:

  * Default state of `config/judge_simulator.yaml` is pct_only — the
    `economics:` block is OMITTED, USD ROI is therefore DISABLED, and no
    hidden default notional is applied anywhere.
  * When `economics:` IS provided, qty derivation is deterministic and
    qty normalization reuses the production qty_normalizer (fail-closed
    on step_size / min_qty / min_notional).
  * Symbol precision is loaded from `config/aurora/instruments.yaml` — no
    fabrication if a symbol is missing.
  * Leverage is never silently applied; ROI USD vs margin ROI is explicit.
  * The strict outcomes schema is NOT modified by PKG-3 (notional metadata
    belongs in the sidecar manifest written by PKG-1, not in outcomes.json).
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from apps.reference.domains.alpha_search.judge.simulator.config_models import (
    EconomicsConfig,
    SimulatorConfig,
)
from tools.judge.notional import (
    InstrumentPrecision,
    compute_roi_usd,
    derive_notional_for_outcome,
    derive_raw_qty,
    load_instrument_precision_map,
    manifest_pointer_strings,
)

ROOT = Path(__file__).resolve().parents[3]
SSOT_PATH = ROOT / "config" / "judge_simulator.yaml"
INSTRUMENTS_PATH = ROOT / "config" / "aurora" / "instruments.yaml"
OUTCOME_SCHEMA_PATH = (
    ROOT
    / "apps"
    / "reference"
    / "domains"
    / "alpha_search"
    / "judge"
    / "simulator"
    / "schemas"
    / "outcome_input_v1.json"
)


# ---------------------------------------------------------------------------
# T1: SSOT loads from config/judge_simulator.yaml; current state is pct_only
# ---------------------------------------------------------------------------
def test_1_notional_config_loads_from_judge_simulator_ssot():
    raw = yaml.safe_load(SSOT_PATH.read_text(encoding="utf-8"))
    section = raw["judge_simulator"]
    cfg = SimulatorConfig(**section)
    # PKG-3 v1 default: `economics:` block is omitted -> USD ROI disabled.
    assert cfg.economics is None
    assert cfg.usd_roi_enabled is False
    # ...but the SSOT is the right file (no other config carries this).
    assert "economics" not in section, (
        "PKG-3 v1: economics block must remain commented-out by default "
        "to keep USD ROI explicit-opt-in"
    )


# ---------------------------------------------------------------------------
# T2: Missing notional blocks USD ROI without hidden default
# ---------------------------------------------------------------------------
def test_2_missing_notional_blocks_usd_roi_without_hidden_default():
    cfg = SimulatorConfig(
        judge_logs_path="logs/judge_experts",
        outcome_data_path="data/simulator/outcomes.json",
        calibration_dataset_path="artifacts/phase5_calibration.jsonl",
        summary_report_path="artifacts/phase5_summary_report.json",
    )
    assert cfg.usd_roi_enabled is False
    # The manifest pointer block must explicitly mark pct_only mode.
    pointers = manifest_pointer_strings(economics_present=False)
    assert pointers["notional_mode"] == "pct_only"
    assert pointers["fixed_notional_usd"] is None
    assert pointers["roi_usd_targets"] is None
    # And EconomicsConfig itself must REJECT a missing notional value.
    with pytest.raises(Exception):
        EconomicsConfig()  # notional_usd_per_trade is required (no default)


# ---------------------------------------------------------------------------
# T3: Fixed-notional qty derivation is deterministic and exact (Decimal)
# ---------------------------------------------------------------------------
def test_3_fixed_notional_qty_derivation():
    qty = derive_raw_qty(5000.0, 100.0)
    assert qty == Decimal("50")
    # Non-trivial price; check arithmetic precision (Decimal, not float).
    qty2 = derive_raw_qty(5000.0, 145.5)
    assert qty2 == Decimal("5000") / Decimal("145.5")


# ---------------------------------------------------------------------------
# T4: qty normalization uses the instruments.yaml step_size and is fail-closed
# ---------------------------------------------------------------------------
def test_4_qty_normalization_uses_instrument_step_size():
    precision = load_instrument_precision_map(INSTRUMENTS_PATH)
    assert "BTCUSDT" in precision
    assert "SOLUSDT" in precision
    # SOLUSDT step_size=1, min_qty=1, min_notional=5
    sol = precision["SOLUSDT"]
    assert sol.step_size == Decimal("1")
    assert sol.min_qty == Decimal("1")
    assert sol.min_notional == Decimal("5")

    econ = EconomicsConfig(
        notional_usd_per_trade=5000.0,
        qty_normalization="instrument_step_size",
    )
    # SOL at 145.5 -> raw_qty = 5000/145.5 ≈ 34.36, normalized to 34 (step=1)
    res = derive_notional_for_outcome(
        symbol="SOLUSDT", entry_price=145.5, economics=econ, precision_map=precision,
    )
    assert res.ok is True
    assert res.normalized_qty == Decimal("34")
    assert res.realized_notional == Decimal("34") * Decimal("145.5")


# ---------------------------------------------------------------------------
# T5: min_notional / min_qty failures are fail-closed (no silent bump-up)
# ---------------------------------------------------------------------------
def test_5_min_notional_policy_fail_closed():
    precision = load_instrument_precision_map(INSTRUMENTS_PATH)
    # BTC at 60_000 with notional=10 -> raw_qty=0.000166, step_size=0.001 -> rounds to 0
    econ_tiny = EconomicsConfig(
        notional_usd_per_trade=10.0,
        qty_normalization="instrument_step_size",
        min_notional_policy="fail_closed",
    )
    res = derive_notional_for_outcome(
        symbol="BTCUSDT", entry_price=60_000.0,
        economics=econ_tiny, precision_map=precision,
    )
    assert res.ok is False
    # Either rounded-to-zero or below-min — both are fail-closed cases.
    assert res.why.startswith("NRR-")
    assert res.normalized_qty in (None, Decimal("0"))


# ---------------------------------------------------------------------------
# T6: Missing instrument precision fails closed (no qty fabrication)
# ---------------------------------------------------------------------------
def test_6_missing_instrument_precision_fails_closed():
    precision = load_instrument_precision_map(INSTRUMENTS_PATH)
    econ = EconomicsConfig(notional_usd_per_trade=5000.0)
    res = derive_notional_for_outcome(
        symbol="DOESNOTEXISTUSDT", entry_price=1.0,
        economics=econ, precision_map=precision,
    )
    assert res.ok is False
    assert res.why == "NRR-JUDGE-PRECISION-MISSING"
    assert res.normalized_qty is None
    assert res.leverage is None


# ---------------------------------------------------------------------------
# T7: leverage_source=none → no margin ROI claim
# ---------------------------------------------------------------------------
def test_7_leverage_source_none_means_no_margin_roi_claim():
    precision = load_instrument_precision_map(INSTRUMENTS_PATH)
    econ = EconomicsConfig(
        notional_usd_per_trade=5000.0, leverage_source="none",
    )
    res = derive_notional_for_outcome(
        symbol="SOLUSDT", entry_price=145.5,
        economics=econ, precision_map=precision,
    )
    assert res.ok is True
    assert res.leverage is None

    roi = compute_roi_usd(
        entry_price=145.5, exit_price=147.0,
        qty=res.normalized_qty, side="LONG", leverage=res.leverage,
    )
    assert roi["roi_usd_absolute"] == (
        Decimal("147.0") - Decimal("145.5")) * Decimal("34")
    # no margin ROI when leverage_source=none
    assert roi["roi_usd_margin"] is None


def test_7b_leverage_source_instruments_yaml_carries_target_leverage():
    precision = load_instrument_precision_map(INSTRUMENTS_PATH)
    econ = EconomicsConfig(
        notional_usd_per_trade=5000.0, leverage_source="instruments_yaml",
    )
    res = derive_notional_for_outcome(
        symbol="SOLUSDT", entry_price=145.5,
        economics=econ, precision_map=precision,
    )
    assert res.ok is True
    assert res.leverage == 20  # per config/aurora/instruments.yaml SOLUSDT
    roi = compute_roi_usd(
        entry_price=145.5, exit_price=147.0,
        qty=res.normalized_qty, side="LONG", leverage=res.leverage,
    )
    assert roi["roi_usd_margin"] == roi["roi_usd_absolute"] * Decimal("20")


# ---------------------------------------------------------------------------
# T8: roi_usd_targets must be loaded explicitly (no default of [5, 8])
# ---------------------------------------------------------------------------
def test_8_roi_usd_targets_loaded_explicitly():
    econ_none = EconomicsConfig(notional_usd_per_trade=5000.0)
    assert econ_none.roi_usd_targets == []
    econ_explicit = EconomicsConfig(
        notional_usd_per_trade=5000.0, roi_usd_targets=[5.0, 8.0],
    )
    assert econ_explicit.roi_usd_targets == [5.0, 8.0]
    with pytest.raises(Exception):
        EconomicsConfig(notional_usd_per_trade=5000.0, roi_usd_targets=[-1.0])


# ---------------------------------------------------------------------------
# T9: outcome_input_v1.json strict schema is NOT mutated by PKG-3
# ---------------------------------------------------------------------------
def test_9_outcome_schema_not_modified_with_notional_fields():
    schema = json.loads(OUTCOME_SCHEMA_PATH.read_text(encoding="utf-8"))
    # Top-level: still strict (additionalProperties: false).
    assert schema.get("additionalProperties") is False
    outcome_props = schema["properties"]["outcomes"]["items"]
    assert outcome_props.get("additionalProperties") is False
    # PKG-3 fields must NOT appear in the strict per-outcome schema.
    forbidden = {
        "notional_usd",
        "qty",
        "leverage",
        "margin_usd",
        "roi_usd_absolute",
        "roi_usd_margin",
        "economics",
    }
    declared = set(outcome_props["properties"].keys())
    leaks = forbidden & declared
    assert not leaks, (
        f"PKG-3 fields must live in outcomes_manifest.json sidecar, not in "
        f"outcome_input_v1.json; leaked: {sorted(leaks)}"
    )


# ---------------------------------------------------------------------------
# T10: PKG-1 manifest notional pointer strings are pinned
# ---------------------------------------------------------------------------
def test_10_pkg1_manifest_notional_pointer_strings():
    pointers_off = manifest_pointer_strings(economics_present=False)
    assert pointers_off["notional_mode"] == "pct_only"
    assert pointers_off["notional_source"] is None

    pointers_on = manifest_pointer_strings(economics_present=True)
    assert pointers_on["notional_mode"] == "explicit_usd"
    assert (
        pointers_on["notional_source"]
        == "config/judge_simulator.yaml#judge_simulator.economics"
    )
    assert (
        pointers_on["fixed_notional_usd"]
        == "config/judge_simulator.yaml#judge_simulator.economics.notional_usd_per_trade"
    )
    # All on-pointers must reference the SSOT file by path; none may be None.
    assert all(
        isinstance(v, str) and v.startswith("config/judge_simulator.yaml#")
        for k, v in pointers_on.items()
        if k != "notional_mode"
    )


# ---------------------------------------------------------------------------
# T11: SimulatorConfig accepts the `economics` block in canonical YAML shape
# ---------------------------------------------------------------------------
def test_11_simulator_config_accepts_economics_block_shape():
    raw = {
        "judge_logs_path": "logs/judge_experts",
        "outcome_data_path": "data/simulator/outcomes.json",
        "calibration_dataset_path": "artifacts/phase5_calibration.jsonl",
        "summary_report_path": "artifacts/phase5_summary_report.json",
        "fee_per_cycle_bps": 25,
        "slippage_pct": 0.1,
        "economics": {
            "notional_usd_per_trade": 5000.0,
            "leverage_source": "instruments_yaml",
            "qty_normalization": "instrument_step_size",
            "min_notional_policy": "fail_closed",
            "roi_usd_targets": [5.0, 8.0],
            "instruments_config_path": "config/aurora/instruments.yaml",
        },
    }
    cfg = SimulatorConfig(**raw)
    assert cfg.usd_roi_enabled is True
    assert cfg.economics.notional_usd_per_trade == 5000.0
    assert cfg.economics.roi_usd_targets == [5.0, 8.0]
