import json

from apps.reference.domains.alpha_search.runtime.runbook import compare_scenarios
from tools.analysis.audit_alpha_search_scenarios_latest_run import extract_trade_economics


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def test_audit_trade_economics_prefers_recorded_net_cost_fields():
    econ = extract_trade_economics(
        {
            "pnl": 50.0,
            "raw_pnl": 50.0,
            "fee_cost": 12.5,
            "slippage_cost": 5.0,
            "total_cost": 17.5,
            "net_pnl_after_cost": 32.5,
            "cost_model_id": "unit_cost_v1",
            "cost_model_source": "unit",
            "notional_size": 5000.0,
        }
    )

    assert econ["raw_pnl"] == 50.0
    assert econ["total_cost"] == 17.5
    assert econ["net_pnl_after_cost"] == 32.5
    assert econ["cost_status"] == "COST_AWARE"


def test_audit_trade_economics_marks_legacy_raw_only():
    econ = extract_trade_economics({"pnl": 50.0}, fallback_cost_per_trade=17.5)

    assert econ["raw_pnl"] == 50.0
    assert econ["total_cost"] == 17.5
    assert econ["net_pnl_after_cost"] == 32.5
    assert econ["cost_status"] == "LEGACY_RAW_ONLY"


def test_runbook_compare_scenarios_ranks_by_net_pnl_after_cost(tmp_path):
    session_dir = tmp_path / "session"
    raw_winner = session_dir / "S19_ENSEMBLE_MR_BALANCED_VARIANT"
    net_winner = session_dir / "S01_MR_RSI_HEAVY"
    raw_winner.mkdir(parents=True)
    net_winner.mkdir(parents=True)

    _write_jsonl(raw_winner / "scores.jsonl", [{"score": 10.0}])
    _write_jsonl(net_winner / "scores.jsonl", [{"score": 1.0}])
    _write_jsonl(
        raw_winner / "trades.jsonl",
        [{
            "pnl": 100.0,
            "raw_pnl": 100.0,
            "total_cost": 120.0,
            "net_pnl_after_cost": -20.0,
        }],
    )
    _write_jsonl(
        net_winner / "trades.jsonl",
        [{
            "pnl": 40.0,
            "raw_pnl": 40.0,
            "total_cost": 17.5,
            "net_pnl_after_cost": 22.5,
        }],
    )

    result = compare_scenarios(session_dir)

    assert result["ranking_metric"] == "net_pnl_after_cost"
    assert result["best"]["scenario_id"] == "S01_MR_RSI_HEAVY"
    assert result["scenarios"]["S19_ENSEMBLE_MR_BALANCED_VARIANT"]["raw_pnl_diagnostic"] == 100.0
    assert result["scenarios"]["S19_ENSEMBLE_MR_BALANCED_VARIANT"]["net_pnl_after_cost"] == -20.0
