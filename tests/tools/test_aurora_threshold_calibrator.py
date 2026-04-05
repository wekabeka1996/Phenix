import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

import tools.calibration.calibrate_aurora_thresholds as calibrator
from tools.calibration.calibrate_aurora_thresholds import (
    CalibrationRunOutputs,
    CalibrationError,
    FeatureLogAudit,
    RecorderBar,
    ReplayMetrics,
    ReplayWindowSpec,
    THRESHOLD_SOURCE_MODE_ASSET_OVERRIDE_ONLY,
    THRESHOLD_SOURCE_MODE_LIVE_EFFECTIVE,
    ThresholdSurface,
    V2SymbolCalibration,
    _build_v2_baseline_metrics,
    _build_v2_validation_metrics,
    _candidate_blockers_for_surface,
    _extract_live_threshold_surface,
    _guardrail_failures,
    _parse_args,
    _window_spec_for_bars,
    main,
)


def _aurora_fixture() -> dict:
    return {
        "decision": {
            "signal_threshold": 0.162,
            "regime_threshold_multipliers": {
                "DEFAULT": 1.0,
                "TREND_UP": 0.1,
            },
        },
        "assets": {
            "BTCUSDT": {
                "signal_threshold": {
                    "enabled": False,
                    "value": None,
                },
                "regime_thresholds": {
                    "DEFAULT": 1.0,
                    "TREND_UP": 0.1,
                },
            }
        },
    }


def test_extract_live_threshold_surface_live_effective_falls_back_to_global_threshold():
    surface = _extract_live_threshold_surface(
        _aurora_fixture(),
        symbol="BTCUSDT",
        threshold_source_mode=THRESHOLD_SOURCE_MODE_LIVE_EFFECTIVE,
    )

    assert surface.signal_threshold_value == pytest.approx(0.162)
    assert surface.signal_threshold_source == "global_decision"
    assert surface.signal_threshold_path == "decision.signal_threshold"
    assert surface.regime_threshold_source == "asset_override"
    assert surface.regime_threshold_path == "assets.BTCUSDT.regime_thresholds"


def test_extract_live_threshold_surface_asset_override_only_rejects_disabled_override():
    with pytest.raises(
        CalibrationError,
        match=r"requires assets\.BTCUSDT\.signal_threshold\.enabled=true",
    ):
        _extract_live_threshold_surface(
            _aurora_fixture(),
            symbol="BTCUSDT",
            threshold_source_mode=THRESHOLD_SOURCE_MODE_ASSET_OVERRIDE_ONLY,
        )


def test_candidate_blockers_for_surface_reject_global_threshold_baseline():
    blockers = _candidate_blockers_for_surface(
        ThresholdSurface(
            symbol="BTCUSDT",
            signal_threshold_value=0.162,
            regime_thresholds={"DEFAULT": 1.0, "TREND_UP": 0.1},
            signal_threshold_source="global_decision",
            signal_threshold_path="decision.signal_threshold",
            regime_threshold_source="asset_override",
            regime_threshold_path="assets.BTCUSDT.regime_thresholds",
        )
    )

    assert blockers
    assert "decision.signal_threshold" in blockers[0]


def _make_replay_metrics(
    *,
    eligible_bars: int = 40,
    active_bars: int = 12,
    activation_rate: float = 0.30,
    max_daily_activation_rate: float = 0.35,
    mean_forward_bps_3: float | None = 4.0,
    hit_rate_3: float | None = 0.60,
) -> ReplayMetrics:
    return ReplayMetrics(
        eligible_bars=eligible_bars,
        active_bars=active_bars,
        buy_count=max(0, active_bars // 2),
        sell_count=max(0, active_bars - (active_bars // 2)),
        activation_rate=activation_rate,
        max_daily_activation_rate=max_daily_activation_rate,
        mean_forward_bps_1=2.0 if mean_forward_bps_3 is not None else None,
        mean_forward_bps_3=mean_forward_bps_3,
        hit_rate_1=0.55 if hit_rate_3 is not None else None,
        hit_rate_3=hit_rate_3,
        p50_abs_score=0.12,
        p75_abs_score=0.20,
        p80_abs_score=0.24,
        p90_abs_score=0.31,
        regime_counts={"DEFAULT": eligible_bars},
    )


def _make_feature_audit() -> FeatureLogAudit:
    return FeatureLogAudit(
        symbol="BTCUSDT",
        exists=True,
        file_size_mb=1.25,
        sampled_lines=5,
        sampled_keys=["close_boundary_ts_ms", "symbol", "score"],
        has_timestamp_fields=True,
        warnings=[],
    )


def _make_recorder_bar(day_offset: int) -> RecorderBar:
    timestamp = datetime(2026, 3, 1) + timedelta(days=day_offset)
    return RecorderBar(
        timestamp=timestamp,
        timestamp_ms=int(timestamp.timestamp() * 1000),
        symbol="BTCUSDT",
        tf_sec=300,
        ready=True,
        not_ready_reasons="",
        close=100.0 + float(day_offset),
        high=101.0 + float(day_offset),
        low=99.0 + float(day_offset),
        pillar_sum=0.25,
        pillar_operator=0.10,
        pillar_strategist=0.15,
        spread_bps=2.0,
        volatility_state=0.5,
        price_motion_norm=0.1,
    )


def test_parse_args_help_mentions_hardened_artifact_contract(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit):
        _parse_args(["--help"])

    help_text = capsys.readouterr().out
    assert "candidate_aurora_threshold_overlay.yaml" in help_text
    assert "--forward-days" in help_text
    assert "--min-train-days" in help_text


def test_window_spec_for_bars_fails_closed_when_train_validation_forward_windows_do_not_fit():
    bars = [_make_recorder_bar(day_offset) for day_offset in range(6)]

    with pytest.raises(
        CalibrationError,
        match=r"requires at least 9 unique eligible dates",
    ):
        _window_spec_for_bars(
            bars,
            validation_days=3,
            forward_days=3,
            min_train_days=3,
        )


def test_build_v2_metrics_exposes_non_promotable_candidate_state():
    calibration = V2SymbolCalibration(
        symbol="BTCUSDT",
        surface=ThresholdSurface(
            symbol="BTCUSDT",
            signal_threshold_value=0.162,
            regime_thresholds={"DEFAULT": 1.0},
            signal_threshold_source="global_decision",
            signal_threshold_path="decision.signal_threshold",
            regime_threshold_source="asset_override",
            regime_threshold_path="assets.BTCUSDT.regime_thresholds",
        ),
        window_spec=ReplayWindowSpec(
            train_days=["2026-03-01", "2026-03-02"],
            validation_days=["2026-03-03"],
            forward_days=["2026-03-04"],
        ),
        recorder_bar_count=128,
        feature_log_audit=_make_feature_audit(),
        current_train_metrics=_make_replay_metrics(),
        current_validation_metrics=_make_replay_metrics(),
        current_forward_metrics=_make_replay_metrics(),
        candidate=None,
        candidate_blockers=[
            "Current live signal threshold resolves via decision.signal_threshold; candidate emission remains limited to assets.<SYMBOL>.signal_threshold.value and is therefore disabled in this mode."
        ],
        warnings=[],
    )
    args = _parse_args(
        [
            "--symbols",
            "BTCUSDT",
            "--from-date",
            "2026-03-01",
            "--to-date",
            "2026-03-20",
            "--input-source",
            "recorder-features-v2",
        ]
    )

    baseline_metrics = _build_v2_baseline_metrics([calibration])
    validation_metrics = _build_v2_validation_metrics([calibration], args)

    contract = baseline_metrics["symbols"]["BTCUSDT"]["candidate_surface_contract"]
    assert contract["promotable"] is False
    assert "decision.signal_threshold" in contract["promotability_blockers"][0]

    validation_symbol = validation_metrics["symbols"]["BTCUSDT"]
    assert validation_symbol["candidate_present"] is False
    assert validation_symbol["candidate_promotable"] is False
    assert validation_symbol["all_guardrails_pass"] is False


def test_guardrail_failures_reject_validation_underperformance_and_forward_degradation():
    args = _parse_args(
        [
            "--symbols",
            "BTCUSDT",
            "--from-date",
            "2026-03-01",
            "--to-date",
            "2026-03-20",
            "--input-source",
            "recorder-features-v2",
            "--min-validation-improvement-bps",
            "0.5",
            "--max-forward-degradation-bps",
            "0.25",
        ]
    )
    baseline = _make_replay_metrics(
        activation_rate=0.20,
        max_daily_activation_rate=0.25,
        mean_forward_bps_3=5.0,
        hit_rate_3=0.62,
    )
    validation_candidate = _make_replay_metrics(
        activation_rate=0.05,
        max_daily_activation_rate=0.50,
        mean_forward_bps_3=3.5,
        hit_rate_3=0.45,
    )
    forward_candidate = _make_replay_metrics(
        activation_rate=0.80,
        max_daily_activation_rate=0.50,
        mean_forward_bps_3=4.0,
        hit_rate_3=0.45,
    )

    validation_failures = _guardrail_failures(
        validation_candidate,
        args,
        split_name="validation",
        baseline_metrics=baseline,
    )
    forward_failures = _guardrail_failures(
        forward_candidate,
        args,
        split_name="forward",
        baseline_metrics=baseline,
    )

    assert any(
        "validation:delta_mean_forward_bps_3" in failure for failure in validation_failures)
    assert any(
        "validation:activation_ratio_vs_baseline" in failure for failure in validation_failures)
    assert any(
        "forward:delta_mean_forward_bps_3" in failure for failure in forward_failures)
    assert any(
        "forward:activation_ratio_vs_baseline" in failure for failure in forward_failures)


def test_main_writes_hardened_artifacts_without_mutating_aurora_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    aurora_yaml_path = tmp_path / "aurora.yaml"
    aurora_yaml_path.write_text(
        yaml.safe_dump(
            {
                "aurora": {
                    "decision": {
                        "signal_threshold": 0.162,
                        "regime_threshold_multipliers": {"DEFAULT": 1.0},
                    },
                    "assets": {
                        "BTCUSDT": {
                            "signal_threshold": {"enabled": True, "value": 0.111},
                            "regime_thresholds": {"DEFAULT": 1.0},
                        }
                    },
                }
            },
            sort_keys=False,
            allow_unicode=False,
        ),
        encoding="utf-8",
    )
    original_yaml = aurora_yaml_path.read_text(encoding="utf-8")
    out_dir = tmp_path / "out"

    def _fake_run_v1(args, ordered_symbols, threshold_surfaces):
        assert ordered_symbols == ["BTCUSDT"]
        assert threshold_surfaces["BTCUSDT"].signal_threshold_path == "assets.BTCUSDT.signal_threshold.value"
        return CalibrationRunOutputs(
            overlay={
                "assets": {
                    "BTCUSDT": {
                        "signal_threshold": {"value": 0.101},
                        "regime_thresholds": {"DEFAULT": 1.0},
                    }
                }
            },
            report_text="# report\n",
            verdict="NO_GO_RESEARCH_ONLY",
            baseline_metrics={"baseline": True},
            candidate_metrics={"candidate": True},
            validation_metrics={"validation": "unavailable_in_research_mode"},
            forward_metrics={"forward": "unavailable_in_research_mode"},
            run_manifest={
                "artifacts": {},
                "verdict": "NO_GO_RESEARCH_ONLY",
                "promotable": False,
            },
        )

    monkeypatch.setattr(calibrator, "_run_v1", _fake_run_v1)

    exit_code = main(
        [
            "--aurora-yaml",
            str(aurora_yaml_path),
            "--symbols",
            "BTCUSDT",
            "--from-date",
            "2026-03-01",
            "--to-date",
            "2026-03-02",
            "--out-dir",
            str(out_dir),
        ]
    )

    assert exit_code == 0
    assert (out_dir / "candidate_aurora_threshold_overlay.yaml").is_file()
    assert (out_dir / "candidate_threshold_overlay.yaml").is_file()
    assert (out_dir / "baseline_metrics.json").is_file()
    assert (out_dir / "candidate_metrics.json").is_file()
    assert (out_dir / "validation_metrics.json").is_file()
    assert (out_dir / "forward_metrics.json").is_file()
    assert (out_dir / "report.md").is_file()
    assert (out_dir / "run_manifest.json").is_file()

    manifest = json.loads(
        (out_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"]["candidate_aurora_threshold_overlay"].endswith(
        "candidate_aurora_threshold_overlay.yaml")
    assert manifest["artifacts"]["candidate_threshold_overlay_legacy"].endswith(
        "candidate_threshold_overlay.yaml")
    assert aurora_yaml_path.read_text(encoding="utf-8") == original_yaml
