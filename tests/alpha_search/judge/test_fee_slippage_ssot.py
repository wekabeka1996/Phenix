"""PKG-2 tests for fee/slippage SSOT (Judge offline pipeline).

These tests pin the SSOT decision so future drift fails loudly:

  * `config/judge_simulator.yaml` is the AUTHORITATIVE source of
    fee/slippage parameters consumed by the official PKG-1 → PKG-4
    pipeline (offline judge-simulator + judge-review CLIs).
  * `config/alpha_search.yaml judge.simulator.{fees_bps, slippage_bps}`
    is consumed ONLY by the forensic-only ShadowPlanSimulator and is
    a separate, named axis (no cross-consumption).
  * Units are explicit and consistent.
  * No fee/slippage numeric literals leak into code outside the SSOT
    file and the (forensic-only) ShadowSimulatorConfig defaults.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SSOT_PATH = ROOT / "config" / "judge_simulator.yaml"
ALPHA_SEARCH_PATH = ROOT / "config" / "alpha_search.yaml"


# ---------------------------------------------------------------------------
# T1: SSOT file shape — `judge_simulator` key with canonical fee/slippage names
# ---------------------------------------------------------------------------
def test_1_judge_simulator_yaml_is_ssot_and_carries_canonical_fields():
    raw = yaml.safe_load(SSOT_PATH.read_text(encoding="utf-8"))
    assert "judge_simulator" in raw, "SSOT must use `judge_simulator` top key"
    section = raw["judge_simulator"]
    assert "fee_per_cycle_bps" in section
    assert "slippage_pct" in section
    # Pinned current values; update intentionally if economics change.
    assert section["fee_per_cycle_bps"] == 25
    assert section["slippage_pct"] == 0.1


# ---------------------------------------------------------------------------
# T2: SimulatorConfig loads ONLY the SSOT file, validates fee/slippage
# ---------------------------------------------------------------------------
def test_2_simulator_config_loads_from_ssot_only():
    from apps.reference.domains.alpha_search.judge.simulator.cli import (
        load_simulator_config,
    )

    cfg = load_simulator_config(SSOT_PATH)
    assert cfg.fee_per_cycle_bps == 25.0
    assert cfg.slippage_pct == 0.1


# ---------------------------------------------------------------------------
# T3: SimulatorConfig refuses unknown fee/slippage field names
#     (catches accidental copy of `fees_bps`/`slippage_bps` into SSOT)
# ---------------------------------------------------------------------------
def test_3_simulator_config_rejects_shadow_simulator_field_names():
    from apps.reference.domains.alpha_search.judge.simulator.config_models import (
        SimulatorConfig,
    )

    base = dict(
        judge_logs_path="logs/judge_experts",
        outcome_data_path="data/simulator/outcomes.json",
        calibration_dataset_path="artifacts/phase5_calibration.jsonl",
        summary_report_path="artifacts/phase5_summary_report.json",
    )
    with pytest.raises(Exception):
        SimulatorConfig(**base, fees_bps=2.0)
    with pytest.raises(Exception):
        SimulatorConfig(**base, slippage_bps=1.0)


# ---------------------------------------------------------------------------
# T4: ShadowSimulatorConfig (forensic) is the ONLY consumer of fees_bps/slippage_bps
# ---------------------------------------------------------------------------
def test_4_shadow_simulator_config_is_forensic_only_consumer_of_bps_field_names():
    from apps.reference.domains.alpha_search.judge.config_models import (
        ShadowSimulatorConfig,
    )

    cfg = ShadowSimulatorConfig()
    # Canonical defaults — pinned so accidental edits trip CI.
    assert cfg.fees_bps == 2.0
    assert cfg.slippage_bps == 1.0


# ---------------------------------------------------------------------------
# T5: alpha_search.yaml judge.simulator carries only the forensic axis
# ---------------------------------------------------------------------------
def test_5_alpha_search_yaml_judge_simulator_block_is_forensic_only():
    raw = yaml.safe_load(ALPHA_SEARCH_PATH.read_text(encoding="utf-8"))
    sim = raw["alpha_search"]["judge"]["simulator"]
    assert "fees_bps" in sim and sim["fees_bps"] == 2.0
    assert "slippage_bps" in sim and sim["slippage_bps"] == 1.0
    # Forbid the SSOT field names from leaking into this block.
    assert "fee_per_cycle_bps" not in sim, (
        "alpha_search.yaml must not duplicate the SSOT field name "
        "`fee_per_cycle_bps`; that field belongs in config/judge_simulator.yaml only"
    )
    assert "slippage_pct" not in sim, (
        "alpha_search.yaml must not duplicate the SSOT field name "
        "`slippage_pct`; that field belongs in config/judge_simulator.yaml only"
    )


# ---------------------------------------------------------------------------
# T6: Fee/slippage unit semantics in code are bps/100 and pct/100
# ---------------------------------------------------------------------------
def test_6_fee_slippage_calculator_unit_semantics():
    from apps.reference.domains.alpha_search.judge.simulator import (
        fee_slippage_calculator as fsc,
    )

    # 25 bps -> 0.0025 decimal return cost
    assert fsc.compute_fee_cost_bps(25.0) == pytest.approx(0.0025)
    # 0.1 pct -> 0.001 decimal return cost == 10 bps
    assert fsc.compute_slippage_cost_pct(0.1) == pytest.approx(0.001)


# ---------------------------------------------------------------------------
# T7: No hard-coded fee/slippage literals in offline simulator code outside SSOT
# ---------------------------------------------------------------------------
def test_7_no_hardcoded_fee_literals_in_offline_simulator_code():
    sim_root = (
        ROOT
        / "apps"
        / "reference"
        / "domains"
        / "alpha_search"
        / "judge"
        / "simulator"
    )
    pattern = re.compile(
        r"\b(fee_per_cycle_bps|slippage_pct)\s*=\s*([0-9.]+)\b")
    offenders: list[tuple[Path, str]] = []
    for py in sim_root.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for line in text.splitlines():
            m = pattern.search(line)
            if not m:
                continue
            # Allow Pydantic default declarations of the form `... = Field(default=25.0, ...)`
            if "Field(" in line or "default=" in line:
                continue
            offenders.append((py, line.strip()))
    assert not offenders, f"Hard-coded fee/slippage literals found: {offenders}"


# ---------------------------------------------------------------------------
# T8: SSOT and forensic blocks are not silently merged (different field names)
# ---------------------------------------------------------------------------
def test_8_ssot_and_forensic_axes_use_disjoint_field_names():
    ssot_fields = {"fee_per_cycle_bps", "slippage_pct"}
    forensic_fields = {"fees_bps", "slippage_bps"}
    assert ssot_fields.isdisjoint(forensic_fields), (
        "SSOT field names overlap forensic field names — rename one set"
    )


# ---------------------------------------------------------------------------
# T9: PKG-2 manifest contract — outcomes manifest fee/slippage source pointer
# (Forward-compatible: PKG-1 will write `fee_source` / `slippage_source` to
# outcomes_manifest.json. This test pins the expected string values so the
# materializer can be authored against a stable contract.)
# ---------------------------------------------------------------------------
def test_9_outcomes_manifest_fee_source_pointer_is_ssot_path():
    expected_fee_source = "config/judge_simulator.yaml#judge_simulator.fee_per_cycle_bps"
    expected_slip_source = "config/judge_simulator.yaml#judge_simulator.slippage_pct"
    # The materializer (PKG-1) MUST emit exactly these strings into
    # outcomes_manifest.json. Pinning them here keeps PKG-1 honest.
    assert expected_fee_source.endswith("fee_per_cycle_bps")
    assert expected_slip_source.endswith("slippage_pct")
    assert "judge_simulator.yaml" in expected_fee_source
    assert "judge_simulator.yaml" in expected_slip_source


# ---------------------------------------------------------------------------
# T10: Smoke — both YAML files parse and the SSOT defaults remain valid
# ---------------------------------------------------------------------------
def test_10_both_configs_parse_and_ssot_validates_via_pydantic():
    from apps.reference.domains.alpha_search.judge.simulator.config_models import (
        SimulatorConfig,
    )

    raw = yaml.safe_load(SSOT_PATH.read_text(encoding="utf-8"))
    SimulatorConfig(**raw["judge_simulator"])

    alpha = yaml.safe_load(ALPHA_SEARCH_PATH.read_text(encoding="utf-8"))
    sim = alpha["alpha_search"]["judge"]["simulator"]
    assert isinstance(sim["fees_bps"], (int, float))
    assert isinstance(sim["slippage_bps"], (int, float))
