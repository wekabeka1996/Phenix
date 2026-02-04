import shutil
from pathlib import Path

import pytest


class _Runtime:
    def __init__(self, config_dir: str):
        self.config_dir = config_dir


class _SystemMeta:
    def __init__(self, config_dir: str):
        self.runtime = _Runtime(config_dir)


class _Cfg:
    def __init__(self, *, config_dir: Path, resolved: dict):
        self.system_meta = _SystemMeta(str(config_dir))
        self._resolved = resolved

    def model_dump(self):
        return self._resolved


def _write(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def test_run_bundle_saves_correct_files(tmp_path: Path):
    from backtest_engine.reporting import save_backtest_run_bundle

    # Build synthetic config tree
    cfg_dir = tmp_path / "config" / "aurora"
    _write(cfg_dir / "system.yaml", "system: 1\n")
    _write(cfg_dir / "trading.yaml", "trading: 1\n")
    _write(cfg_dir / "regime.yaml", "basis_tf_sec: 300\nuncertain_cutoff: 0.35\n")
    _write(cfg_dir / "instruments.yaml", "instruments: {}\n")
    _write(cfg_dir / "strategies.yaml", "version: '1'\nassignments: {}\n")
    _write(cfg_dir / "strategies" / "aurora.yaml", "strategies:\n  aurora: {}\n")
    _write(cfg_dir / "strategies" / "mean_reversion.yaml", "strategies:\n  mean_reversion: {}\n")

    resolved = {
        "system_meta": {"runtime": {"config_dir": str(cfg_dir)}},
        "strategies_registry": {
            "assignments": {
                "BTCUSDT": ["aurora"],
                "ETHUSDT": ["mean_reversion"],
            }
        },
    }
    cfg = _Cfg(config_dir=cfg_dir, resolved=resolved)

    reports_root = tmp_path / "reports" / "backtests"
    report = {"run_id": "R", "config_snapshot": {"x": 1}}

    bundle = save_backtest_run_bundle(run_id="R", report=report, config=cfg, reports_root=reports_root)

    assert (bundle / "result.json").exists()
    assert (bundle / "resolved_config.json").exists()
    assert (bundle / "manifest.json").exists()

    assert (bundle / "config" / "aurora.yaml").exists()
    assert (bundle / "config" / "mean_reversion.yaml").exists()

    ssot = bundle / "config" / "ssot"
    for name in ("system.yaml", "trading.yaml", "regime.yaml", "instruments.yaml", "strategies.yaml"):
        assert (ssot / name).exists()

    manifest = (bundle / "manifest.json").read_text(encoding="utf-8")
    assert "\"config_hash\"" in manifest
    assert "\"active_strategies\"" in manifest
    assert "aurora" in manifest and "mean_reversion" in manifest


def test_run_bundle_fail_closed_on_missing_yaml(tmp_path: Path):
    from backtest_engine.reporting import save_backtest_run_bundle

    cfg_dir = tmp_path / "config" / "aurora"
    _write(cfg_dir / "system.yaml", "system: 1\n")
    _write(cfg_dir / "trading.yaml", "trading: 1\n")
    _write(cfg_dir / "regime.yaml", "basis_tf_sec: 300\nuncertain_cutoff: 0.35\n")
    _write(cfg_dir / "instruments.yaml", "instruments: {}\n")
    _write(cfg_dir / "strategies.yaml", "version: '1'\nassignments: {}\n")
    # Intentionally omit strategies/aurora.yaml

    resolved = {
        "system_meta": {"runtime": {"config_dir": str(cfg_dir)}},
        "strategies_registry": {"assignments": {"BTCUSDT": ["aurora"]}},
    }
    cfg = _Cfg(config_dir=cfg_dir, resolved=resolved)

    with pytest.raises(RuntimeError, match=r"missing required strategy config strategies/aurora.yaml"):
        save_backtest_run_bundle(run_id="R", report={"ok": True}, config=cfg, reports_root=tmp_path / "reports" / "backtests")


def test_manifest_is_deterministic(tmp_path: Path):
    from backtest_engine.reporting import save_backtest_run_bundle

    cfg_dir = tmp_path / "config" / "aurora"
    _write(cfg_dir / "system.yaml", "system: 1\n")
    _write(cfg_dir / "trading.yaml", "trading: 1\n")
    _write(cfg_dir / "regime.yaml", "basis_tf_sec: 300\nuncertain_cutoff: 0.35\n")
    _write(cfg_dir / "instruments.yaml", "instruments: {}\n")
    _write(cfg_dir / "strategies.yaml", "version: '1'\nassignments: {}\n")
    _write(cfg_dir / "strategies" / "aurora.yaml", "strategies:\n  aurora: {}\n")

    resolved = {
        "system_meta": {"runtime": {"config_dir": str(cfg_dir)}},
        "strategies_registry": {"assignments": {"BTCUSDT": ["aurora"]}},
    }
    cfg = _Cfg(config_dir=cfg_dir, resolved=resolved)

    reports_root = tmp_path / "reports" / "backtests"

    bundle1 = save_backtest_run_bundle(run_id="R", report={"x": 1}, config=cfg, reports_root=reports_root)
    m1 = (bundle1 / "manifest.json").read_bytes()

    shutil.rmtree(bundle1)

    bundle2 = save_backtest_run_bundle(run_id="R", report={"x": 1}, config=cfg, reports_root=reports_root)
    m2 = (bundle2 / "manifest.json").read_bytes()

    assert m1 == m2
