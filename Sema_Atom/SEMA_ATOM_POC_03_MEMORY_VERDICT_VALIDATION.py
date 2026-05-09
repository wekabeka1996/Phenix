from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_SAF_PATH = REPO_ROOT / "aurora_real_logs_v02.saf.jsonl"
DEFAULT_POC02_REPORT_PATH = REPO_ROOT / "SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT.md"
DEFAULT_REPORT_PATH = REPO_ROOT / "SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT.md"

CANONICAL_OUTCOME_MAP = {
    "ACCEPTED_WIN": "GOOD_DECISION",
    "ACCEPTED_LOSS": "CLEAN_LOSS",
    "BAD_EXIT": "BAD_EXIT",
    "REJECT_CORRECT_BLOCK": "POLICY_PROTECTED",
    "REJECT_MISSED_POSITIVE": "POLICY_TOO_STRICT",
    "ACCEPTED_FLAT": "NEUTRAL_SIGNAL",
    "REJECT_FLAT": "NEUTRAL_SIGNAL",
    "ACCEPTED_UNSCORABLE": "NEUTRAL_SIGNAL",
    "REJECT_UNSCORABLE": "NEUTRAL_SIGNAL",
}


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    return int(numeric)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def normalize_outcome_code(outcome_code: str | None) -> str:
    if outcome_code is None:
        return "NEUTRAL_SIGNAL"
    return CANONICAL_OUTCOME_MAP.get(outcome_code, "NEUTRAL_SIGNAL")


@dataclass(slots=True)
class ValidationAtom:
    atom_id: str
    event_ts_ms: int
    context_key: tuple[str, str, str, str, str]
    context: dict[str, Any]
    original_outcome_code: str
    canonical_outcome_code: str
    net_score: float
    reward_bps: float
    threat_bps: float
    surprise: float
    importance: float


@dataclass(slots=True)
class ContextSplit:
    context_key: tuple[str, str, str, str, str]
    train_atoms: list[ValidationAtom]
    validation_atoms: list[ValidationAtom]


@dataclass(slots=True)
class ContextVerdict:
    context_key: tuple[str, str, str, str, str]
    context: dict[str, Any]
    train_count: int
    validation_count: int
    verdict: str
    recommendation: str
    train_net_score: float
    train_outcome_counts: dict[str, int]
    validation_net_score: float
    validation_outcome_counts: dict[str, int]
    validation_result: str
    validation_reason: str
    policy_too_strict_rate_train: float
    negative_rate_train: float
    favorable_rate_train: float
    policy_too_strict_rate_validation: float
    negative_rate_validation: float
    favorable_rate_validation: float


def load_atoms(path: Path) -> list[ValidationAtom]:
    atoms: list[ValidationAtom] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            context = payload.get("context") or {}
            raw_contract = payload.get("raw_contract") or {}
            event_ts_ms = (
                _safe_int(raw_contract.get("event_ts_ms"))
                or _safe_int(raw_contract.get("close_ts_ms"))
                or _safe_int(raw_contract.get("entry_ts_ms"))
                or line_number
            )
            context_key = (
                str(context.get("symbol")),
                str(context.get("side")),
                str(context.get("strategy_id")),
                str(context.get("regime")),
                str(context.get("confidence_bucket")),
            )
            atoms.append(
                ValidationAtom(
                    atom_id=str(payload.get("atom_id")),
                    event_ts_ms=event_ts_ms,
                    context_key=context_key,
                    context=dict(context),
                    original_outcome_code=str(payload.get("outcome_code")),
                    canonical_outcome_code=normalize_outcome_code(_text(payload.get("outcome_code"))),
                    net_score=float(payload.get("net_score") or 0.0),
                    reward_bps=float(payload.get("reward_bps") or 0.0),
                    threat_bps=float(payload.get("threat_bps") or 0.0),
                    surprise=float(payload.get("surprise") or 0.0),
                    importance=float(payload.get("importance") or 0.0),
                )
            )
    return sorted(atoms, key=lambda atom: (atom.event_ts_ms, atom.atom_id))


def split_atoms_by_context(atoms: Sequence[ValidationAtom]) -> list[ContextSplit]:
    grouped: dict[tuple[str, str, str, str, str], list[ValidationAtom]] = defaultdict(list)
    for atom in atoms:
        grouped[atom.context_key].append(atom)

    splits: list[ContextSplit] = []
    for context_key in sorted(grouped):
        context_atoms = sorted(grouped[context_key], key=lambda atom: (atom.event_ts_ms, atom.atom_id))
        pivot = len(context_atoms) // 2
        if len(context_atoms) >= 2 and pivot == 0:
            pivot = 1
        train_atoms = context_atoms[:pivot]
        validation_atoms = context_atoms[pivot:]
        splits.append(ContextSplit(context_key=context_key, train_atoms=train_atoms, validation_atoms=validation_atoms))
    return splits


def _outcome_counts(atoms: Sequence[ValidationAtom]) -> Counter[str]:
    return Counter(atom.canonical_outcome_code for atom in atoms)


def _avg_net_score(atoms: Sequence[ValidationAtom]) -> float:
    if not atoms:
        return 0.0
    return sum(atom.net_score for atom in atoms) / len(atoms)


def _rate(counts: Counter[str], labels: Iterable[str]) -> float:
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    return sum(counts.get(label, 0) for label in labels) / total


def infer_memory_verdict(train_atoms: Sequence[ValidationAtom]) -> tuple[str, str, dict[str, float], dict[str, int]]:
    counts = _outcome_counts(train_atoms)
    train_net_score = _avg_net_score(train_atoms)
    policy_too_strict_rate = _rate(counts, ["POLICY_TOO_STRICT"])
    negative_rate = _rate(counts, ["CLEAN_LOSS", "BAD_EXIT"])
    favorable_rate = _rate(counts, ["GOOD_DECISION", "POLICY_PROTECTED"])

    if len(train_atoms) < 2:
        return (
            "LOW_SUPPORT",
            "collect_more_atoms",
            {
                "policy_too_strict_rate": policy_too_strict_rate,
                "negative_rate": negative_rate,
                "favorable_rate": favorable_rate,
                "train_net_score": train_net_score,
            },
            dict(sorted(counts.items())),
        )
    if policy_too_strict_rate >= 0.60 and counts.get("POLICY_TOO_STRICT", 0) >= 2:
        verdict = "POLICY_TOO_STRICT_CANDIDATE"
        recommendation = "review_policy_thresholds"
    elif negative_rate >= 0.50 and train_net_score < 0:
        verdict = "TOXIC_CONTEXT"
        recommendation = "avoid_or_review"
    elif favorable_rate >= 0.50 and train_net_score > 0:
        verdict = "FAVORABLE_CONTEXT"
        recommendation = "retain_or_promote"
    else:
        verdict = "MIXED_CONTEXT"
        recommendation = "monitor"
    return (
        verdict,
        recommendation,
        {
            "policy_too_strict_rate": policy_too_strict_rate,
            "negative_rate": negative_rate,
            "favorable_rate": favorable_rate,
            "train_net_score": train_net_score,
        },
        dict(sorted(counts.items())),
    )


def classify_validation_result(
    verdict: str,
    validation_atoms: Sequence[ValidationAtom],
) -> tuple[str, str, dict[str, float], dict[str, int], float]:
    counts = _outcome_counts(validation_atoms)
    validation_net_score = _avg_net_score(validation_atoms)
    policy_too_strict_rate = _rate(counts, ["POLICY_TOO_STRICT"])
    negative_rate = _rate(counts, ["CLEAN_LOSS", "BAD_EXIT"])
    favorable_rate = _rate(counts, ["GOOD_DECISION", "POLICY_PROTECTED"])

    if not validation_atoms:
        return (
            "INCONCLUSIVE",
            "no_validation_atoms",
            {
                "policy_too_strict_rate": policy_too_strict_rate,
                "negative_rate": negative_rate,
                "favorable_rate": favorable_rate,
            },
            dict(sorted(counts.items())),
            validation_net_score,
        )

    if verdict == "TOXIC_CONTEXT":
        confirmed = validation_net_score < 0 or negative_rate >= 0.50
        return (
            "CONFIRMED" if confirmed else "CONTRADICTED",
            "validation_negative_profile" if confirmed else "validation_not_negative_enough",
            {
                "policy_too_strict_rate": policy_too_strict_rate,
                "negative_rate": negative_rate,
                "favorable_rate": favorable_rate,
            },
            dict(sorted(counts.items())),
            validation_net_score,
        )
    if verdict == "FAVORABLE_CONTEXT":
        confirmed = validation_net_score > 0 or favorable_rate >= 0.50
        return (
            "CONFIRMED" if confirmed else "CONTRADICTED",
            "validation_positive_profile" if confirmed else "validation_not_positive_enough",
            {
                "policy_too_strict_rate": policy_too_strict_rate,
                "negative_rate": negative_rate,
                "favorable_rate": favorable_rate,
            },
            dict(sorted(counts.items())),
            validation_net_score,
        )
    if verdict == "POLICY_TOO_STRICT_CANDIDATE":
        confirmed = policy_too_strict_rate >= 0.50 and counts.get("POLICY_TOO_STRICT", 0) >= 1
        return (
            "CONFIRMED" if confirmed else "CONTRADICTED",
            "validation_high_missed_positive_rate" if confirmed else "validation_missing_missed_positive_pattern",
            {
                "policy_too_strict_rate": policy_too_strict_rate,
                "negative_rate": negative_rate,
                "favorable_rate": favorable_rate,
            },
            dict(sorted(counts.items())),
            validation_net_score,
        )
    if verdict == "MIXED_CONTEXT":
        strong_negative = validation_net_score < -10 or negative_rate >= 0.60
        strong_positive = validation_net_score > 10 or favorable_rate >= 0.60
        strong_policy = policy_too_strict_rate >= 0.60 and counts.get("POLICY_TOO_STRICT", 0) >= 1
        if strong_negative or strong_positive or strong_policy:
            return (
                "CONTRADICTED",
                "validation_became_directional",
                {
                    "policy_too_strict_rate": policy_too_strict_rate,
                    "negative_rate": negative_rate,
                    "favorable_rate": favorable_rate,
                },
                dict(sorted(counts.items())),
                validation_net_score,
            )
        return (
            "CONFIRMED",
            "validation_remained_inconclusive",
            {
                "policy_too_strict_rate": policy_too_strict_rate,
                "negative_rate": negative_rate,
                "favorable_rate": favorable_rate,
            },
            dict(sorted(counts.items())),
            validation_net_score,
        )
    return (
        "INCONCLUSIVE",
        "low_support_verdict_not_scored",
        {
            "policy_too_strict_rate": policy_too_strict_rate,
            "negative_rate": negative_rate,
            "favorable_rate": favorable_rate,
        },
        dict(sorted(counts.items())),
        validation_net_score,
    )


def evaluate_contexts(
    splits: Sequence[ContextSplit],
    *,
    min_train_atoms: int,
    min_validation_atoms: int,
) -> list[ContextVerdict]:
    results: list[ContextVerdict] = []
    for split in splits:
        context = dict(split.train_atoms[0].context if split.train_atoms else split.validation_atoms[0].context)
        verdict, recommendation, train_metrics, train_counts = infer_memory_verdict(split.train_atoms)
        if len(split.train_atoms) < min_train_atoms or len(split.validation_atoms) < min_validation_atoms:
            validation_result = "SKIPPED_LOW_SUPPORT"
            validation_reason = "train_or_validation_support_below_threshold"
            validation_metrics = {
                "policy_too_strict_rate": 0.0,
                "negative_rate": 0.0,
                "favorable_rate": 0.0,
            }
            validation_counts: dict[str, int] = {}
            validation_net_score = _avg_net_score(split.validation_atoms)
        else:
            (
                validation_result,
                validation_reason,
                validation_metrics,
                validation_counts,
                validation_net_score,
            ) = classify_validation_result(verdict, split.validation_atoms)
        results.append(
            ContextVerdict(
                context_key=split.context_key,
                context=context,
                train_count=len(split.train_atoms),
                validation_count=len(split.validation_atoms),
                verdict=verdict,
                recommendation=recommendation,
                train_net_score=train_metrics["train_net_score"],
                train_outcome_counts=train_counts,
                validation_net_score=validation_net_score,
                validation_outcome_counts=validation_counts,
                validation_result=validation_result,
                validation_reason=validation_reason,
                policy_too_strict_rate_train=train_metrics["policy_too_strict_rate"],
                negative_rate_train=train_metrics["negative_rate"],
                favorable_rate_train=train_metrics["favorable_rate"],
                policy_too_strict_rate_validation=validation_metrics["policy_too_strict_rate"],
                negative_rate_validation=validation_metrics["negative_rate"],
                favorable_rate_validation=validation_metrics["favorable_rate"],
            )
        )
    return results


def final_verdict(contexts_tested: int, confirmation_rate: float) -> str:
    if contexts_tested < 5:
        return "VALIDATION_INCONCLUSIVE"
    if confirmation_rate >= 0.60:
        return "VALIDATION_PASSED"
    if confirmation_rate < 0.40:
        return "VALIDATION_FAILED"
    return "VALIDATION_INCONCLUSIVE"


def build_report(
    *,
    saf_path: Path,
    poc02_report_path: Path,
    output_path: Path,
    atoms: Sequence[ValidationAtom],
    context_results: Sequence[ContextVerdict],
    final_status: str,
) -> str:
    contexts_tested = [item for item in context_results if item.validation_result in {"CONFIRMED", "CONTRADICTED"}]
    contexts_skipped = [item for item in context_results if item.validation_result == "SKIPPED_LOW_SUPPORT"]
    confirmations = [item for item in context_results if item.validation_result == "CONFIRMED"]
    contradictions = [item for item in context_results if item.validation_result == "CONTRADICTED"]
    false_positive_verdicts = [
        item for item in contradictions if item.verdict in {"TOXIC_CONTEXT", "FAVORABLE_CONTEXT", "POLICY_TOO_STRICT_CANDIDATE"}
    ]
    false_negative_verdicts = [
        item for item in contradictions if item.verdict == "MIXED_CONTEXT"
    ]
    confirmation_rate = (len(confirmations) / len(contexts_tested)) if contexts_tested else 0.0

    def _ranked(verdict_name: str, key_name: str, reverse: bool = True) -> list[ContextVerdict]:
        matched = [item for item in context_results if item.verdict == verdict_name]
        return sorted(matched, key=lambda item: getattr(item, key_name), reverse=reverse)[:5]

    top_toxic = _ranked("TOXIC_CONTEXT", "train_net_score", reverse=False)
    top_favorable = _ranked("FAVORABLE_CONTEXT", "train_net_score", reverse=True)
    top_policy = _ranked("POLICY_TOO_STRICT_CANDIDATE", "policy_too_strict_rate_train", reverse=True)

    lines = [
        "# SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT",
        "",
        "## Verdict",
        final_status,
        "",
        "## Scope",
        "- Read-only validation of POC_02 memory verdicts using only `aurora_real_logs_v02.saf.jsonl` and the POC_02 report.",
        "- No live logic, policy, gating, or enforcement changes.",
        "",
        "## Inputs Read",
        f"- {saf_path}",
        f"- {poc02_report_path}",
        "",
        "## Summary",
        f"- total atoms: {len(atoms)}",
        f"- contexts tested: {len(contexts_tested)}",
        f"- contexts skipped due to low support: {len(contexts_skipped)}",
        f"- verdict confirmation rate: {confirmation_rate:.4f}",
        f"- false positive verdicts: {len(false_positive_verdicts)}",
        f"- false negative verdicts: {len(false_negative_verdicts)}",
        "",
        "## Context Evaluation Details",
    ]
    for item in context_results:
        lines.extend(
            [
                f"- context: {item.context['symbol']} {item.context['side']} {item.context['strategy_id']} {item.context['regime']} {item.context['confidence_bucket']}",
                f"  train_count={item.train_count} validation_count={item.validation_count} verdict={item.verdict} recommendation={item.recommendation}",
                f"  train_net_score={item.train_net_score:.6f} validation_net_score={item.validation_net_score:.6f}",
                f"  train_outcomes={_json_dumps(item.train_outcome_counts)} validation_outcomes={_json_dumps(item.validation_outcome_counts)}",
                f"  validation_result={item.validation_result} reason={item.validation_reason}",
            ]
        )

    def _emit_ranked(title: str, items: Sequence[ContextVerdict], score_field: str) -> None:
        lines.extend(["", f"## {title}"])
        if not items:
            lines.append("- none")
            return
        for item in items:
            score_value = getattr(item, score_field)
            lines.append(
                f"- {item.context['symbol']} {item.context['side']} {item.context['regime']} {item.context['confidence_bucket']} "
                f"train_count={item.train_count} validation_count={item.validation_count} train_score={score_value:.6f} validation_result={item.validation_result}"
            )

    _emit_ranked("Top Toxic Candidates", top_toxic, "train_net_score")
    _emit_ranked("Top Favorable Candidates", top_favorable, "train_net_score")
    _emit_ranked("Top Policy-Too-Strict Candidates", top_policy, "policy_too_strict_rate_train")

    lines.extend(
        [
            "",
            "## False Positive Verdicts",
        ]
    )
    if false_positive_verdicts:
        for item in false_positive_verdicts:
            lines.append(
                f"- {item.context['symbol']} {item.context['side']} {item.context['regime']} {item.context['confidence_bucket']} "
                f"verdict={item.verdict} validation_result={item.validation_result} reason={item.validation_reason}"
            )
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## False Negative Verdicts",
        ]
    )
    if false_negative_verdicts:
        for item in false_negative_verdicts:
            lines.append(
                f"- {item.context['symbol']} {item.context['side']} {item.context['regime']} {item.context['confidence_bucket']} "
                f"verdict={item.verdict} validation_result={item.validation_result} reason={item.validation_reason}"
            )
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Residual Uncertainty",
            "- The SAF file is a single frozen slice, so chronological validation is within-slice only and not a fresh forward period.",
            "- Context support is sparse for many symbol/side/regime buckets, so skipped contexts materially limit confidence.",
            "- `POLICY_TOO_STRICT` evidence is strongest where the adapter already reconstructed rejected offline outcomes; missing-reference rejects remain out of scope.",
            "- `NEUTRAL_SIGNAL` rows are retained for chronology and support accounting but do not directly prove favorable or toxic predictive value.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def run_validation(
    *,
    saf_path: Path = DEFAULT_SAF_PATH,
    poc02_report_path: Path = DEFAULT_POC02_REPORT_PATH,
    output_path: Path = DEFAULT_REPORT_PATH,
    min_train_atoms: int = 2,
    min_validation_atoms: int = 1,
) -> dict[str, Any]:
    atoms = load_atoms(saf_path)
    splits = split_atoms_by_context(atoms)
    context_results = evaluate_contexts(splits, min_train_atoms=min_train_atoms, min_validation_atoms=min_validation_atoms)
    contexts_tested = [item for item in context_results if item.validation_result in {"CONFIRMED", "CONTRADICTED"}]
    confirmation_rate = (
        sum(1 for item in context_results if item.validation_result == "CONFIRMED") / len(contexts_tested)
        if contexts_tested
        else 0.0
    )
    status = final_verdict(len(contexts_tested), confirmation_rate)
    report_text = build_report(
        saf_path=saf_path,
        poc02_report_path=poc02_report_path,
        output_path=output_path,
        atoms=atoms,
        context_results=context_results,
        final_status=status,
    )
    output_path.write_text(report_text, encoding="utf-8")
    return {
        "status": status,
        "output_path": output_path,
        "total_atoms": len(atoms),
        "contexts": [asdict(item) for item in context_results],
        "confirmation_rate": confirmation_rate,
        "contexts_tested": len(contexts_tested),
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only POC_03 memory verdict validation.")
    parser.add_argument("--saf", type=Path, default=DEFAULT_SAF_PATH, help="Path to aurora_real_logs_v02.saf.jsonl")
    parser.add_argument("--poc02-report", type=Path, default=DEFAULT_POC02_REPORT_PATH, help="Path to POC_02 report")
    parser.add_argument("--output-report", type=Path, default=DEFAULT_REPORT_PATH, help="Output report path")
    parser.add_argument("--min-train-atoms", type=int, default=2, help="Minimum train atoms per tested context")
    parser.add_argument("--min-validation-atoms", type=int, default=1, help="Minimum validation atoms per tested context")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_validation(
        saf_path=args.saf,
        poc02_report_path=args.poc02_report,
        output_path=args.output_report,
        min_train_atoms=args.min_train_atoms,
        min_validation_atoms=args.min_validation_atoms,
    )
    print(f"status={result['status']}")
    print(f"report={result['output_path']}")
    print(f"total_atoms={result['total_atoms']}")
    print(f"contexts_tested={result['contexts_tested']}")
    print(f"confirmation_rate={result['confirmation_rate']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
