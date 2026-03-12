from __future__ import annotations

import copy
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.objective_engine.normalizers import sigmoid_normalize

from .features import OBJECTIVE_COMPONENTS
from .metrics import compute_candidate_summary, passes_hard_rejection_gates


@dataclass(slots=True)
class ObjectiveCandidate:
    score: float
    summary: dict[str, Any]
    domain_overlay: dict[str, Any]
    strategy_overlays: dict[str, dict[str, Any]]


def split_walk_forward(
    df: pd.DataFrame,
    *,
    ts_col: str = "ts_ms",
    fractions: tuple[float, float, float] = (0.6, 0.2, 0.2),
) -> dict[str, pd.DataFrame]:
    if df.empty:
        return {"train": df.copy(), "validation": df.copy(), "test": df.copy()}
    if abs(sum(fractions) - 1.0) > 1e-9:
        raise ValueError("walk-forward fractions must sum to 1.0")
    ordered = df.sort_values(ts_col, kind="mergesort").reset_index(drop=True)
    n = len(ordered)
    train_end = max(1, int(n * fractions[0]))
    val_end = max(train_end + 1, int(n * (fractions[0] + fractions[1]))) if n >= 3 else n
    return {
        "train": ordered.iloc[:train_end].copy(),
        "validation": ordered.iloc[train_end:val_end].copy(),
        "test": ordered.iloc[val_end:].copy(),
    }


def _load_current_objective_overlays(config_root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    cfg = ConfigLoader(config_root).load_config()
    domain_overlay = {"objective_engine": cfg.domains.objective_engine.model_dump(mode="python")}
    strategy_overlays = {
        "aurora": {"aurora": {"objective": cfg.strategies.aurora.objective.model_dump(mode="python")}},
        "md_amr": {"md_amr": {"objective": cfg.strategies.md_amr.objective.model_dump(mode="python")}},
        "mean_reversion": {"mean_reversion": {"objective": cfg.strategies.mean_reversion.objective.model_dump(mode="python")}},
    }
    return domain_overlay, strategy_overlays


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _base_profiles(config_root: Path, strategy_bundle_path: Path | None) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    domain_overlay, strategy_overlays = _load_current_objective_overlays(config_root)
    external_bundle = _load_json(strategy_bundle_path)
    if isinstance(external_bundle, dict):
        strategy_overlays = external_bundle.get("strategy_overlays", strategy_overlays)
    return domain_overlay, strategy_overlays


def _regime_profile_for(strategy_overlays: dict[str, dict[str, Any]], strategy_id: str, regime: str) -> dict[str, Any] | None:
    strategy_payload = strategy_overlays.get(strategy_id, {})
    inner = next(iter(strategy_payload.values()), {}) if isinstance(strategy_payload, dict) else {}
    objective = inner.get("objective") if isinstance(inner, dict) else None
    if not isinstance(objective, dict):
        return None
    regimes = objective.get("regimes")
    if not isinstance(regimes, dict):
        return None
    return regimes.get(str(regime))


def _recompute_candidate_frame(realized_df: pd.DataFrame, strategy_overlays: dict[str, dict[str, Any]]) -> pd.DataFrame:
    if realized_df.empty:
        return realized_df.copy()
    df = realized_df.copy()
    candidate_scores: list[float] = []
    candidate_blocked: list[bool] = []
    missing_rates: list[float] = []
    for _, row in df.iterrows():
        strategy_id = str(row.get("strategy_id") or "")
        regime = str(row.get("regime") or "")
        profile = _regime_profile_for(strategy_overlays, strategy_id, regime)
        if not isinstance(profile, dict):
            candidate_scores.append(float("nan"))
            candidate_blocked.append(True)
            missing_rates.append(1.0)
            continue
        weights = profile.get("weights") if isinstance(profile.get("weights"), dict) else {}
        multiplier_cfg = profile.get("multiplier") if isinstance(profile.get("multiplier"), dict) else {}
        gate_cfg = profile.get("gate") if isinstance(profile.get("gate"), dict) else {}
        total_penalty = 0.0
        missing_component = False
        for component in OBJECTIVE_COMPONENTS:
            column = f"pretrade_component_{component}"
            if column not in df.columns or pd.isna(row.get(column)):
                missing_component = True
                break
            total_penalty += float(weights.get(component, 0.0)) * float(row[column])
        original_score = row.get("pretrade_original_score")
        if pd.isna(original_score):
            original_score = row.get("pretrade_objective_score")
        if missing_component or pd.isna(original_score):
            candidate_scores.append(float("nan"))
            candidate_blocked.append(True)
            missing_rates.append(1.0)
            continue
        z_value = total_penalty * float(multiplier_cfg.get("lambda_scale", 1.0))
        normalized_penalty = sigmoid_normalize(
            z_value,
            center=float(multiplier_cfg.get("penalty_center", 0.0)),
            scale=float(multiplier_cfg.get("penalty_scale", 1.0)),
        )
        m_min = float(multiplier_cfg.get("m_min", 0.1))
        m_max = float(multiplier_cfg.get("m_max", 1.5))
        multiplier = m_min + normalized_penalty * (m_max - m_min)
        multiplier = max(m_min, min(multiplier, m_max))
        score = float(original_score) * multiplier
        enforcement_mode = str(gate_cfg.get("enforcement_mode", "OBSERVE")).upper()
        min_score = float(gate_cfg.get("min_objective_score", 0.0))
        blocked = enforcement_mode == "GATE" and abs(score) < min_score
        candidate_scores.append(score)
        candidate_blocked.append(blocked)
        missing_rates.append(0.0)
    df["candidate_objective_score"] = candidate_scores
    df["candidate_blocked"] = candidate_blocked
    df["missing_objective_input_rate"] = missing_rates
    return df


def _mutate_strategy_overlays(strategy_overlays: dict[str, dict[str, Any]], *, rng: random.Random) -> dict[str, dict[str, Any]]:
    mutated = copy.deepcopy(strategy_overlays)
    for payload in mutated.values():
        strategy_root = next(iter(payload.values()), None) if isinstance(payload, dict) else None
        objective = strategy_root.get("objective") if isinstance(strategy_root, dict) else None
        regimes = objective.get("regimes") if isinstance(objective, dict) else None
        if not isinstance(regimes, dict):
            continue
        for profile in regimes.values():
            weights = profile.get("weights")
            if isinstance(weights, dict):
                for key, value in list(weights.items()):
                    weights[key] = round(float(value) * rng.uniform(0.8, 1.2), 6)
            multiplier = profile.get("multiplier")
            if isinstance(multiplier, dict):
                multiplier["lambda_scale"] = round(float(multiplier.get("lambda_scale", 1.0)) * rng.uniform(0.85, 1.15), 6)
                multiplier["penalty_center"] = round(float(multiplier.get("penalty_center", 0.0)) + rng.uniform(-0.5, 0.5), 6)
                multiplier["penalty_scale"] = round(max(0.1, float(multiplier.get("penalty_scale", 1.0)) * rng.uniform(0.85, 1.15)), 6)
            gate = profile.get("gate")
            if isinstance(gate, dict):
                gate["min_objective_score"] = round(max(0.0, float(gate.get("min_objective_score", 0.0)) * rng.uniform(0.8, 1.2)), 6)
    return mutated


def search_objective_candidates(
    *,
    realized_df: pd.DataFrame,
    attempted_df: pd.DataFrame,
    config_root: Path,
    strategy_bundle_path: Path | None,
    trials: int,
    top_k: int,
    seed: int,
    min_trade_count: int,
) -> list[ObjectiveCandidate]:
    rng = random.Random(seed)
    domain_overlay, base_strategy_overlays = _base_profiles(config_root, strategy_bundle_path)

    baseline_frame = _recompute_candidate_frame(realized_df, base_strategy_overlays)
    baseline_summary = compute_candidate_summary(
        attempted_entries=attempted_df,
        realized_trades=baseline_frame,
    )
    candidates: list[ObjectiveCandidate] = [
        ObjectiveCandidate(
            score=float(baseline_summary["score"]),
            summary=baseline_summary,
            domain_overlay=copy.deepcopy(domain_overlay),
            strategy_overlays=copy.deepcopy(base_strategy_overlays),
        )
    ]

    for _ in range(int(trials)):
        strategy_overlays = _mutate_strategy_overlays(base_strategy_overlays, rng=rng)
        scored_frame = _recompute_candidate_frame(realized_df, strategy_overlays)
        summary = compute_candidate_summary(
            attempted_entries=attempted_df,
            realized_trades=scored_frame,
        )
        allowed, reasons = passes_hard_rejection_gates(
            summary=summary,
            baseline_summary=baseline_summary,
            min_trade_count=min_trade_count,
        )
        if not allowed:
            summary = dict(summary)
            summary["rejection_reasons"] = reasons
            continue
        candidates.append(
            ObjectiveCandidate(
                score=float(summary["score"]),
                summary=summary,
                domain_overlay=copy.deepcopy(domain_overlay),
                strategy_overlays=strategy_overlays,
            )
        )

    candidates = sorted(candidates, key=lambda candidate: candidate.score, reverse=True)
    return candidates[: max(1, int(top_k))]
