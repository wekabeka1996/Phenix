import pytest


def test_extract_backtest_config_snapshot_includes_repro_anchors():
    from backtest_engine.reporting import _extract_backtest_config_snapshot

    cfg = {
        "trading_mode": "backtest",
        "trading": {"backtest": {"foo": 1}, "execution": {"bar": 2}},
        "strategies": {
            "aurora": {
                "assets": {
                    "BTCUSDT": {
                        "exit": {"sl_pct": 0.02},
                        "take_profit": {"tp_low_ratio": 0.5},
                    }
                }
            }
        },
        "basis_tf_sec": 300,
        "uncertain_cutoff": 0.35,
        "liveness_factor": 3,
        "models": {"volatility_v2": {"window": 20}},
    }

    snap = _extract_backtest_config_snapshot(cfg)

    assert "git_sha" in snap
    assert "config_files" in snap and isinstance(snap["config_files"], list)
    assert "config_hash" in snap and isinstance(snap["config_hash"], str) and len(snap["config_hash"]) == 64
    assert snap.get("config_hash_algo") == "sha256"

    # Determinism (same inputs => same hash)
    snap2 = _extract_backtest_config_snapshot(cfg)
    assert snap2.get("config_hash") == snap.get("config_hash")

    resolved = snap.get("resolved_config")
    assert isinstance(resolved, dict)

    btc = resolved.get("strategies", {}).get("aurora", {}).get("assets", {}).get("BTCUSDT")
    assert btc is not None
    assert btc.get("exit", {}).get("sl_pct") == pytest.approx(0.02)

    regime = resolved.get("regime.yaml")
    assert isinstance(regime, dict)
    assert regime.get("basis_tf_sec") == 300
    assert regime.get("uncertain_cutoff") == pytest.approx(0.35)

    # config_files contains hashes for key SSOT files (best-effort)
    paths = {str(x.get("path")) for x in (snap.get("config_files") or []) if isinstance(x, dict)}
    assert any(p.endswith("config/aurora/regime.yaml") for p in paths)
    assert any(p.endswith("config/aurora/strategies/aurora.yaml") for p in paths)
