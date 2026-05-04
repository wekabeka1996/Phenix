from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterator, Literal, Mapping, Sequence

import numpy as np
import pandas as pd

from apps.reference.config_loader import get_config
from apps.reference.domains.system_stress.system_stress_overlay import (
    SystemStressOverlay,
    _StressActuator,
    _SymbolStressState,
)


ORACLE_MODES = ("future_vol", "future_range", "future_abs_return")
STRESS_LABEL_POLICIES = (
    "primary_quantile",
    "primary_or_secondary",
    "primary_and_secondary",
)
SUMMARY_HIGHER_IS_BETTER = {"f1", "precision",
                            "recall", "balanced_accuracy", "coverage"}
SUMMARY_LOWER_IS_BETTER = {
    "alert_rate",
    "state_switches_per_1000",
    "overblocking_proxy",
    "alert_gap",
}


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


@dataclass(frozen=True)
class Split:
    train: pd.DataFrame
    test: pd.DataFrame
    train_days: list[str]
    test_days: list[str]


@dataclass(frozen=True)
class CandidateSpec:
    aggregation_method: Literal["weighted_vote", "k_of_n", "max"]
    weights: Dict[str, float] | None = None
    k: int | None = None

    def candidate_id(self) -> str:
        if self.aggregation_method == "weighted_vote":
            weights = self.weights or {}
            parts = [f"{key}={weights[key]:.4f}" for key in sorted(weights)]
            return f"weighted_vote__{'__'.join(parts)}"
        if self.aggregation_method == "k_of_n":
            return f"k_of_n__k={int(self.k or 0)}"
        return "max"

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "aggregation_method": self.aggregation_method,
            "candidate_id": self.candidate_id(),
        }
        if self.weights is not None:
            payload["weights"] = dict(self.weights)
        if self.k is not None:
            payload["k"] = int(self.k)
        return payload

    def to_yaml_fragment(self) -> dict[str, Any]:
        aggregation: dict[str, Any] = {"method": self.aggregation_method}
        if self.aggregation_method == "weighted_vote":
            aggregation["weights"] = dict(self.weights or {})
        elif self.aggregation_method == "k_of_n":
            aggregation["k"] = int(self.k or 0)
        return {"system_stress": {"aggregation": aggregation}}


@dataclass(frozen=True)
class CandidateResult:
    candidate: CandidateSpec
    metrics: Dict[str, float]

    @property
    def aggregation_method(self) -> str:
        return self.candidate.aggregation_method

    @property
    def weights(self) -> Dict[str, float] | None:
        return self.candidate.weights

    @property
    def k(self) -> int | None:
        return self.candidate.k

    @property
    def candidate_id(self) -> str:
        return self.candidate.candidate_id()


@dataclass(frozen=True)
class WalkForwardWindow:
    window_id: int
    train_days: list[str]
    validate_days: list[str]
    test_days: list[str]

    def all_days(self) -> list[str]:
        return [*self.train_days, *self.validate_days, *self.test_days]


@dataclass(frozen=True)
class OracleSpec:
    primary: Literal["future_vol", "future_range", "future_abs_return"]
    forecast_horizon_bars: int
    stress_label_policy: Literal[
        "primary_quantile",
        "primary_or_secondary",
        "primary_and_secondary",
    ]
    primary_quantile: float
    secondary: Literal["future_vol", "future_range",
                       "future_abs_return"] | None = None
    secondary_quantile: float | None = None

    def __post_init__(self) -> None:
        if self.primary not in ORACLE_MODES:
            raise ValueError(f"Unsupported primary oracle: {self.primary}")
        if self.secondary is not None and self.secondary not in ORACLE_MODES:
            raise ValueError(f"Unsupported secondary oracle: {self.secondary}")
        if self.forecast_horizon_bars < 1:
            raise ValueError("forecast_horizon_bars must be >= 1")
        if self.stress_label_policy not in STRESS_LABEL_POLICIES:
            raise ValueError(
                f"Unsupported stress_label_policy: {self.stress_label_policy}"
            )
        if not (0.0 < float(self.primary_quantile) < 1.0):
            raise ValueError("primary_quantile must be between 0 and 1")
        if self.stress_label_policy != "primary_quantile" and self.secondary is None:
            raise ValueError(
                "secondary oracle is required for primary_or_secondary and primary_and_secondary policies"
            )
        if self.secondary_quantile is not None and not (0.0 < float(self.secondary_quantile) < 1.0):
            raise ValueError("secondary_quantile must be between 0 and 1")

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "primary": self.primary,
            "secondary": self.secondary,
            "forecast_horizon_bars": int(self.forecast_horizon_bars),
            "stress_label_policy": self.stress_label_policy,
            "primary_quantile": float(self.primary_quantile),
            "secondary_quantile": float(
                self.secondary_quantile
                if self.secondary_quantile is not None
                else self.primary_quantile
            ),
        }
        return payload


@dataclass(frozen=True)
class DatasetBundle:
    frame: pd.DataFrame
    manifest: Dict[str, Any]


class _AggregateProxy:
    _aggregate = SystemStressOverlay._aggregate

    def __init__(self, thresholds: Any, aggregation: Any) -> None:
        self._thr = thresholds
        self._agg = aggregation


def _set_path(mapping: Dict[str, Any], path: str, value: Any) -> None:
    cursor = mapping
    parts = path.split(".")
    for part in parts[:-1]:
        cursor = cursor.setdefault(part, {})
    cursor[parts[-1]] = value


def _coerce_integral_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    rounded = pd.Series(np.rint(numeric), index=series.index, dtype="float64")
    mask = numeric.notna() & np.isclose(numeric, rounded, atol=1e-9)

    coerced = pd.Series(pd.NA, index=series.index, dtype="Int64")
    if bool(mask.any()):
        coerced.loc[mask] = rounded.loc[mask].astype("int64")
    return coerced


def _normalize_path_token(token: str | Path) -> str:
    return Path(token).as_posix().strip()


def load_exclusion_policy(path: Path | None) -> dict[str, set[str]]:
    if path is None:
        return {"exclude_dates": set(), "exclude_files": set()}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        "exclude_dates": {_normalize_path_token(item) for item in payload.get("exclude_dates", [])},
        "exclude_files": {_normalize_path_token(item) for item in payload.get("exclude_files", [])},
    }


def scan_recorder_files(
    recorder_dir: Path,
    *,
    start: date | None,
    end: date | None,
    symbols: Sequence[str],
    tf_sec: int,
    exclusion_policy: Mapping[str, set[str]] | None = None,
) -> tuple[list[Path], list[dict[str, Any]]]:
    included_paths: list[Path] = []
    excluded_records: list[dict[str, Any]] = []
    policy = exclusion_policy or {
        "exclude_dates": set(), "exclude_files": set()}

    if not recorder_dir.exists():
        return included_paths, excluded_records

    target_symbols = {symbol.upper() for symbol in symbols}
    exclude_dates = set(policy.get("exclude_dates", set()))
    exclude_files = set(policy.get("exclude_files", set()))

    for day_dir in sorted(path for path in recorder_dir.iterdir() if path.is_dir()):
        try:
            day = parse_date(day_dir.name)
        except ValueError:
            continue

        if start and day < start:
            continue
        if end and day >= end:
            continue

        for symbol in target_symbols:
            path = day_dir / f"{symbol}_{int(tf_sec)}.csv"
            if not path.exists():
                continue

            relative_path = path.relative_to(recorder_dir).as_posix()
            if day_dir.name in exclude_dates:
                excluded_records.append(
                    {"path": relative_path, "reason": f"excluded_date:{day_dir.name}"}
                )
                continue
            if relative_path in exclude_files or path.as_posix() in exclude_files:
                excluded_records.append(
                    {"path": relative_path, "reason": "excluded_file"}
                )
                continue

            included_paths.append(path)

    return included_paths, excluded_records


def _load_recorder_paths(
    csv_paths: Sequence[Path],
    *,
    target_symbols: set[str],
    tf_sec: int,
    skip_bad_csvs: bool = False,
    skipped_paths: list[str] | None = None,
    loaded_paths: list[Path] | None = None,
) -> pd.DataFrame:
    out: list[pd.DataFrame] = []
    for path in csv_paths:
        symbol = path.stem.rsplit("_", 1)[0].upper()
        if symbol not in target_symbols:
            continue
        try:
            df = pd.read_csv(path)
        except Exception as exc:
            if skip_bad_csvs:
                if skipped_paths is not None:
                    skipped_paths.append(f"{path}: {exc}")
                continue
            raise ValueError(
                f"Recorder CSV parse failed for {path}: {exc}") from exc

        if "symbol" not in df.columns:
            df["symbol"] = symbol
        out.append(df)
        if loaded_paths is not None:
            loaded_paths.append(path)

    if not out:
        return pd.DataFrame()

    df = pd.concat(out, ignore_index=True)
    if "timestamp" in df.columns:
        df["timestamp"] = _coerce_integral_series(df["timestamp"])
        df = df[df["timestamp"].notna()].copy()
    if "tf_sec" in df.columns:
        df["tf_sec"] = _coerce_integral_series(df["tf_sec"])
        df = df[df["tf_sec"] == int(tf_sec)]

    for column in ["open", "high", "low", "close"]:
        if column not in df.columns:
            if column == "close":
                raise ValueError("CSV must contain 'close' column")
            df[column] = df["close"]

    return df.sort_values(["symbol", "timestamp"], kind="mergesort").reset_index(drop=True)


def load_recorder_dataset(
    recorder_dir: Path,
    *,
    start: date | None,
    end: date | None,
    symbols: Sequence[str],
    tf_sec: int,
    skip_bad_csvs: bool = False,
    skipped_paths: list[str] | None = None,
) -> pd.DataFrame:
    included_paths, _ = scan_recorder_files(
        recorder_dir,
        start=start,
        end=end,
        symbols=symbols,
        tf_sec=tf_sec,
        exclusion_policy=None,
    )
    return _load_recorder_paths(
        included_paths,
        target_symbols={symbol.upper() for symbol in symbols},
        tf_sec=tf_sec,
        skip_bad_csvs=skip_bad_csvs,
        skipped_paths=skipped_paths,
    )


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_dataset_bundle(
    recorder_dir: Path,
    *,
    start: date | None,
    end: date | None,
    symbols: Sequence[str],
    tf_sec: int,
    exclusion_policy: Mapping[str, set[str]] | None = None,
    skip_bad_csvs: bool = False,
) -> DatasetBundle:
    selected_paths, excluded_records = scan_recorder_files(
        recorder_dir,
        start=start,
        end=end,
        symbols=symbols,
        tf_sec=tf_sec,
        exclusion_policy=exclusion_policy,
    )
    loaded_paths: list[Path] = []
    skipped_messages: list[str] = []
    frame = _load_recorder_paths(
        selected_paths,
        target_symbols={symbol.upper() for symbol in symbols},
        tf_sec=tf_sec,
        skip_bad_csvs=skip_bad_csvs,
        skipped_paths=skipped_messages,
        loaded_paths=loaded_paths,
    )

    skipped_loaded = {
        Path(message.split(":", 1)[0]) for message in skipped_messages}
    for skipped in sorted(skipped_loaded):
        excluded_records.append(
            {
                "path": skipped.relative_to(recorder_dir).as_posix(),
                "reason": "parse_error_skip",
            }
        )

    file_hashes = {
        path.relative_to(recorder_dir).as_posix(): _hash_file(path)
        for path in sorted(loaded_paths)
    }
    fingerprint_payload = json.dumps(
        file_hashes, sort_keys=True).encode("utf-8")
    fingerprint = hashlib.sha256(fingerprint_payload).hexdigest()

    materialized = materialize_day_column(frame)
    manifest = {
        "schema_version": 1,
        "recorder_dir": recorder_dir.as_posix(),
        "symbols": sorted({symbol.upper() for symbol in symbols}),
        "tf_sec": int(tf_sec),
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "included_files": sorted(file_hashes.keys()),
        "excluded_files": sorted(excluded_records, key=lambda item: (item["path"], item["reason"])),
        "file_hashes": file_hashes,
        "fingerprint": fingerprint,
        "row_count": int(len(materialized)),
        "day_count": int(materialized["__day"].nunique()) if not materialized.empty else 0,
        "days": sorted(materialized["__day"].unique().tolist()) if not materialized.empty else [],
        "skip_bad_csvs": bool(skip_bad_csvs),
    }
    return DatasetBundle(frame=materialized, manifest=manifest)


def validate_dataset_manifest(
    actual_manifest: Mapping[str, Any],
    expected_manifest: Mapping[str, Any],
    *,
    strict: bool,
) -> list[str]:
    diffs: list[str] = []
    compare_keys = [
        "symbols",
        "tf_sec",
        "start",
        "end",
        "included_files",
        "excluded_files",
        "fingerprint",
        "row_count",
        "day_count",
        "days",
    ]
    for key in compare_keys:
        if actual_manifest.get(key) != expected_manifest.get(key):
            diffs.append(
                f"manifest mismatch for {key}: expected={expected_manifest.get(key)!r} actual={actual_manifest.get(key)!r}"
            )
    if strict and diffs:
        raise ValueError(
            "Dataset manifest divergence detected: " + "; ".join(diffs))
    return diffs


def materialize_day_column(df: pd.DataFrame) -> pd.DataFrame:
    materialized = df.copy()
    if "__day" in materialized.columns:
        materialized["__day"] = materialized["__day"].astype(str)
        return materialized

    if "datetime" in materialized.columns:
        day_series = materialized["datetime"].astype(str).str.slice(0, 10)
    else:
        timestamp = pd.to_numeric(materialized["timestamp"], errors="coerce")
        day_series = pd.to_datetime(
            timestamp, unit="ms", utc=True).dt.strftime("%Y-%m-%d")
    materialized["__day"] = day_series.astype(str)
    return materialized


def split_by_day(df: pd.DataFrame, *, train_frac: float) -> Split:
    if not (0.0 < train_frac < 1.0):
        raise ValueError("train_frac must be between 0 and 1 (exclusive).")

    materialized = materialize_day_column(df)
    days = sorted(set(materialized["__day"].tolist()))

    if len(days) < 2:
        return Split(
            train=materialized,
            test=materialized.iloc[0:0].copy(),
            train_days=days,
            test_days=[],
        )

    split_idx = int(len(days) * train_frac)
    split_idx = max(1, min(len(days) - 1, split_idx))
    train_days = days[:split_idx]
    test_days = days[split_idx:]

    train = materialized[materialized["__day"].isin(train_days)].copy()
    test = materialized[materialized["__day"].isin(test_days)].copy()
    return Split(train=train, test=test, train_days=train_days, test_days=test_days)


def build_walkforward_windows(
    df: pd.DataFrame,
    *,
    train_windows: int,
    validate_windows: int,
    test_windows: int,
    step_windows: int,
) -> list[WalkForwardWindow]:
    if train_windows < 1 or validate_windows < 1 or test_windows < 1:
        raise ValueError("walk-forward windows must be >= 1")
    if step_windows < 1:
        raise ValueError("step_windows must be >= 1")

    materialized = materialize_day_column(df)
    days = sorted(materialized["__day"].unique().tolist())
    total_span = train_windows + validate_windows + test_windows
    if len(days) < total_span:
        raise ValueError(
            f"Not enough unique days for walk-forward: required at least {total_span}, got {len(days)}"
        )

    windows: list[WalkForwardWindow] = []
    window_id = 1
    for start_idx in range(0, len(days) - total_span + 1, step_windows):
        train_days = days[start_idx:start_idx + train_windows]
        validate_start = start_idx + train_windows
        validate_days = days[validate_start:validate_start + validate_windows]
        test_start = validate_start + validate_windows
        test_days = days[test_start:test_start + test_windows]
        windows.append(
            WalkForwardWindow(
                window_id=window_id,
                train_days=train_days,
                validate_days=validate_days,
                test_days=test_days,
            )
        )
        window_id += 1
    if not windows:
        raise ValueError("No walk-forward windows were generated.")
    return windows


def compute_future_label_scores(
    df: pd.DataFrame,
    *,
    mode: str,
    horizon_bars: int,
) -> pd.Series:
    if horizon_bars < 1:
        raise ValueError("horizon_bars must be >= 1")

    if mode not in ORACLE_MODES:
        raise ValueError(
            f"Unsupported label mode: {mode}. Expected one of {sorted(ORACLE_MODES)}"
        )

    ordered = df.sort_values(["symbol", "timestamp"],
                             kind="mergesort").reset_index(drop=True)
    scores = np.full(len(ordered), np.nan, dtype=float)

    for _, sym_df in ordered.groupby("symbol", sort=False):
        idx = sym_df.index.to_numpy()
        close = pd.to_numeric(
            sym_df["close"], errors="coerce").to_numpy(dtype=float)
        high = pd.to_numeric(
            sym_df["high"], errors="coerce").to_numpy(dtype=float)
        low = pd.to_numeric(
            sym_df["low"], errors="coerce").to_numpy(dtype=float)
        log_close = np.where(close > 0.0, np.log(close), np.nan)
        log_ret = np.full(len(sym_df), np.nan, dtype=float)
        if len(sym_df) >= 2:
            log_ret[1:] = np.diff(log_close)

        for local_i, global_i in enumerate(idx):
            end = min(len(sym_df), local_i + 1 + horizon_bars)
            if end <= local_i + 1:
                continue

            if mode == "future_vol":
                future = log_ret[local_i + 1:end]
                future = future[np.isfinite(future)]
                if len(future) >= 2:
                    scores[global_i] = float(np.std(future, ddof=0))
                continue

            current_close = close[local_i]
            if not np.isfinite(current_close) or current_close <= 0.0:
                continue

            if mode == "future_range":
                future_high = high[local_i + 1:end]
                future_low = low[local_i + 1:end]
                future_high = future_high[np.isfinite(future_high)]
                future_low = future_low[np.isfinite(future_low)]
                if len(future_high) >= 1 and len(future_low) >= 1:
                    scores[global_i] = float(
                        (np.max(future_high) - np.min(future_low)) / current_close
                    )
                continue

            future_close = close[end - 1]
            if np.isfinite(future_close) and future_close > 0.0:
                scores[global_i] = float(
                    abs(math.log(future_close / current_close)))

    return pd.Series(scores, index=ordered.index, dtype=float)


def compute_oracle_score_cache(df: pd.DataFrame, *, oracle: OracleSpec) -> dict[str, pd.Series]:
    cache = {
        oracle.primary: compute_future_label_scores(
            df, mode=oracle.primary, horizon_bars=oracle.forecast_horizon_bars
        )
    }
    if oracle.secondary is not None and oracle.secondary not in cache:
        cache[oracle.secondary] = compute_future_label_scores(
            df, mode=oracle.secondary, horizon_bars=oracle.forecast_horizon_bars
        )
    return cache


def threshold_from_train_scores(scores: pd.Series, *, quantile: float) -> float:
    if not (0.0 < quantile < 1.0):
        raise ValueError("quantile must be between 0 and 1 (exclusive).")
    finite_scores = pd.to_numeric(scores, errors="coerce")
    finite_scores = finite_scores[np.isfinite(finite_scores)]
    if finite_scores.empty:
        raise ValueError(
            "No finite train scores available to derive a label threshold."
        )
    return float(np.nanquantile(finite_scores.to_numpy(dtype=float), quantile))


def derive_oracle_labels(
    *,
    primary_scores: pd.Series,
    secondary_scores: pd.Series | None,
    train_mask: pd.Series,
    target_mask: pd.Series,
    oracle: OracleSpec,
) -> tuple[pd.Series, dict[str, float]]:
    primary_threshold = threshold_from_train_scores(
        primary_scores[train_mask], quantile=float(oracle.primary_quantile)
    )
    primary_target = primary_scores[target_mask] >= primary_threshold
    thresholds = {"primary_threshold": float(primary_threshold)}

    if oracle.stress_label_policy == "primary_quantile":
        return primary_target.astype(bool), thresholds

    if secondary_scores is None:
        raise ValueError(
            "secondary_scores required for the configured stress_label_policy"
        )
    secondary_quantile = float(
        oracle.secondary_quantile
        if oracle.secondary_quantile is not None
        else oracle.primary_quantile
    )
    secondary_threshold = threshold_from_train_scores(
        secondary_scores[train_mask], quantile=secondary_quantile
    )
    secondary_target = secondary_scores[target_mask] >= secondary_threshold
    thresholds["secondary_threshold"] = float(secondary_threshold)

    if oracle.stress_label_policy == "primary_or_secondary":
        return (primary_target | secondary_target).astype(bool), thresholds
    return (primary_target & secondary_target).astype(bool), thresholds


def normalize_weights(weights: Mapping[str, float]) -> Dict[str, float]:
    total = float(sum(float(value) for value in weights.values()))
    if total <= 0.0:
        raise ValueError("Weight sum must be positive.")
    return {
        key: round(float(value) / total, 10)
        for key, value in weights.items()
    }


def collect_active_weight_keys(config: Any) -> list[str]:
    ss_cfg = getattr(config, "system_stress", None)
    if ss_cfg is None:
        raise ValueError("Config does not contain system_stress section.")

    supported = ["atr", "vol", "gap", "range"]
    weights = dict(getattr(ss_cfg.aggregation, "weights", {}) or {})
    active: list[str] = []
    for name in supported:
        sigma = getattr(ss_cfg.thresholds, f"{name}_sigma", 0.0)
        if float(sigma) > 0.0 and (
            str(getattr(ss_cfg.aggregation, "method", "")) != "weighted_vote"
            or name in weights
        ):
            active.append(name)
    if not active:
        raise ValueError(
            "No active price triggers found for system stress calibration."
        )
    return active


def _integer_weight_compositions(total_units: int, parts: int) -> Iterator[list[int]]:
    if parts == 1:
        yield [total_units]
        return
    for value in range(total_units + 1):
        for rest in _integer_weight_compositions(total_units - value, parts - 1):
            yield [value, *rest]


def generate_weight_candidates(weight_keys: Sequence[str], *, step: float) -> list[Dict[str, float]]:
    if not weight_keys:
        raise ValueError("weight_keys must not be empty")
    if step <= 0.0 or step > 1.0:
        raise ValueError("step must be within (0, 1].")

    units = round(1.0 / step)
    if not math.isclose(units * step, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError(
            "step must evenly divide 1.0, for example 0.5, 0.25, 0.1, or 0.05."
        )

    candidates: list[Dict[str, float]] = []
    for composition in _integer_weight_compositions(int(units), len(weight_keys)):
        candidate = {
            key: round(value / int(units), 10)
            for key, value in zip(weight_keys, composition)
        }
        candidates.append(candidate)
    return candidates


def quantize_weights(weights: Mapping[str, float], *, step: float) -> Dict[str, float]:
    normalized = normalize_weights(weights)
    best_candidate: Dict[str, float] | None = None
    best_distance: float | None = None
    for candidate in generate_weight_candidates(list(normalized.keys()), step=step):
        distance = sum((candidate[key] - normalized[key])
                       ** 2 for key in normalized)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_candidate = candidate
    if best_candidate is None:
        raise ValueError("Failed to quantize weights.")
    return best_candidate


def generate_candidate_specs(
    weight_keys: Sequence[str],
    *,
    aggregation_methods: Sequence[str],
    step: float,
) -> list[CandidateSpec]:
    specs: list[CandidateSpec] = []
    unique_methods = list(dict.fromkeys(str(method)
                          for method in aggregation_methods))
    for method in unique_methods:
        if method == "weighted_vote":
            for weights in generate_weight_candidates(weight_keys, step=step):
                specs.append(
                    CandidateSpec(
                        aggregation_method="weighted_vote",
                        weights=dict(weights),
                    )
                )
            continue
        if method == "k_of_n":
            for value in range(1, len(weight_keys) + 1):
                specs.append(CandidateSpec(
                    aggregation_method="k_of_n", k=value))
            continue
        if method == "max":
            specs.append(CandidateSpec(aggregation_method="max"))
            continue
        raise ValueError(f"Unsupported aggregation method: {method}")
    return specs


def build_evaluation_config(
    base_cfg_dict: Dict[str, Any],
    *,
    tf_sec: int,
    aggregation_method: Literal["weighted_vote",
                                "k_of_n", "max"] = "weighted_vote",
    weights: Mapping[str, float] | None = None,
    k: int | None = None,
    baseline_window: int | None = None,
    burn_in_bars: int | None = None,
) -> Any:
    cfg_dict = copy.deepcopy(base_cfg_dict)
    overlay: dict[str, Any] = {
        "basis_tf_sec": int(tf_sec),
        "system_stress.enabled": True,
        "system_stress.aggregation.method": aggregation_method,
    }
    if aggregation_method == "weighted_vote":
        if weights is None:
            raise ValueError(
                "weights are required for weighted_vote calibration")
        overlay["system_stress.aggregation.weights"] = dict(
            normalize_weights(weights))
    else:
        overlay["system_stress.aggregation.weights"] = None
    if aggregation_method == "k_of_n":
        if k is None:
            raise ValueError("k is required when aggregation_method=k_of_n")
        overlay["system_stress.aggregation.k"] = int(k)
    if baseline_window is not None:
        overlay["system_stress.baseline_window"] = int(baseline_window)
    if burn_in_bars is not None:
        overlay["system_stress.burn_in_bars"] = int(burn_in_bars)

    for path, value in overlay.items():
        _set_path(cfg_dict, path, value)

    from apps.reference.config_models import AuroraConfig as PydanticAuroraConfig

    return PydanticAuroraConfig(**cfg_dict)


def simulate_stress_states(df: pd.DataFrame, *, config: Any) -> pd.DataFrame:
    ordered = df.sort_values(["symbol", "timestamp"],
                             kind="mergesort").reset_index(drop=True)
    ss_cfg = config.system_stress
    aggregator = _AggregateProxy(ss_cfg.thresholds, ss_cfg.aggregation)

    metric_states: Dict[str, _SymbolStressState] = {}
    actuators: Dict[str, _StressActuator] = {}
    rows: list[Dict[str, Any]] = []

    for row in ordered.itertuples(index=False):
        symbol = str(getattr(row, "symbol"))
        open_ = float(getattr(row, "open"))
        high = float(getattr(row, "high"))
        low = float(getattr(row, "low"))
        close = float(getattr(row, "close"))

        if symbol not in metric_states:
            metric_states[symbol] = _SymbolStressState(
                window=int(ss_cfg.baseline_window),
                robust_method=str(
                    getattr(ss_cfg, "robust_method", "none") or "none"),
            )
            actuators[symbol] = _StressActuator(sm=ss_cfg.state_mapping)

        metric_state = metric_states[symbol]
        actuator = actuators[symbol]
        z_atr, z_vol, z_gap, z_range, _, _, _, _ = metric_state.update(
            open_=open_,
            high=high,
            low=low,
            close=close,
        )

        eligible = metric_state.bars_seen >= int(ss_cfg.burn_in_bars)
        if eligible:
            stress_level = float(aggregator._aggregate(
                z_atr, z_vol, z_gap, z_range))
            state, _ = actuator.step(stress_level)
        else:
            stress_level = 0.0
            state = actuator.state

        rows.append(
            {
                "pred_state": state,
                "pred_positive": state in {"STRESS", "EXTREME"},
                "stress_level": stress_level,
                "eligible": eligible,
            }
        )

    return pd.DataFrame(rows, index=ordered.index)


def _state_statistics(states: pd.Series | None, evaluated_rows: int) -> dict[str, float]:
    if states is None or states.empty:
        return {
            "state_switch_count": 0.0,
            "avg_dwell_bars": 0.0,
            "total_dwell_bars": 0.0,
            "dwell_segments": 0.0,
            "normal_rows": float(evaluated_rows),
            "stress_rows": 0.0,
            "extreme_rows": 0.0,
            "stress_rate": 0.0,
            "extreme_rate": 0.0,
            "normal_rate": 1.0 if evaluated_rows else 0.0,
        }

    state_values = states.astype(str).tolist()
    switch_count = sum(1 for left, right in zip(
        state_values, state_values[1:]) if left != right)
    dwell_lengths: list[int] = []
    current_dwell = 1 if state_values else 0
    for left, right in zip(state_values, state_values[1:]):
        if left == right:
            current_dwell += 1
        else:
            dwell_lengths.append(current_dwell)
            current_dwell = 1
    if current_dwell:
        dwell_lengths.append(current_dwell)

    normal_rows = sum(1 for value in state_values if value == "NORMAL")
    stress_rows = sum(1 for value in state_values if value == "STRESS")
    extreme_rows = sum(1 for value in state_values if value == "EXTREME")
    dwell_segments = len(dwell_lengths)
    total_dwell_bars = float(sum(dwell_lengths))
    avg_dwell_bars = total_dwell_bars / dwell_segments if dwell_segments else 0.0
    return {
        "state_switch_count": float(switch_count),
        "avg_dwell_bars": float(avg_dwell_bars),
        "total_dwell_bars": float(total_dwell_bars),
        "dwell_segments": float(dwell_segments),
        "normal_rows": float(normal_rows),
        "stress_rows": float(stress_rows),
        "extreme_rows": float(extreme_rows),
        "stress_rate": float(stress_rows / evaluated_rows) if evaluated_rows else 0.0,
        "extreme_rate": float(extreme_rows / evaluated_rows) if evaluated_rows else 0.0,
        "normal_rate": float(normal_rows / evaluated_rows) if evaluated_rows else 0.0,
    }


def binary_metrics(
    y_true: pd.Series,
    y_pred: pd.Series,
    *,
    states: pd.Series | None,
    total_rows: int,
) -> Dict[str, float]:
    true_values = y_true.astype(bool).to_numpy(dtype=bool)
    pred_values = y_pred.astype(bool).to_numpy(dtype=bool)

    tp = int(np.sum(pred_values & true_values))
    tn = int(np.sum((~pred_values) & (~true_values)))
    fp = int(np.sum(pred_values & (~true_values)))
    fn = int(np.sum((~pred_values) & true_values))

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2.0 * precision * recall / \
        (precision + recall) if (precision + recall) else 0.0
    tnr = tn / (tn + fp) if (tn + fp) else 0.0
    balanced_accuracy = 0.5 * (recall + tnr)
    evaluated_rows = len(true_values)
    alert_rate = float(np.mean(pred_values)) if evaluated_rows else 0.0
    label_rate = float(np.mean(true_values)) if evaluated_rows else 0.0
    state_stats = _state_statistics(states, evaluated_rows)

    return {
        "tp": float(tp),
        "tn": float(tn),
        "fp": float(fp),
        "fn": float(fn),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "balanced_accuracy": float(balanced_accuracy),
        "alert_rate": float(alert_rate),
        "label_rate": float(label_rate),
        "alert_gap": float(abs(alert_rate - label_rate)),
        "overblocking_proxy": float(max(0.0, alert_rate - label_rate)),
        "coverage": float(evaluated_rows / total_rows) if total_rows else 0.0,
        "rows": float(evaluated_rows),
        "target_rows": float(total_rows),
        "state_switch_count": float(state_stats["state_switch_count"]),
        "state_switches_per_1000": (
            float(state_stats["state_switch_count"]) / evaluated_rows * 1000.0
            if evaluated_rows
            else 0.0
        ),
        "avg_dwell_bars": float(state_stats["avg_dwell_bars"]),
        "total_dwell_bars": float(state_stats["total_dwell_bars"]),
        "dwell_segments": float(state_stats["dwell_segments"]),
        "normal_rows": float(state_stats["normal_rows"]),
        "stress_rows": float(state_stats["stress_rows"]),
        "extreme_rows": float(state_stats["extreme_rows"]),
        "normal_rate": float(state_stats["normal_rate"]),
        "stress_rate": float(state_stats["stress_rate"]),
        "extreme_rate": float(state_stats["extreme_rate"]),
    }


def evaluate_candidate(
    df: pd.DataFrame,
    *,
    base_cfg_dict: Dict[str, Any],
    weights: Mapping[str, float] | None,
    tf_sec: int,
    label_scores: pd.Series,
    label_threshold: float,
    aggregation_method: Literal["weighted_vote",
                                "k_of_n", "max"] = "weighted_vote",
    k: int | None = None,
    baseline_window: int | None = None,
    burn_in_bars: int | None = None,
) -> Dict[str, float]:
    config = build_evaluation_config(
        base_cfg_dict,
        tf_sec=tf_sec,
        aggregation_method=aggregation_method,
        weights=weights,
        k=k,
        baseline_window=baseline_window,
        burn_in_bars=burn_in_bars,
    )
    preds = simulate_stress_states(df, config=config)

    scores = pd.to_numeric(label_scores, errors="coerce")
    labels = scores >= float(label_threshold)
    mask = preds["eligible"].astype(bool) & np.isfinite(
        scores.to_numpy(dtype=float))

    if not bool(mask.any()):
        raise ValueError(
            "No evaluable rows remained after burn-in and future-label masking."
        )

    return binary_metrics(
        labels[mask],
        preds.loc[mask, "pred_positive"],
        states=preds.loc[mask, "pred_state"],
        total_rows=len(df),
    )


def _aggregate_metric_dicts(metrics_list: Sequence[Mapping[str, float]]) -> Dict[str, float]:
    if not metrics_list:
        raise ValueError("metrics_list must not be empty")
    tp = sum(float(item["tp"]) for item in metrics_list)
    tn = sum(float(item["tn"]) for item in metrics_list)
    fp = sum(float(item["fp"]) for item in metrics_list)
    fn = sum(float(item["fn"]) for item in metrics_list)
    rows = sum(float(item["rows"]) for item in metrics_list)
    target_rows = sum(float(item["target_rows"]) for item in metrics_list)
    switch_count = sum(float(item["state_switch_count"])
                       for item in metrics_list)
    total_dwell_bars = sum(float(item["total_dwell_bars"])
                           for item in metrics_list)
    dwell_segments = sum(float(item["dwell_segments"])
                         for item in metrics_list)
    normal_rows = sum(float(item["normal_rows"]) for item in metrics_list)
    stress_rows = sum(float(item["stress_rows"]) for item in metrics_list)
    extreme_rows = sum(float(item["extreme_rows"]) for item in metrics_list)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2.0 * precision * recall / \
        (precision + recall) if (precision + recall) else 0.0
    tnr = tn / (tn + fp) if (tn + fp) else 0.0
    balanced_accuracy = 0.5 * (recall + tnr)
    alert_rate = (tp + fp) / rows if rows else 0.0
    label_rate = (tp + fn) / rows if rows else 0.0
    avg_dwell_bars = total_dwell_bars / dwell_segments if dwell_segments else 0.0

    return {
        "tp": float(tp),
        "tn": float(tn),
        "fp": float(fp),
        "fn": float(fn),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "balanced_accuracy": float(balanced_accuracy),
        "alert_rate": float(alert_rate),
        "label_rate": float(label_rate),
        "alert_gap": float(abs(alert_rate - label_rate)),
        "overblocking_proxy": float(max(0.0, alert_rate - label_rate)),
        "coverage": float(rows / target_rows) if target_rows else 0.0,
        "rows": float(rows),
        "target_rows": float(target_rows),
        "state_switch_count": float(switch_count),
        "state_switches_per_1000": float(switch_count / rows * 1000.0) if rows else 0.0,
        "avg_dwell_bars": float(avg_dwell_bars),
        "total_dwell_bars": float(total_dwell_bars),
        "dwell_segments": float(dwell_segments),
        "normal_rows": float(normal_rows),
        "stress_rows": float(stress_rows),
        "extreme_rows": float(extreme_rows),
        "normal_rate": float(normal_rows / rows) if rows else 0.0,
        "stress_rate": float(stress_rows / rows) if rows else 0.0,
        "extreme_rate": float(extreme_rows / rows) if rows else 0.0,
    }


def _mean_metric_dicts(metrics_list: Sequence[Mapping[str, float]]) -> Dict[str, float]:
    if not metrics_list:
        raise ValueError("metrics_list must not be empty")
    keys = [
        "f1",
        "precision",
        "recall",
        "balanced_accuracy",
        "alert_rate",
        "label_rate",
        "coverage",
        "state_switches_per_1000",
        "avg_dwell_bars",
        "overblocking_proxy",
        "alert_gap",
        "stress_rate",
        "extreme_rate",
    ]
    return {
        key: float(np.mean([float(item[key]) for item in metrics_list]))
        for key in keys
    }


def _std_metric_dicts(metrics_list: Sequence[Mapping[str, float]]) -> Dict[str, float]:
    if not metrics_list:
        raise ValueError("metrics_list must not be empty")
    keys = [
        "f1",
        "balanced_accuracy",
        "alert_rate",
        "state_switches_per_1000",
        "overblocking_proxy",
        "stress_rate",
        "extreme_rate",
    ]
    return {
        key: float(np.std([float(item[key]) for item in metrics_list], ddof=0))
        for key in keys
    }


def _worst_metric_dicts(metrics_list: Sequence[Mapping[str, float]]) -> Dict[str, float]:
    if not metrics_list:
        raise ValueError("metrics_list must not be empty")
    result: Dict[str, float] = {}
    for key in SUMMARY_HIGHER_IS_BETTER:
        result[key] = float(min(float(item[key]) for item in metrics_list))
    for key in SUMMARY_LOWER_IS_BETTER:
        result[key] = float(max(float(item[key]) for item in metrics_list))
    return result


def summarize_window_metrics(metrics_list: Sequence[Mapping[str, float]]) -> Dict[str, Dict[str, float]]:
    if not metrics_list:
        raise ValueError("metrics_list must not be empty")
    return {
        "aggregate": _aggregate_metric_dicts(metrics_list),
        "mean": _mean_metric_dicts(metrics_list),
        "std": _std_metric_dicts(metrics_list),
        "worst": _worst_metric_dicts(metrics_list),
    }


def flatten_summary_metrics(prefix: str, summary: Mapping[str, Mapping[str, float]]) -> Dict[str, float]:
    flat: Dict[str, float] = {}
    for summary_name, metrics in summary.items():
        for metric_name, value in metrics.items():
            flat[f"{prefix}_{summary_name}_{metric_name}"] = float(value)
    return flat


def _ranking_value(value: float, descending: bool) -> float:
    return float(value) if descending else -float(value)


def candidate_rank_tuple(metrics: Mapping[str, float], ranking_stack: Sequence[str]) -> tuple[float, ...]:
    rank_values: list[float] = []
    for field in ranking_stack:
        descending = True
        metric_name = field
        if field.startswith("-"):
            descending = False
            metric_name = field[1:]
        if metric_name not in metrics:
            raise KeyError(f"Ranking metric not found: {metric_name}")
        rank_values.append(_ranking_value(
            float(metrics[metric_name]), descending))
    return tuple(rank_values)


def evaluate_candidate_walkforward(
    frame: pd.DataFrame,
    *,
    windows: Sequence[WalkForwardWindow],
    score_cache: Mapping[str, pd.Series],
    oracle: OracleSpec,
    base_cfg_dict: Dict[str, Any],
    candidate: CandidateSpec,
    tf_sec: int,
    baseline_window: int | None = None,
    burn_in_bars: int | None = None,
    ranking_stack: Sequence[str] | None = None,
) -> Dict[str, Any]:
    materialized = materialize_day_column(frame)
    validate_window_metrics: list[dict[str, float]] = []
    test_window_metrics: list[dict[str, float]] = []
    window_rows: list[dict[str, Any]] = []

    config = build_evaluation_config(
        base_cfg_dict,
        tf_sec=tf_sec,
        aggregation_method=candidate.aggregation_method,
        weights=candidate.weights,
        k=candidate.k,
        baseline_window=baseline_window,
        burn_in_bars=burn_in_bars,
    )

    for window in windows:
        window_mask = materialized["__day"].isin(window.all_days())
        slice_df = materialized.loc[window_mask].copy().reset_index().rename(columns={
            "index": "__source_index"})
        preds = simulate_stress_states(slice_df, config=config)
        slice_df = pd.concat([slice_df.reset_index(
            drop=True), preds.reset_index(drop=True)], axis=1)

        train_mask = slice_df["__day"].isin(window.train_days)
        validate_mask = slice_df["__day"].isin(window.validate_days)
        test_mask = slice_df["__day"].isin(window.test_days)

        primary_scores = score_cache[oracle.primary].loc[slice_df["__source_index"]].reset_index(
            drop=True)
        secondary_scores = None
        if oracle.secondary is not None:
            secondary_scores = score_cache[oracle.secondary].loc[slice_df["__source_index"]].reset_index(
                drop=True)

        validate_labels, thresholds = derive_oracle_labels(
            primary_scores=primary_scores,
            secondary_scores=secondary_scores,
            train_mask=train_mask.reset_index(drop=True),
            target_mask=validate_mask.reset_index(drop=True),
            oracle=oracle,
        )
        validate_labels = validate_labels.reset_index(drop=True)
        test_labels, _ = derive_oracle_labels(
            primary_scores=primary_scores,
            secondary_scores=secondary_scores,
            train_mask=train_mask.reset_index(drop=True),
            target_mask=test_mask.reset_index(drop=True),
            oracle=oracle,
        )
        test_labels = test_labels.reset_index(drop=True)

        validate_scores = primary_scores[validate_mask.reset_index(drop=True)]
        validate_pred_mask = (
            slice_df.loc[validate_mask, "eligible"].reset_index(
                drop=True).astype(bool)
            & np.isfinite(validate_scores.to_numpy(dtype=float))
        )
        if not bool(validate_pred_mask.any()):
            raise ValueError(
                f"No evaluable validate rows for window {window.window_id}; adjust burn-in or oracle horizon."
            )
        validate_metrics = binary_metrics(
            validate_labels[validate_pred_mask],
            slice_df.loc[validate_mask, "pred_positive"].reset_index(drop=True)[
                validate_pred_mask],
            states=slice_df.loc[validate_mask, "pred_state"].reset_index(drop=True)[
                validate_pred_mask],
            total_rows=int(validate_mask.sum()),
        )

        test_scores = primary_scores[test_mask.reset_index(drop=True)]
        test_pred_mask = (
            slice_df.loc[test_mask, "eligible"].reset_index(
                drop=True).astype(bool)
            & np.isfinite(test_scores.to_numpy(dtype=float))
        )
        if not bool(test_pred_mask.any()):
            raise ValueError(
                f"No evaluable test rows for window {window.window_id}; adjust burn-in or oracle horizon."
            )
        test_metrics = binary_metrics(
            test_labels[test_pred_mask],
            slice_df.loc[test_mask, "pred_positive"].reset_index(drop=True)[
                test_pred_mask],
            states=slice_df.loc[test_mask, "pred_state"].reset_index(drop=True)[
                test_pred_mask],
            total_rows=int(test_mask.sum()),
        )

        validate_window_metrics.append(validate_metrics)
        test_window_metrics.append(test_metrics)
        window_rows.append(
            {
                "window_id": int(window.window_id),
                "train_days": list(window.train_days),
                "validate_days": list(window.validate_days),
                "test_days": list(window.test_days),
                "thresholds": thresholds,
                "validate": validate_metrics,
                "test": test_metrics,
            }
        )

    validate_summary = summarize_window_metrics(validate_window_metrics)
    test_summary = summarize_window_metrics(test_window_metrics)
    flat_metrics = {}
    flat_metrics.update(flatten_summary_metrics("validate", validate_summary))
    flat_metrics.update(flatten_summary_metrics("test", test_summary))

    ranking_stack = list(ranking_stack or [])
    rank_tuple = candidate_rank_tuple(
        flat_metrics, ranking_stack) if ranking_stack else ()
    return {
        "candidate": candidate.as_dict(),
        "validate": validate_summary,
        "test": test_summary,
        "window_rows": window_rows,
        "ranking_metrics": flat_metrics,
        "ranking_tuple": list(rank_tuple),
    }


def search_weight_grid(
    train_df: pd.DataFrame,
    *,
    base_cfg_dict: Dict[str, Any],
    weight_keys: Sequence[str],
    tf_sec: int,
    label_scores: pd.Series,
    label_threshold: float,
    step: float,
    aggregation_methods: Sequence[str] | None = None,
    baseline_window: int | None = None,
    burn_in_bars: int | None = None,
) -> list[CandidateResult]:
    methods = aggregation_methods or ["weighted_vote"]
    results: list[CandidateResult] = []
    for candidate in generate_candidate_specs(weight_keys, aggregation_methods=methods, step=step):
        metrics = evaluate_candidate(
            train_df,
            base_cfg_dict=base_cfg_dict,
            weights=candidate.weights,
            aggregation_method=candidate.aggregation_method,
            k=candidate.k,
            tf_sec=tf_sec,
            label_scores=label_scores,
            label_threshold=label_threshold,
            baseline_window=baseline_window,
            burn_in_bars=burn_in_bars,
        )
        results.append(CandidateResult(candidate=candidate, metrics=metrics))

    results.sort(
        key=lambda result: (
            float(result.metrics["balanced_accuracy"]),
            float(result.metrics["f1"]),
            -float(result.metrics["overblocking_proxy"]),
            -float(result.metrics["state_switches_per_1000"]),
            -float(result.metrics["alert_gap"]),
        ),
        reverse=True,
    )
    return results


def load_base_config_dict() -> Dict[str, Any]:
    return get_config().model_dump()
