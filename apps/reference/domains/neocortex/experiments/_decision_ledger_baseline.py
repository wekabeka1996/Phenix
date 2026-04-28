from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_curve, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.reference.domains.shadow_telemetry.schemas.decision_ledger_row import (  # noqa: E402
    DecisionOutcomeLedgerRow,
    ExecutionOutcome,
)


FEATURE_PREFIX = "f_"
DEFAULT_LEDGER_PATH = REPO_ROOT / "logs" / \
    "shadow_telemetry" / "decision_ledger_v1.jsonl"
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / \
    "calibration" / "neocortex_baseline"
DEFAULT_DATASET_PATH = DEFAULT_ARTIFACT_DIR / "decision_ledger_dataset_v1.csv"
DEFAULT_METADATA_PATH = DEFAULT_ARTIFACT_DIR / \
    "decision_ledger_dataset_v1_meta.json"
DEFAULT_REPORT_PATH = DEFAULT_ARTIFACT_DIR / "dumb_baseline_eval_report_v1.json"
DEFAULT_MODEL_PATH = REPO_ROOT / "data" / \
    "checkpoints" / "baseline_logreg_v1.pkl"

RESERVED_COLUMNS = {
    "decision_id",
    "rid",
    "decision_ts_ms",
    "realized_pnl_net",
    "toxic_label",
    "source_kind",
}
SKIP_FEATURE_TOKENS = {"rid", "decision_id"}
SKIP_FEATURE_SUFFIXES = ("ts", "ts_ms", "timestamp")
SYMBOL_BIAS = {
    "BTCUSDT": -0.05,
    "ETHUSDT": 0.05,
    "SOLUSDT": 0.12,
    "BNBUSDT": -0.08,
    "DOGEUSDT": 0.18,
}


@dataclass(slots=True)
class LedgerLoadResult:
    executed_rows: list[DecisionOutcomeLedgerRow]
    total_lines: int
    parsed_rows: int
    malformed_lines: int


@dataclass(slots=True)
class DatasetBuildResult:
    frame: pd.DataFrame
    metadata: dict[str, Any]


@dataclass(slots=True)
class SplitResult:
    train: pd.DataFrame
    test: pd.DataFrame
    feature_columns: list[str]


@dataclass(slots=True)
class SimulationResult:
    threshold: float
    baseline_pnl: float
    counterfactual_pnl: float
    pnl_lift_abs: float
    pnl_lift_pct: float
    blocked_count: int
    intervention_rate: float
    toxic_block_precision: float | None
    prevented_toxic_loss: float
    missed_good_pnl: float


def _safe_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _should_skip_feature(name: str) -> bool:
    tokens = set(name.split("__"))
    if tokens & SKIP_FEATURE_TOKENS:
        return True
    return name.endswith(SKIP_FEATURE_SUFFIXES)


def _add_feature(features: dict[str, Any], name: str, value: Any) -> None:
    if value is None or _should_skip_feature(name):
        return
    feature_name = f"{FEATURE_PREFIX}{name}"
    if isinstance(value, bool):
        features[feature_name] = float(value)
        return
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        if math.isfinite(numeric):
            features[feature_name] = numeric
        return
    numeric = _safe_float(value)
    if numeric is not None and not isinstance(value, str):
        features[feature_name] = numeric
        return
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return
        if _safe_float(stripped) is not None and any(
            token in name for token in ("quantity", "qty", "confidence", "score", "rate", "pct", "price", "vol")
        ):
            features[feature_name] = float(stripped)
            return
        features[feature_name] = stripped.upper() if len(
            stripped) <= 64 else stripped[:64]


def _flatten_scalars(value: Any, prefix: str, features: dict[str, Any]) -> None:
    if value is None:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            child_prefix = f"{prefix}__{key}" if prefix else str(key)
            _flatten_scalars(item, child_prefix, features)
        return
    if isinstance(value, (list, tuple)):
        numeric_values = [float(item) for item in value if isinstance(
            item, (int, float)) and math.isfinite(float(item))]
        if numeric_values:
            _add_feature(features, f"{prefix}__len", len(numeric_values))
            _add_feature(features, f"{prefix}__mean",
                         float(np.mean(numeric_values)))
            _add_feature(features, f"{prefix}__std",
                         float(np.std(numeric_values)))
            _add_feature(features, f"{prefix}__min",
                         float(np.min(numeric_values)))
            _add_feature(features, f"{prefix}__max",
                         float(np.max(numeric_values)))
        return
    _add_feature(features, prefix, value)


def _extract_row_features(row: DecisionOutcomeLedgerRow, source_kind: str, toxic_pnl_threshold: float) -> dict[str, Any]:
    snapshot = dict(row.causal_state_snapshot or {})
    features: dict[str, Any] = {
        "decision_id": row.decision_id,
        "rid": row.rid,
        "decision_ts_ms": int(row.decision_ts_ms),
        "realized_pnl_net": float(row.realized_pnl_net),
        "toxic_label": int(float(row.realized_pnl_net) <= toxic_pnl_threshold),
        "source_kind": source_kind,
    }

    action_value = row.neocortex_action.value if hasattr(
        row.neocortex_action, "value") else str(row.neocortex_action)
    _add_feature(features, "symbol", row.symbol)
    _add_feature(features, "action", action_value)
    _add_feature(features, "fallback_reason", row.fallback_reason or "NONE")

    decision_ts_ms = int(row.decision_ts_ms)
    tick_ts_ms = _safe_float(snapshot.get("tick_ts_ms"))
    feature_event_ts_ms = _safe_float(snapshot.get("feature_event_ts_ms"))
    portfolio_event_ts_ms = _safe_float(snapshot.get("portfolio_event_ts_ms"))
    if tick_ts_ms is not None:
        _add_feature(features, "snapshot_age_ms", decision_ts_ms - tick_ts_ms)
    if feature_event_ts_ms is not None:
        _add_feature(features, "feature_age_ms",
                     decision_ts_ms - feature_event_ts_ms)
    if portfolio_event_ts_ms is not None:
        _add_feature(features, "portfolio_age_ms",
                     decision_ts_ms - portfolio_event_ts_ms)

    _add_feature(features, "snapshot_contract",
                 snapshot.get("snapshot_contract") or "MISSING")
    _add_feature(features, "trigger_event_type",
                 snapshot.get("trigger_event_type") or "MISSING")

    intent = snapshot.get("intent") if isinstance(
        snapshot.get("intent"), dict) else {}
    _add_feature(features, "intent__side", intent.get("side"))
    _add_feature(features, "intent__reduce_only", intent.get("reduce_only"))
    _add_feature(features, "intent__proposed_action",
                 intent.get("proposed_action"))
    _add_feature(features, "intent__strategy_id", intent.get("strategy_id"))
    _add_feature(features, "intent__quantity", intent.get("quantity"))

    observation = snapshot.get("observation") if isinstance(
        snapshot.get("observation"), dict) else {}
    raw_features = observation.get("features") if isinstance(
        observation.get("features"), dict) else {}
    _flatten_scalars(raw_features, "observation__features", features)

    safety_gate = snapshot.get("safety_gate") if isinstance(
        snapshot.get("safety_gate"), dict) else {}
    _flatten_scalars(safety_gate, "safety_gate", features)

    regime_state = snapshot.get("regime_state") if isinstance(
        snapshot.get("regime_state"), dict) else {}
    _flatten_scalars(regime_state, "regime_state", features)

    portfolio_position = snapshot.get("portfolio_position") if isinstance(
        snapshot.get("portfolio_position"), dict) else {}
    _flatten_scalars(portfolio_position, "portfolio_position", features)

    _flatten_scalars(row.data_quality_flags or {}, "dq", features)
    return features


def load_executed_ledger_rows(path: Path) -> LedgerLoadResult:
    if not path.exists():
        return LedgerLoadResult(executed_rows=[], total_lines=0, parsed_rows=0, malformed_lines=0)

    executed_rows: list[DecisionOutcomeLedgerRow] = []
    total_lines = 0
    parsed_rows = 0
    malformed_lines = 0
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            total_lines += 1
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                row = DecisionOutcomeLedgerRow.model_validate(payload)
            except Exception:
                malformed_lines += 1
                continue
            parsed_rows += 1
            if row.execution_outcome == ExecutionOutcome.EXECUTED and row.realized_pnl_net is not None:
                executed_rows.append(row)

    executed_rows.sort(key=lambda item: int(item.decision_ts_ms))
    return LedgerLoadResult(
        executed_rows=executed_rows,
        total_lines=total_lines,
        parsed_rows=parsed_rows,
        malformed_lines=malformed_lines,
    )


def generate_synthetic_ledger_rows(count: int, start_ts_ms: int, seed: int) -> list[DecisionOutcomeLedgerRow]:
    if count <= 0:
        return []

    rng = np.random.default_rng(seed)
    symbols = np.array(sorted(SYMBOL_BIAS))
    regimes = np.array(["TREND_UP", "TREND_DOWN", "MEAN_REVERT", "BREAKOUT"])
    rows: list[DecisionOutcomeLedgerRow] = []
    for index in range(count):
        phase = index / max(count - 1, 1)
        symbol = str(rng.choice(symbols))
        regime = str(rng.choice(regimes, p=[0.32, 0.22, 0.28, 0.18]))
        side = "LONG" if rng.random() < 0.54 else "SHORT"
        trend_dir = 1 if regime == "TREND_UP" else -1 if regime == "TREND_DOWN" else 0
        side_dir = 1 if side == "LONG" else -1
        trend_alignment = float(side_dir * trend_dir)

        regime_confidence = float(
            np.clip(rng.normal(0.64 + 0.08 * math.sin(phase * 6.0), 0.12), 0.05, 0.99))
        signal_score = float(
            np.clip(rng.normal(0.56 + 0.07 * math.cos(phase * 7.0), 0.15), 0.01, 0.99))
        price_momentum_5m = float(rng.normal(0.85 * trend_alignment, 0.95))
        volatility_20 = float(np.clip(rng.lognormal(
            mean=-0.25 + 0.35 * phase, sigma=0.25), 0.15, 2.6))
        realized_vol_5m = float(
            np.clip(volatility_20 + rng.normal(0.0, 0.15), 0.05, 3.2))
        spread_bps = float(
            np.clip(rng.normal(1.1 + 1.5 * volatility_20, 0.7), 0.2, 8.5))
        volume_sma_ratio = float(
            np.clip(rng.normal(1.08 - 0.12 * phase, 0.24), 0.25, 2.5))
        orderbook_imbalance = float(
            np.clip(rng.normal(0.45 * trend_alignment, 0.32), -1.0, 1.0))
        liquidity_score = float(
            np.clip(rng.normal(0.72 - 0.08 * volatility_20, 0.12), 0.05, 0.99))
        rsi_14 = float(
            np.clip(rng.normal(50.0 + 17.0 * trend_alignment, 10.0), 1.0, 99.0))
        bb_position = float(
            np.clip(rng.normal(0.50 + 0.20 * trend_alignment, 0.18), 0.0, 1.0))
        bb_width = float(
            np.clip(rng.normal(0.030 + 0.012 * volatility_20, 0.010), 0.005, 0.16))
        price_sma_20_deviation = float(
            rng.normal(0.30 * trend_alignment, 0.48))
        stoch_k = float(
            np.clip(rng.normal(50.0 + 18.0 * trend_alignment, 14.0), 0.0, 100.0))
        stoch_d = float(np.clip(stoch_k + rng.normal(0.0, 7.0), 0.0, 100.0))
        funding_rate = float(
            np.clip(rng.normal(0.0004 * trend_alignment, 0.0010), -0.005, 0.005))
        oi_delta_5m = float(rng.normal(0.12 * trend_alignment, 0.35))
        atr_pct = float(
            np.clip(rng.normal(0.42 + 0.16 * volatility_20, 0.11), 0.04, 2.40))

        toxic_logit = (
            1.05 * (volatility_20 - 1.0)
            + 0.17 * spread_bps
            - 1.30 * (signal_score - 0.50)
            - 1.05 * (regime_confidence - 0.50)
            - 0.75 * trend_alignment
            - 0.55 * (volume_sma_ratio - 1.0)
            - 0.45 * orderbook_imbalance * side_dir
            - 0.60 * (liquidity_score - 0.50)
            + SYMBOL_BIAS[symbol]
            + rng.normal(0.0, 0.58)
        )
        toxic_probability = _sigmoid(toxic_logit)
        is_toxic = bool(rng.random() < toxic_probability)
        if is_toxic:
            realized_pnl_net = - \
                float(
                    abs(rng.normal(9.0 + 14.0 * toxic_probability + 3.0 * volatility_20, 4.2)))
        else:
            realized_pnl_net = float(abs(rng.normal(
                8.0 + 9.5 * signal_score + 6.5 * regime_confidence + 2.0 * max(trend_alignment, 0.0), 4.8)))

        decision_ts_ms = int(start_ts_ms + index * 300_000)
        rid = f"SYN-RID-{decision_ts_ms}-{index:04d}"
        payload = {
            "decision_id": f"syn-decision-{index:05d}",
            "rid": rid,
            "symbol": symbol,
            "decision_ts_ms": decision_ts_ms,
            "causal_state_snapshot": {
                "snapshot_contract": "decision_making_projection_v1",
                "symbol": symbol,
                "tick_ts_ms": decision_ts_ms - int(rng.integers(50, 800)),
                "feature_event_ts_ms": decision_ts_ms - int(rng.integers(20, 400)),
                "portfolio_event_ts_ms": decision_ts_ms - int(rng.integers(40, 1200)),
                "trigger_event_type": "EVT:AUTHORITY_DECISION",
                "observation": {
                    "features": {
                        "bb_position": bb_position,
                        "bb_width": bb_width,
                        "rsi_14": rsi_14,
                        "price_sma_20_deviation": price_sma_20_deviation,
                        "volume_sma_ratio": volume_sma_ratio,
                        "stoch_k": stoch_k,
                        "stoch_d": stoch_d,
                        "price_momentum_5m": price_momentum_5m,
                        "volatility_20": volatility_20,
                        "realized_vol_5m": realized_vol_5m,
                        "spread_bps": spread_bps,
                        "orderbook_imbalance": orderbook_imbalance,
                        "funding_rate": funding_rate,
                        "oi_delta_5m": oi_delta_5m,
                        "liquidity_score": liquidity_score,
                        "atr_pct": atr_pct,
                    },
                    "feature_state": {
                        "ts_ms": decision_ts_ms,
                        "symbol": symbol,
                        "tf_sec": 300,
                    },
                },
                "intent": {
                    "rid": rid,
                    "strategy_id": f"baseline_{symbol.lower()}",
                    "side": side,
                    "quantity": str(round(float(rng.uniform(0.15, 2.25)), 4)),
                    "reduce_only": False,
                    "proposed_action": "ALLOW",
                },
                "regime_state": {
                    "regime": regime,
                    "confidence": regime_confidence,
                    "trend_dir": trend_dir,
                },
                "portfolio_position": {
                    "symbol": symbol,
                    "qty": 0.0,
                    "leverage": float(np.clip(rng.normal(2.8, 0.8), 1.0, 5.0)),
                },
                "safety_gate": {
                    "regime": regime,
                    "regime_confidence": regime_confidence,
                    "signal_score": signal_score,
                    "intent_side": side,
                },
            },
            "neocortex_action": "ALLOW",
            "fallback_reason": None,
            "execution_outcome": "EXECUTED",
            "realized_pnl_net": realized_pnl_net,
            "data_quality_flags": {
                "snapshot_missing": False,
                "supports_counterfactual_join": False,
                "snapshot_provider_configured": True,
                "has_nan": False,
                "is_stale": False,
                "is_projection": True,
            },
        }
        rows.append(DecisionOutcomeLedgerRow.model_validate(payload))

    return rows


def prepare_dataset(
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    *,
    min_real_rows: int = 240,
    synthetic_rows: int = 420,
    seed: int = 7,
    toxic_pnl_threshold: float = 0.0,
) -> DatasetBuildResult:
    ledger_load = load_executed_ledger_rows(ledger_path)
    real_rows = ledger_load.executed_rows
    real_count = len(real_rows)
    toxic_real_count = sum(float(row.realized_pnl_net) <=
                           toxic_pnl_threshold for row in real_rows)
    non_toxic_real_count = real_count - toxic_real_count

    synthetic_reasons: list[str] = []
    if not ledger_path.exists():
        synthetic_reasons.append("ledger_missing")
    if real_count < min_real_rows:
        synthetic_reasons.append("insufficient_executed_rows")
    if toxic_real_count == 0 or non_toxic_real_count == 0:
        synthetic_reasons.append("single_class_real_data")
    elif min(toxic_real_count, non_toxic_real_count) < 25:
        synthetic_reasons.append("minority_class_too_small")

    synthetic_needed = 0
    if synthetic_reasons:
        synthetic_needed = max(min_real_rows - real_count, 0)
        if real_count == 0 or "single_class_real_data" in synthetic_reasons:
            synthetic_needed = max(synthetic_needed, synthetic_rows)
        elif "minority_class_too_small" in synthetic_reasons:
            synthetic_needed = max(synthetic_needed, 120)

    start_ts_ms = int(real_rows[-1].decision_ts_ms +
                      300_000) if real_rows else 1_710_000_000_000
    synthetic_ledger_rows = generate_synthetic_ledger_rows(
        synthetic_needed, start_ts_ms=start_ts_ms, seed=seed)

    record_frames: list[pd.DataFrame] = []
    if real_rows:
        record_frames.append(pd.DataFrame(_extract_row_features(
            row, "real", toxic_pnl_threshold) for row in real_rows))
    if synthetic_ledger_rows:
        record_frames.append(pd.DataFrame(_extract_row_features(
            row, "synthetic", toxic_pnl_threshold) for row in synthetic_ledger_rows))
    frame = pd.concat(record_frames, ignore_index=True,
                      sort=False) if record_frames else pd.DataFrame()
    if frame.empty:
        raise RuntimeError(
            "Decision ledger dataset prep produced an empty dataset.")

    frame = frame.sort_values(
        "decision_ts_ms", kind="stable").reset_index(drop=True)
    metadata = {
        "ledger_path": str(ledger_path),
        "ledger_exists": ledger_path.exists(),
        "ledger_total_lines": ledger_load.total_lines,
        "ledger_parsed_rows": ledger_load.parsed_rows,
        "ledger_malformed_lines": ledger_load.malformed_lines,
        "real_executed_rows": real_count,
        "real_toxic_rows": toxic_real_count,
        "real_non_toxic_rows": non_toxic_real_count,
        "synthetic_rows": len(synthetic_ledger_rows),
        "total_rows": int(len(frame)),
        "feature_columns": [column for column in frame.columns if column.startswith(FEATURE_PREFIX)],
        "used_synthetic_fallback": bool(synthetic_ledger_rows),
        "synthetic_reasons": synthetic_reasons,
        "toxic_pnl_threshold": toxic_pnl_threshold,
        "seed": seed,
    }
    return DatasetBuildResult(frame=frame, metadata=metadata)


def save_dataset_artifacts(frame: pd.DataFrame, metadata: dict[str, Any], dataset_path: Path, metadata_path: Path) -> None:
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(dataset_path, index=False)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with metadata_path.open("w", encoding="utf-8") as handle:
        json.dump(_json_ready(metadata), handle, indent=2, sort_keys=True)


def load_dataset_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if frame.empty:
        raise RuntimeError(f"Prepared dataset is empty: {path}")
    return frame


def split_dataset_chronologically(dataset: pd.DataFrame, train_ratio: float = 0.70) -> SplitResult:
    if dataset.empty:
        raise RuntimeError("Cannot split an empty dataset.")
    ordered = dataset.sort_values(
        "decision_ts_ms", kind="stable").reset_index(drop=True)
    split_index = int(math.floor(len(ordered) * train_ratio))
    split_index = max(1, min(split_index, len(ordered) - 1))
    feature_columns = [
        column for column in ordered.columns if column.startswith(FEATURE_PREFIX)]
    if not feature_columns:
        raise RuntimeError("Prepared dataset has no feature columns.")
    return SplitResult(
        train=ordered.iloc[:split_index].reset_index(drop=True),
        test=ordered.iloc[split_index:].reset_index(drop=True),
        feature_columns=feature_columns,
    )


def build_model_pipeline(feature_frame: pd.DataFrame) -> Pipeline:
    numeric_columns = [column for column in feature_frame.columns if pd.api.types.is_numeric_dtype(
        feature_frame[column])]
    categorical_columns = [
        column for column in feature_frame.columns if column not in numeric_columns]

    transformers: list[tuple[str, Pipeline, list[str]]] = []
    if numeric_columns:
        transformers.append(
            (
                "num",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", StandardScaler()),
                    ]
                ),
                numeric_columns,
            )
        )
    if categorical_columns:
        transformers.append(
            (
                "cat",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categorical_columns,
            )
        )
    if not transformers:
        raise RuntimeError(
            "No usable feature columns were found for model training.")

    return Pipeline(
        steps=[
            ("preprocess", ColumnTransformer(transformers=transformers)),
            (
                "model",
                LogisticRegression(
                    max_iter=2_000,
                    class_weight="balanced",
                    solver="lbfgs",
                ),
            ),
        ]
    )


def score_toxic_probability(model: Pipeline, feature_frame: pd.DataFrame) -> np.ndarray:
    probabilities = model.predict_proba(feature_frame)
    classes = list(model.named_steps["model"].classes_)
    if 1 not in classes:
        return np.zeros(len(feature_frame), dtype=float)
    toxic_class_index = classes.index(1)
    return probabilities[:, toxic_class_index]


def precision_at_recall(y_true: np.ndarray, y_score: np.ndarray, recall_target: float) -> tuple[float, float | None]:
    if len(np.unique(y_true)) < 2:
        return float("nan"), None
    precision, recall, thresholds = precision_recall_curve(y_true, y_score)
    candidate_indices = np.where(recall >= recall_target)[0]
    if len(candidate_indices) == 0:
        return float("nan"), None
    best_index = max(candidate_indices, key=lambda index: precision[index])
    threshold = None
    if len(thresholds) > 0:
        threshold_index = min(max(best_index - 1, 0), len(thresholds) - 1)
        threshold = float(thresholds[threshold_index])
    return float(precision[best_index]), threshold


def simulate_blocking(
    pnl: np.ndarray,
    toxic_label: np.ndarray,
    toxic_probability: np.ndarray,
    threshold: float,
) -> SimulationResult:
    blocked_mask = toxic_probability >= threshold
    baseline_pnl = float(np.sum(pnl))
    counterfactual_pnl = float(np.sum(pnl[~blocked_mask]))
    pnl_lift_abs = counterfactual_pnl - baseline_pnl
    pnl_lift_pct = 0.0 if baseline_pnl == 0.0 else (
        pnl_lift_abs / abs(baseline_pnl)) * 100.0
    blocked_count = int(np.sum(blocked_mask))
    intervention_rate = float(blocked_count / len(pnl)) if len(pnl) else 0.0
    toxic_block_precision = None
    if blocked_count > 0:
        toxic_block_precision = float(np.mean(toxic_label[blocked_mask]))
    prevented_toxic_loss = float(
        -np.sum(pnl[blocked_mask & (toxic_label == 1)]))
    missed_good_pnl = float(np.sum(pnl[blocked_mask & (toxic_label == 0)]))
    return SimulationResult(
        threshold=float(threshold),
        baseline_pnl=baseline_pnl,
        counterfactual_pnl=counterfactual_pnl,
        pnl_lift_abs=pnl_lift_abs,
        pnl_lift_pct=pnl_lift_pct,
        blocked_count=blocked_count,
        intervention_rate=intervention_rate,
        toxic_block_precision=toxic_block_precision,
        prevented_toxic_loss=prevented_toxic_loss,
        missed_good_pnl=missed_good_pnl,
    )


def tune_threshold(
    pnl: np.ndarray,
    toxic_label: np.ndarray,
    toxic_probability: np.ndarray,
    *,
    max_intervention_rate: float,
    default_threshold: float = 0.70,
) -> SimulationResult:
    quantile_thresholds = np.quantile(
        toxic_probability, np.linspace(0.55, 0.95, 12))
    fixed_thresholds = np.linspace(0.50, 0.95, 19)
    candidate_thresholds = sorted({round(float(item), 4) for item in np.concatenate(
        [quantile_thresholds, fixed_thresholds, np.array([default_threshold])])})

    candidates: list[SimulationResult] = []
    for threshold in candidate_thresholds:
        result = simulate_blocking(
            pnl, toxic_label, toxic_probability, threshold)
        if result.blocked_count == 0:
            continue
        if result.intervention_rate <= max_intervention_rate + 1e-12:
            candidates.append(result)

    if not candidates:
        return simulate_blocking(pnl, toxic_label, toxic_probability, default_threshold)

    return max(
        candidates,
        key=lambda result: (result.counterfactual_pnl, -
                            result.intervention_rate, result.threshold),
    )


def render_table(title: str, frame: pd.DataFrame) -> str:
    return f"{title}\n{frame.to_string(index=False)}"


def write_report_json(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(_json_ready(report), handle, indent=2, sort_keys=True)


def compute_roc_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    if len(np.unique(y_true)) < 2:
        return float("nan")
    return float(roc_auc_score(y_true, y_score))
