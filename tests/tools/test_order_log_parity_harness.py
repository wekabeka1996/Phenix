from pathlib import Path
from types import SimpleNamespace

from tests.tools.test_order_log_scenario_backtest_core import _build_runtime
from tools.order_log_scenario_backtest.models import CanonicalEntry
from tools.order_log_scenario_backtest.parity_harness import run_parity_harness


def test_parity_harness_emits_required_artifacts(tmp_path: Path, monkeypatch) -> None:
    workspace_root, runtime_root, report_root, _ = _build_runtime(tmp_path)
    canonical_entries = [
        CanonicalEntry(
            entry_id="entry-1",
            lifecycle_id="life-1",
            rid="rid-1",
            trade_id="trade-1",
            symbol="ETHUSDT",
            side="BUY",
            strategy_id="aurora",
            entry_ts_ms=1_767_225_410_000,
            entry_time_iso="2026-01-01T00:10:10Z",
            entry_price=100.0,
            qty=1.0,
            leverage=10.0,
            timestamp_quality="exact",
            reconstruction_confidence="high",
            regime_at_entry="TREND_DOWN",
            regime_confidence_at_entry=0.30,
            regime_source="test",
        ),
        CanonicalEntry(
            entry_id="entry-2",
            lifecycle_id="life-2",
            rid="rid-2",
            trade_id="trade-2",
            symbol="BTCUSDT",
            side="SELL",
            strategy_id="aurora",
            entry_ts_ms=1_767_225_710_000,
            entry_time_iso="2026-01-01T00:15:10Z",
            entry_price=200.0,
            qty=1.0,
            leverage=10.0,
            timestamp_quality="exact",
            reconstruction_confidence="high",
            regime_at_entry="TREND_UP",
            regime_confidence_at_entry=0.30,
            regime_source="test",
        ),
    ]
    fake_config = SimpleNamespace(
        trading_mode="paper",
        domains=SimpleNamespace(
            decision_making=SimpleNamespace(
                directional_sanity=SimpleNamespace(
                    enabled=True,
                    nrr026_enabled=True,
                    nrr027_enabled=False,
                    min_abs_delta_price=0.0,
                    min_confidence=0.0,
                    min_regime_confidence=0.35,
                    min_regime_confidence_by_regime={"DEFAULT": 0.35, "TREND_UP": 0.2, "TREND_DOWN": 0.2},
                    max_regime_confidence_by_regime={"TREND_UP": 0.4},
                    consecutive_bars=1,
                    hard_veto_consecutive_bars=2,
                ),
                price_motion_sanity=SimpleNamespace(
                    enabled=False,
                    flash_window_sec=10,
                    bleed_window_sec=60,
                    flash_threshold_norm=1.0,
                    bleed_threshold_norm=0.5,
                    require_bleed_ready=True,
                ),
            )
        ),
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                safety_gates=SimpleNamespace(
                    enabled=True,
                    regime_confidence=None,
                    system_stress_policy="off",
                    stress_attenuation_factor=0.5,
                )
            )
        ),
    )

    from tools.order_log_scenario_backtest import parity_harness as mod

    def _fake_reconstruct(*_args, **_kwargs):
        return canonical_entries, [], {"status": "synthetic"}

    monkeypatch.setattr(mod, "load_runtime_config", lambda _workspace_root: fake_config)
    monkeypatch.setattr(mod, "reconstruct_canonical_entries", _fake_reconstruct)
    result = run_parity_harness(
        workspace_root=workspace_root,
        runtime_root=runtime_root,
        report_root=report_root,
        recorder_root=(workspace_root / "data" / "recorder").resolve(),
        extra_recorder_roots=[],
        strict=True,
    )

    assert result["manifest"]["status"] == "complete"
    assert (report_root / "gate_import_provenance.json").exists()
    assert (report_root / "one_day_parity_summary.json").exists()
    assert (report_root / "one_day_reject_family_matrix.json").exists()
    assert (report_root / "threshold_provenance.json").exists()
    assert (report_root / "parity_limitations.md").exists()
    assert result["parity_summary"]["threshold_provenance_retained"] is True
    assert result["parity_summary"]["behavioral_family_level_parity_passed"] is True
