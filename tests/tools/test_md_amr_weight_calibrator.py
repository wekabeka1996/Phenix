from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from tools.calibration import calibrate_md_amr_weights as calibrator


def _write_md_amr_recorder(root: Path, *, symbol: str, start_day: date, day_count: int) -> None:
    pattern = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0,
               107.0, 108.0, 109.0, 110.0, 111.0, 112.0, 88.0, 94.0, 100.0]
    for offset in range(day_count):
        day = start_day + timedelta(days=offset)
        day_dir = root / day.isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)
        base_ts = int(pd.Timestamp(
            f"{day.isoformat()}T00:00:00Z").value // 1_000_000)
        rows = []
        previous_close = pattern[0] + (offset * 0.2)
        for bar_idx in range(96):
            close_price = pattern[bar_idx % len(pattern)] + (offset * 0.2)
            open_price = previous_close
            rows.append(
                {
                    "timestamp": base_ts + bar_idx * 900_000,
                    "tf_sec": 900,
                    "symbol": symbol,
                    "open": open_price,
                    "high": max(open_price, close_price) + 1.5,
                    "low": min(open_price, close_price) - 1.5,
                    "close": close_price,
                    "volume": 1000 + bar_idx,
                    "regime": "MEAN_REVERSION",
                    "regime_conf": 0.85,
                }
            )
            previous_close = close_price
        pd.DataFrame(rows).to_csv(day_dir / f"{symbol}_900.csv", index=False)


def test_md_amr_calibrator_help_works(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        calibrator.main(["--help"])

    assert exc.value.code == 0
    stdout = capsys.readouterr().out
    assert "train/validation/forward" in stdout
    assert "--validation-days" in stdout
    assert "--freeze-weights" in stdout
    assert "--mutate-base-params" in stdout


def test_md_amr_calibrator_writes_required_artifacts(tmp_path: Path) -> None:
    recorder_root = tmp_path / "recorder"
    _write_md_amr_recorder(recorder_root, symbol="SOLUSDT",
                           start_day=date(2026, 4, 1), day_count=8)
    out_dir = tmp_path / "artifacts"
    yaml_path = Path("config/aurora/strategies/md_amr.yaml")
    original_yaml = yaml_path.read_text(encoding="utf-8")

    rc = calibrator.main(
        [
            "--recorder-dir",
            str(recorder_root),
            "--symbols",
            "SOLUSDT",
            "--start",
            "2026-04-01",
            "--end",
            "2026-04-09",
            "--validation-days",
            "2",
            "--forward-days",
            "2",
            "--min-train-days",
            "2",
            "--trials",
            "24",
            "--top-k",
            "3",
            "--min-trades",
            "2",
            "--out-dir",
            str(out_dir),
        ]
    )

    assert rc == 0
    required = [
        out_dir / "run_manifest.json",
        out_dir / "baseline_metrics.json",
        out_dir / "candidate_metrics.json",
        out_dir / "validation_metrics.json",
        out_dir / "forward_metrics.json",
        out_dir / "candidate_md_amr_strategy_overlay.yaml",
        out_dir / "report.md",
    ]
    for path in required:
        assert path.exists(), str(path)

    manifest = json.loads(
        (out_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["canonical_yaml_writeback"] is False
    assert manifest["verdict"] in {"GO_CANDIDATE", "NO_GO_CANDIDATE"}

    overlay = yaml.safe_load(
        (out_dir / "candidate_md_amr_strategy_overlay.yaml").read_text(encoding="utf-8"))
    assert list(overlay["md_amr"]["weights"].keys()) == [
        "d1", "h1", "m30", "m15"]

    report = (out_dir / "report.md").read_text(encoding="utf-8")
    for section in [
        "## Scope",
        "## Dataset",
        "## Runtime Surface Under Calibration",
        "## Baseline",
        "## Candidate",
        "## Validation",
        "## Forward Evaluation",
        "## Guardrails",
        "## Risks",
        "## Verdict",
        "## Next Action",
    ]:
        assert section in report

    assert yaml_path.read_text(encoding="utf-8") == original_yaml


def test_md_amr_calibrator_fails_closed_when_data_insufficient(tmp_path: Path) -> None:
    recorder_root = tmp_path / "recorder"
    _write_md_amr_recorder(recorder_root, symbol="SOLUSDT",
                           start_day=date(2026, 4, 1), day_count=3)
    out_dir = tmp_path / "failed_artifacts"

    rc = calibrator.main(
        [
            "--recorder-dir",
            str(recorder_root),
            "--symbols",
            "SOLUSDT",
            "--start",
            "2026-04-01",
            "--end",
            "2026-04-04",
            "--validation-days",
            "2",
            "--forward-days",
            "2",
            "--min-train-days",
            "2",
            "--out-dir",
            str(out_dir),
        ]
    )

    assert rc == 2
    manifest = json.loads(
        (out_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed_closed"
    assert manifest["verdict"] == "NO_GO_CANDIDATE"
    assert (out_dir / "report.md").exists()


def test_md_amr_guardrail_artifact_fails_closed_on_forward_degradation() -> None:
    guardrails = calibrator.GuardrailCfg(
        min_trades=5,
        max_drawdown_ratio=0.35,
        min_train_days=2,
        min_activity_ratio=0.5,
        max_activity_ratio=2.5,
    )
    baseline = {
        "selection_score": 1.2,
        "net_return_ratio": 0.10,
        "max_drawdown_ratio": 0.08,
        "total_trades": 8,
        "entry_count": 8,
        "win_rate": 0.5,
    }
    candidate = {
        "selection_score": 0.7,
        "net_return_ratio": 0.08,
        "max_drawdown_ratio": 0.09,
        "total_trades": 8,
        "entry_count": 8,
        "win_rate": 0.5,
    }

    artifact = calibrator._build_comparison_artifact(
        window_name="forward",
        baseline_metrics=baseline,
        candidate_metrics=candidate,
        guardrails=guardrails,
    )

    assert artifact["all_passed"] is False
    failed_names = {item["name"]
                    for item in artifact["guardrails"] if not item["passed"]}
    assert "forward_no_degradation_vs_baseline" in failed_names


def _write_md_amr_recorder_with_regime(
    root: Path,
    *,
    symbol: str,
    start_day: date,
    day_count: int,
    regime: str,
    regime_conf: float = 0.85,
) -> None:
    """Helper: writes recorder CSVs with a specific regime for every bar."""
    pattern = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0,
               107.0, 108.0, 109.0, 110.0, 111.0, 112.0, 88.0, 94.0, 100.0]
    for offset in range(day_count):
        day = start_day + timedelta(days=offset)
        day_dir = root / day.isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)
        base_ts = int(pd.Timestamp(
            f"{day.isoformat()}T00:00:00Z").value // 1_000_000)
        rows = []
        previous_close = pattern[0] + (offset * 0.2)
        for bar_idx in range(96):
            close_price = pattern[bar_idx % len(pattern)] + (offset * 0.2)
            open_price = previous_close
            rows.append(
                {
                    "timestamp": base_ts + bar_idx * 900_000,
                    "tf_sec": 900,
                    "symbol": symbol,
                    "open": open_price,
                    "high": max(open_price, close_price) + 1.5,
                    "low": min(open_price, close_price) - 1.5,
                    "close": close_price,
                    "volume": 1000 + bar_idx,
                    "regime": regime,
                    "regime_conf": regime_conf,
                }
            )
            previous_close = close_price
        pd.DataFrame(rows).to_csv(day_dir / f"{symbol}_900.csv", index=False)


def test_md_amr_regime_gate_blocks_disallowed_regime(tmp_path: Path) -> None:
    """Entries must be blocked when bar regime is not in asset allowed_regimes."""
    # Write data with CHOPPY regime — not in any md_amr allowed_regimes list
    recorder_root = tmp_path / "recorder"
    _write_md_amr_recorder_with_regime(
        recorder_root,
        symbol="SOLUSDT",
        start_day=date(2026, 4, 1),
        day_count=8,
        regime="CHOPPY",
    )
    out_dir = tmp_path / "regime_blocked"

    rc = calibrator.main(
        [
            "--recorder-dir",
            str(recorder_root),
            "--symbols",
            "SOLUSDT",
            "--start",
            "2026-04-01",
            "--end",
            "2026-04-09",
            "--validation-days",
            "2",
            "--forward-days",
            "2",
            "--min-train-days",
            "2",
            "--trials",
            "4",
            "--top-k",
            "2",
            "--min-trades",
            "0",
            "--out-dir",
            str(out_dir),
        ]
    )

    # Calibrator should complete (rc 0 or 2), but with 0 entries due to regime blocking
    assert rc in (0, 2)
    manifest = json.loads(
        (out_dir / "run_manifest.json").read_text(encoding="utf-8"))
    # Expect NO_GO because no trades were generated
    assert manifest["verdict"] == "NO_GO_CANDIDATE"


def test_compute_regime_labels_returns_valid_labels() -> None:
    """_compute_regime_labels must produce only valid regime strings."""
    valid_regimes = {
        "HIGH_VOLATILITY", "LOW_VOLATILITY", "MEAN_REVERSION",
        "TREND_UP", "TREND_DOWN", "UNCERTAIN",
    }
    # Build 200 bars of synthetic OHLCV data with a clear trend then flat
    n = 200
    close = [100.0 + i * 0.5 for i in range(n)]
    df = pd.DataFrame({
        "open": [close[max(0, i - 1)] for i in range(n)],
        "high": [c + 1.0 for c in close],
        "low": [c - 1.0 for c in close],
        "close": close,
        "volume": [1000] * n,
    })
    result = calibrator._compute_regime_labels(df)

    assert len(result) == n
    unique_labels = set(result.dropna().unique())
    assert unique_labels, "Expected at least one non-NaN regime label"
    assert unique_labels.issubset(
        valid_regimes), f"Invalid labels: {unique_labels - valid_regimes}"


def test_md_amr_overlay_serializes_selected_base_param_mutation() -> None:
    md_amr_cfg = calibrator._load_md_amr_yaml(
        Path("config/aurora/strategies/md_amr.yaml")
    )
    base_params = calibrator._extract_base_params(md_amr_cfg)
    asset_cfgs = calibrator._extract_asset_configs(md_amr_cfg, ["SOLUSDT"])
    mutation_surface = calibrator._build_mutation_surface_cfg(
        base_params=base_params,
        asset_cfgs=asset_cfgs,
        symbols=["SOLUSDT"],
        requested_dimensions=("threshold_z", "allowed_regimes"),
    )

    candidate_base_params = dict(base_params)
    candidate_base_params["threshold_z"] = float(
        base_params["threshold_z"]) + 0.2
    allowed_regime_options = mutation_surface.search_space[
        "allowed_regimes"]["by_symbol"]["SOLUSDT"]["candidate_values"]
    mutated_allowed_regimes = next(
        option for option in allowed_regime_options
        if option != asset_cfgs["SOLUSDT"]["allowed_regimes"]
    )
    candidate_asset_cfgs = {
        "SOLUSDT": {
            **asset_cfgs["SOLUSDT"],
            "allowed_regimes": mutated_allowed_regimes,
        }
    }

    overlay = calibrator._overlay_from_candidate_surface(
        weights={"d1": 0.4, "h1": 0.3, "m30": 0.2, "m15": 0.1},
        baseline_base_params=base_params,
        candidate_base_params=candidate_base_params,
        baseline_asset_cfgs=asset_cfgs,
        candidate_asset_cfgs=candidate_asset_cfgs,
        mutation_surface=mutation_surface,
    )

    assert overlay["md_amr"]["threshold_z"] == candidate_base_params["threshold_z"]
    assert overlay["md_amr"]["assets"]["SOLUSDT"]["allowed_regimes"] == candidate_asset_cfgs["SOLUSDT"]["allowed_regimes"]
    assert list(overlay["md_amr"]["weights"].keys()) == [
        "d1", "h1", "m30", "m15"]


def test_md_amr_mutation_surface_invalid_dimension_fails_closed(tmp_path: Path) -> None:
    recorder_root = tmp_path / "recorder"
    _write_md_amr_recorder(recorder_root, symbol="XRPUSDT",
                           start_day=date(2026, 4, 1), day_count=8)
    out_dir = tmp_path / "invalid_dimension"

    rc = calibrator.main(
        [
            "--recorder-dir",
            str(recorder_root),
            "--symbols",
            "XRPUSDT",
            "--start",
            "2026-04-01",
            "--end",
            "2026-04-09",
            "--validation-days",
            "2",
            "--forward-days",
            "2",
            "--min-train-days",
            "2",
            "--mutate-base-params",
            "not_a_field",
            "--out-dir",
            str(out_dir),
        ]
    )

    assert rc == 2
    manifest = json.loads(
        (out_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["failure"]["code"] == "INPUT_CONTRACT_VIOLATION"
    assert "Unsupported md_amr mutation dimension" in manifest["failure"]["message"]


def test_md_amr_mutation_surface_artifacts_include_overlay_and_live_status(tmp_path: Path) -> None:
    recorder_root = tmp_path / "recorder"
    _write_md_amr_recorder(recorder_root, symbol="XRPUSDT",
                           start_day=date(2026, 4, 1), day_count=8)
    out_dir = tmp_path / "phase2a_artifacts"
    yaml_path = Path("config/aurora/strategies/md_amr.yaml")
    original_yaml = yaml_path.read_text(encoding="utf-8")

    rc = calibrator.main(
        [
            "--recorder-dir",
            str(recorder_root),
            "--symbols",
            "XRPUSDT",
            "--start",
            "2026-04-01",
            "--end",
            "2026-04-09",
            "--validation-days",
            "2",
            "--forward-days",
            "2",
            "--min-train-days",
            "2",
            "--trials",
            "12",
            "--top-k",
            "3",
            "--min-trades",
            "2",
            "--mutate-base-params",
            "threshold_z,allowed_regimes",
            "--per-regime",
            "--out-dir",
            str(out_dir),
        ]
    )

    assert rc == 0
    manifest = json.loads(
        (out_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["mutation_surface"]["requested_base_param_dimensions"] == [
        "threshold_z", "allowed_regimes"]
    assert manifest["mutation_surface"]["symbol_scope"][0]["symbol"] == "XRPUSDT"
    assert manifest["mutation_surface"]["symbol_scope"][0]["live_status"] == calibrator.LIVE_ASSIGNED

    candidate_payload = json.loads(
        (out_dir / "candidate_metrics.json").read_text(encoding="utf-8"))
    mutated_dimensions = candidate_payload["selected_candidate"]["mutation_values"]["mutated_dimensions"]
    assert any(dimension != "weights" for dimension in mutated_dimensions)

    overlay = yaml.safe_load(
        (out_dir / "candidate_md_amr_strategy_overlay.yaml").read_text(encoding="utf-8"))
    assert "weights" in overlay["md_amr"]
    assert "threshold_z" in overlay["md_amr"] or "assets" in overlay["md_amr"]

    per_regime = json.loads(
        (out_dir / "per_regime_analysis.json").read_text(encoding="utf-8"))
    first_regime = next(iter(per_regime["per_regime"].values()))
    assert "baseline" in first_regime
    assert "candidate" in first_regime

    assert yaml_path.read_text(encoding="utf-8") == original_yaml


def test_md_amr_freeze_weights_requires_requested_dimensions(tmp_path: Path) -> None:
    recorder_root = tmp_path / "recorder"
    _write_md_amr_recorder(recorder_root, symbol="XRPUSDT",
                           start_day=date(2026, 4, 1), day_count=8)
    out_dir = tmp_path / "freeze_weights_without_dimensions"

    rc = calibrator.main(
        [
            "--recorder-dir",
            str(recorder_root),
            "--symbols",
            "XRPUSDT",
            "--start",
            "2026-04-01",
            "--end",
            "2026-04-09",
            "--validation-days",
            "2",
            "--forward-days",
            "2",
            "--min-train-days",
            "2",
            "--freeze-weights",
            "--out-dir",
            str(out_dir),
        ]
    )

    assert rc == 2
    manifest = json.loads(
        (out_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["failure"]["code"] == "INPUT_CONTRACT_VIOLATION"
    assert "--freeze-weights requires at least one explicit --mutate-base-params dimension" in manifest[
        "failure"]["message"]


def test_md_amr_mutation_values_payload_omits_weights_when_unchanged() -> None:
    md_amr_cfg = calibrator._load_md_amr_yaml(
        Path("config/aurora/strategies/md_amr.yaml")
    )
    base_params = calibrator._extract_base_params(md_amr_cfg)
    asset_cfgs = calibrator._extract_asset_configs(md_amr_cfg, ["XRPUSDT"])
    baseline_weights = calibrator._normalize_weights(
        calibrator._extract_baseline_weights(md_amr_cfg)
    )
    mutation_surface = calibrator._build_mutation_surface_cfg(
        base_params=base_params,
        asset_cfgs=asset_cfgs,
        symbols=["XRPUSDT"],
        requested_dimensions=("threshold_z",),
    )
    candidate_base_params = dict(base_params)
    candidate_base_params["threshold_z"] = float(
        base_params["threshold_z"]) + 0.2

    payload = calibrator._build_mutation_values_payload(
        baseline_weights=baseline_weights,
        candidate_weights=dict(baseline_weights),
        base_params=base_params,
        candidate_base_params=candidate_base_params,
        asset_cfgs=asset_cfgs,
        candidate_asset_cfgs=asset_cfgs,
        mutation_surface=mutation_surface,
    )

    assert payload["mutated_dimensions"] == ["threshold_z"]
