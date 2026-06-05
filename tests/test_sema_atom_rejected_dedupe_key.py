from __future__ import annotations

import json
from pathlib import Path

import SEMA_ATOM_FORWARD_COLLECTOR as fc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rejected_contract(
    *,
    decision_id: str | None = "d-001",
    symbol: str | None = "BTCUSDT",
    side: str | None = "BUY",
    strategy_id: str | None = "aurora",
    event_ts_ms: int | None = 1_778_202_000_000,
    reject_reason: str | None = "LOW_VOL_COST_FLOOR_DENY",
) -> fc.RawContract:
    return fc.RawContract(
        contract_kind="REJECTED",
        contract_id="c-test",
        decision_id=decision_id,
        decision_type="REJECTED",
        symbol=symbol,
        side=side,
        strategy_id=strategy_id,
        regime="LOW_VOLATILITY",
        regime_confidence=0.4,
        direction_confidence=0.2,
        confidence_bucket="0.25..0.50",
        spread_bps=None,
        signal_score=None,
        reference_price=100.0,
        entry_price=100.0,
        close_price=None,
        entry_ts_ms=event_ts_ms,
        event_ts_ms=event_ts_ms,
        close_ts_ms=None,
        realized_pnl_net=None,
        fees=None,
        trade_id=decision_id,
        close_reason=None,
        pnl_status=None,
        reject_reason=reject_reason,
        lifecycle_id=None,
    )


def _make_accepted_contract(
    *,
    lifecycle_id: str | None = "lc-001",
    trade_id: str | None = "t-001",
    close_ts_ms: int | None = 1_778_200_000_000,
) -> fc.RawContract:
    return fc.RawContract(
        contract_kind="ACCEPTED",
        contract_id="c-accepted",
        decision_id="d-accepted",
        decision_type="ACCEPTED",
        symbol="BTCUSDT",
        side="BUY",
        strategy_id="aurora",
        regime="TREND_UP",
        regime_confidence=0.6,
        direction_confidence=0.4,
        confidence_bucket="0.50..0.75",
        spread_bps=None,
        signal_score=None,
        reference_price=100.0,
        entry_price=100.0,
        close_price=102.0,
        entry_ts_ms=1_778_199_000_000,
        event_ts_ms=1_778_199_000_000,
        close_ts_ms=close_ts_ms,
        realized_pnl_net=5.0,
        fees=1.0,
        trade_id=trade_id,
        close_reason="TP",
        pnl_status="resolved",
        reject_reason=None,
        lifecycle_id=lifecycle_id,
    )


# ---------------------------------------------------------------------------
# Test 1: same identity, different reject_reason → duplicate
# ---------------------------------------------------------------------------


def test_same_identity_different_reject_reason_is_duplicate() -> None:
    k1 = fc._rejected_dedupe_key(
        _make_rejected_contract(decision_id="d-001", reject_reason="LOW_VOL_COST_FLOOR_DENY")
    )
    k2 = fc._rejected_dedupe_key(
        _make_rejected_contract(decision_id="d-001", reject_reason="REGIME_BLOCK")
    )
    assert k1 is not None
    assert k2 is not None
    assert k1 == k2, "same decision identity must produce same dedupe key regardless of reject_reason"


# ---------------------------------------------------------------------------
# Test 2: different decision_id, same reject_reason → not duplicate
# ---------------------------------------------------------------------------


def test_different_decision_id_same_reject_reason_not_duplicate() -> None:
    k1 = fc._rejected_dedupe_key(
        _make_rejected_contract(decision_id="d-001", reject_reason="LOW_VOL_COST_FLOOR_DENY")
    )
    k2 = fc._rejected_dedupe_key(
        _make_rejected_contract(decision_id="d-002", reject_reason="LOW_VOL_COST_FLOOR_DENY")
    )
    assert k1 is not None
    assert k2 is not None
    assert k1 != k2


# ---------------------------------------------------------------------------
# Test 3: rid fallback when decision_id absent
# ---------------------------------------------------------------------------


def test_rid_fallback_used_when_decision_id_missing() -> None:
    # decision_id=None means the contract carries rid via trade_id (set in factory)
    contract = _make_rejected_contract(decision_id=None)
    # manually set decision_id to simulate rid fallback having been resolved by collector
    contract = fc.RawContract(
        **{**contract.to_dict(), "decision_id": "rid-fallback-value"}
    )
    k = fc._rejected_dedupe_key(contract)
    assert k is not None
    assert "rid-fallback-value" in k


# ---------------------------------------------------------------------------
# Test 4: missing decision_id AND rid → key is None (incomplete identity)
# ---------------------------------------------------------------------------


def test_missing_decision_id_and_rid_returns_none_key() -> None:
    contract = _make_rejected_contract(decision_id=None)
    # Simulate collector output where both decision_id and rid were absent
    contract_no_id = fc.RawContract(
        **{**contract.to_dict(), "decision_id": None, "trade_id": None}
    )
    assert fc._rejected_dedupe_key(contract_no_id) is None


# ---------------------------------------------------------------------------
# Test 5: missing event_ts_ms → key is None (incomplete dedupe fields)
# ---------------------------------------------------------------------------


def test_missing_event_ts_ms_returns_none_key() -> None:
    contract = _make_rejected_contract(event_ts_ms=None)
    assert fc._rejected_dedupe_key(contract) is None


# ---------------------------------------------------------------------------
# Test 6: different strategy_id → not duplicate
# ---------------------------------------------------------------------------


def test_different_strategy_id_not_duplicate() -> None:
    k1 = fc._rejected_dedupe_key(_make_rejected_contract(strategy_id="aurora"))
    k2 = fc._rejected_dedupe_key(_make_rejected_contract(strategy_id="mean_reversion"))
    assert k1 is not None
    assert k2 is not None
    assert k1 != k2


# ---------------------------------------------------------------------------
# Test 7: dedupe report counts duplicates_detected / duplicates_skipped
# (end-to-end via fc.main with a duplicate rejected row pair)
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _setup_fc_env(tmp_path: Path, rows: list[dict], monkeypatch) -> Path:
    repo = tmp_path
    logs_dir = repo / "logs"
    recorder_day = repo / "data" / "recorder" / "2026-05-08"
    order_log = logs_dir / "order_log_v1.jsonl"
    baseline_saf = repo / "aurora_real_logs_v02.saf.jsonl"
    manifest = repo / "SEMA_ATOM_POC_03B_CANDIDATE_MANIFEST.json"
    trade_lifecycle = logs_dir / "trade_lifecycle.jsonl"
    shadow_dir = logs_dir / "shadow_telemetry"
    shadow_dir.mkdir(parents=True)
    trade_lifecycle.write_text("", encoding="utf-8")
    baseline_saf.write_text("", encoding="utf-8")
    for stub in [
        "SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT.md",
        "SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT.md",
        "SEMA_ATOM_POC_04_COUNTERFACTUAL_POLICY_IMPACT_SIMULATION_REPORT.md",
    ]:
        (repo / stub).write_text("stub", encoding="utf-8")
    manifest.write_text(
        json.dumps({"PROMISING_LOW_SUPPORT": [], "INCONCLUSIVE_LOW_POWER": []}),
        encoding="utf-8",
    )
    recorder_day.mkdir(parents=True, exist_ok=True)
    (recorder_day / "BTCUSDT_300.csv").write_text(
        "timestamp,close,high,low\n1778202000000,100,101,99.5\n1778203000000,101,102,100\n",
        encoding="utf-8",
    )
    _write_jsonl(order_log, rows)

    monkeypatch.setattr(fc, "REPO_ROOT", repo)
    monkeypatch.setattr(fc, "DEFAULT_ORDER_LOG_PATH", order_log)
    monkeypatch.setattr(fc, "DEFAULT_TRADE_LIFECYCLE_PATH", trade_lifecycle)
    monkeypatch.setattr(fc, "DEFAULT_SHADOW_TELEMETRY_DIR", shadow_dir)
    monkeypatch.setattr(fc, "DEFAULT_RECORDER_ROOT", repo / "data" / "recorder")
    monkeypatch.setattr(fc, "DEFAULT_BASELINE_SAF_PATH", baseline_saf)
    monkeypatch.setattr(fc, "DEFAULT_POC02_REPORT_PATH", repo / "SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT.md")
    monkeypatch.setattr(fc, "DEFAULT_POC03_REPORT_PATH", repo / "SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT.md")
    monkeypatch.setattr(fc, "DEFAULT_POC03B_MANIFEST_PATH", manifest)
    monkeypatch.setattr(fc, "DEFAULT_POC04_REPORT_PATH", repo / "SEMA_ATOM_POC_04_COUNTERFACTUAL_POLICY_IMPACT_SIMULATION_REPORT.md")
    monkeypatch.setattr(fc, "DEFAULT_INDEX_PATH", repo / "SEMA_ATOM_FORWARD_COLLECTION_INDEX.json")
    return repo


def _base_rejected_row(
    rid: str = "r-001",
    reject_reason: str = "LOW_VOL_COST_FLOOR_DENY",
) -> dict:
    return {
        "rid": rid,
        "event_type": "DECISION_INTENT_REJECTED",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "strategy_id": "aurora",
        "regime": "LOW_VOLATILITY",
        "regime_confidence": 0.4,
        "metadata": {
            "reject_reason": reject_reason,
            "low_vol_cost_floor": {"entry_price": 100.0, "direction_confidence": 0.2},
        },
        "timestamp": 1_778_202_000_000,
    }


def test_dedupe_report_counts_duplicates_in_report(tmp_path: Path, monkeypatch) -> None:
    # Two rows: same stable identity (rid/symbol/side/ts/strategy_id) but different reject_reason
    row1 = _base_rejected_row(rid="r-001", reject_reason="LOW_VOL_COST_FLOOR_DENY")
    row2 = dict(row1)
    row2["metadata"] = dict(row1["metadata"])
    row2["metadata"]["reject_reason"] = "REGIME_BLOCK"  # different reason, same identity

    repo = _setup_fc_env(tmp_path, [row1, row2], monkeypatch)
    rc = fc.main(["--from", "2026-05-08", "--to", "2026-05-09"])
    assert rc == 0

    report = (repo / "SEMA_ATOM_FORWARD_COLLECTION_2026-05-08_2026-05-09_REPORT.md").read_text(
        encoding="utf-8"
    )
    assert "duplicates_detected: 1" in report
    assert "duplicates_skipped: 1" in report

    atoms_path = repo / "aurora_forward_slice_2026-05-08_2026-05-09.saf.jsonl"
    atoms = [json.loads(l) for l in atoms_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(atoms) == 1, "only one atom — duplicate must have been skipped"


# ---------------------------------------------------------------------------
# Test 8: accepted dedupe key unchanged
# ---------------------------------------------------------------------------


def test_accepted_dedupe_key_unchanged() -> None:
    contract = _make_accepted_contract(
        lifecycle_id="lc-abc", trade_id="t-xyz", close_ts_ms=1_778_200_000_000
    )
    key = fc._accepted_dedupe_key(contract)
    assert key == "accepted:lc-abc:t-xyz:1778200000000"
    assert "reject" not in key
    assert "strategy" not in key
