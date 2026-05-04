from __future__ import annotations

import pandas as pd


OBJECTIVE_COMPONENTS = ("cost", "risk", "edge", "execution", "information", "behavior")


def _merge_nearest_recorder(attempts: pd.DataFrame, recorder: pd.DataFrame) -> pd.DataFrame:
    if attempts.empty or recorder.empty:
        return attempts
    out_frames: list[pd.DataFrame] = []
    for symbol, attempts_sym in attempts.groupby("symbol", sort=False):
        recorder_sym = recorder[recorder["symbol"] == symbol].copy()
        if recorder_sym.empty:
            out_frames.append(attempts_sym)
            continue
        left = attempts_sym.sort_values("ts_ms", kind="mergesort").copy()
        right = recorder_sym.sort_values("timestamp", kind="mergesort").copy()
        tolerance_ms = int(left["tf_sec"].fillna(300).astype("int64").max()) * 2000 if "tf_sec" in left.columns else 600_000
        merged = pd.merge_asof(
            left,
            right,
            left_on="ts_ms",
            right_on="timestamp",
            direction="nearest",
            tolerance=tolerance_ms,
            suffixes=("", "_rec"),
        )
        out_frames.append(merged)
    return pd.concat(out_frames, ignore_index=True) if out_frames else attempts


def build_attempted_entry_frame(
    *,
    recorder_df: pd.DataFrame,
    wal_df: pd.DataFrame,
    default_tf_sec: int,
) -> pd.DataFrame:
    if wal_df.empty:
        return pd.DataFrame()

    attempts = wal_df[
        ((wal_df["verb"] == "TRADE_INTENT_PROPOSED") & (~wal_df["reduce_only"].fillna(False)))
        | (wal_df["verb"].astype(str).str.startswith("TRADE_INTENT_REJECTED"))
    ].copy()
    if attempts.empty:
        return attempts

    attempts["attempt_kind"] = attempts["verb"].map(
        lambda verb: "proposed" if verb == "TRADE_INTENT_PROPOSED" else "rejected"
    )
    attempts["tf_sec"] = int(default_tf_sec)
    attempts["ts_ms"] = pd.to_numeric(attempts["ts_ms"], errors="coerce")
    attempts = attempts.dropna(subset=["ts_ms", "symbol", "strategy_id"]).copy()
    attempts["symbol"] = attempts["symbol"].astype(str).str.upper()
    attempts["strategy_id"] = attempts["strategy_id"].astype(str)
    attempts["ts_ms"] = attempts["ts_ms"].astype("int64")

    if "objective_multiplier" in attempts.columns and "objective_objective_score" in attempts.columns:
        attempts["objective_multiplier"] = pd.to_numeric(attempts["objective_multiplier"], errors="coerce")
        attempts["objective_objective_score"] = pd.to_numeric(attempts["objective_objective_score"], errors="coerce")
        attempts["pretrade_original_score"] = attempts["objective_objective_score"] / attempts["objective_multiplier"].replace(0, pd.NA)
    return _merge_nearest_recorder(attempts, recorder_df).sort_values(["symbol", "ts_ms"], kind="mergesort").reset_index(drop=True)


def build_realized_objective_frame(
    *,
    wal_df: pd.DataFrame,
    ledger_df: pd.DataFrame,
) -> pd.DataFrame:
    realized = wal_df[wal_df["verb"] == "OBJECTIVE_REALIZED_V1"].copy()
    if realized.empty:
        return realized

    realized["ts_ms"] = pd.to_numeric(realized["ts_ms"], errors="coerce")
    for column in (
        "realized_quality_score",
        "realized_pnl",
        "fees",
        "duration_sec",
        "mae",
        "mfe",
        "pretrade_multiplier",
        "pretrade_objective_score",
    ):
        if column in realized.columns:
            realized[column] = pd.to_numeric(realized[column], errors="coerce")

    if "pretrade_multiplier" in realized.columns and "pretrade_objective_score" in realized.columns:
        realized["pretrade_original_score"] = realized["pretrade_objective_score"] / realized["pretrade_multiplier"].replace(0, pd.NA)

    if not ledger_df.empty:
        ledger = ledger_df.copy()
        ledger["symbol"] = ledger["symbol"].astype(str).str.upper()
        if "entry_client_id" in ledger.columns:
            entry_match = ledger.groupby("entry_client_id").size().rename("ledger_entry_matches")
            realized = realized.merge(entry_match, how="left", left_on="entry_rid", right_index=True)
        if "client_order_id" in ledger.columns:
            close_match = ledger.groupby("client_order_id").size().rename("ledger_close_matches")
            realized = realized.merge(close_match, how="left", left_on="close_rid", right_index=True)
    return realized.sort_values(["symbol", "ts_ms"], kind="mergesort").reset_index(drop=True)


def extract_component_frame(df: pd.DataFrame, *, prefix: str) -> pd.DataFrame:
    out = df.copy()
    for component in OBJECTIVE_COMPONENTS:
        column = f"{prefix}_component_{component}"
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    return out
