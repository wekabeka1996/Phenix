from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT_REPORT = REPO_ROOT / "SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT.md"
DEFAULT_OUTPUT_MANIFEST = REPO_ROOT / "SEMA_ATOM_POC_03B_CANDIDATE_MANIFEST.json"
DEFAULT_OUTPUT_REPORT = REPO_ROOT / "SEMA_ATOM_POC_03B_STABILITY_FILTER_REPORT.md"
BUCKETS = (
    "READY_FOR_COUNTERFACTUAL_SIM",
    "PROMISING_LOW_SUPPORT",
    "REJECTED_FALSE_POSITIVE",
    "INCONCLUSIVE_LOW_POWER",
    "CONFIRMED_BUT_UNSTABLE",
    "CONFIRMED_BUT_UNCLASSIFIED",
    "UNKNOWN",
)
SECTION_CONTEXT_DETAILS = "## Context Evaluation Details"
SECTION_END_MARKERS = (
    "## Top Toxic Candidates",
    "## Top Favorable Candidates",
    "## Top Policy-Too-Strict Candidates",
    "## False Positive Verdicts",
)


def _safe_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _safe_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


@dataclass(slots=True)
class ParsedContext:
    context_id: str
    symbol: str | None
    side: str | None
    strategy_id: str | None
    regime: str | None
    confidence_bucket: str | None
    train_count: int | None
    validation_count: int | None
    verdict: str | None
    recommendation: str | None
    train_net_score: float | None
    validation_net_score: float | None
    train_outcomes: dict[str, int] | None
    validation_outcomes: dict[str, int] | None
    validation_result: str | None
    validation_reason: str | None
    source_lines: list[str]


def parse_summary_counts(report_text: str) -> dict[str, int | None]:
    tested = re.search(r"^- contexts tested: (\d+)$", report_text, flags=re.M)
    skipped = re.search(r"^- contexts skipped due to low support: (\d+)$", report_text, flags=re.M)
    total = re.search(r"^- total context evaluations: (\d+)$", report_text, flags=re.M)
    tested_count = _safe_int(tested.group(1) if tested else None)
    skipped_count = _safe_int(skipped.group(1) if skipped else None)
    total_count = _safe_int(total.group(1) if total else None)
    if total_count is None and tested_count is not None and skipped_count is not None:
        total_count = tested_count + skipped_count
    return {
        "contexts_tested": tested_count,
        "contexts_skipped_low_support": skipped_count,
        "expected_contexts_total": total_count,
    }


def _extract_context_section(report_text: str) -> str:
    start = report_text.find(SECTION_CONTEXT_DETAILS)
    if start < 0:
        return ""
    section = report_text[start + len(SECTION_CONTEXT_DETAILS):]
    end_positions = [section.find(marker) for marker in SECTION_END_MARKERS if section.find(marker) >= 0]
    if end_positions:
        section = section[: min(end_positions)]
    return section.strip()


def _parse_context_line(line: str) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    payload = line[len("- context: "):].strip()
    parts = payload.split()
    if len(parts) < 5:
        return None, None, None, None, None
    return parts[0], parts[1], parts[2], parts[3], parts[4]


def _parse_counts_line(line: str) -> dict[str, Any]:
    match = re.search(
        r"train_count=(\d+)\s+validation_count=(\d+)\s+verdict=([A-Z_]+)\s+recommendation=([a-z_]+)",
        line.strip(),
    )
    if not match:
        return {}
    return {
        "train_count": _safe_int(match.group(1)),
        "validation_count": _safe_int(match.group(2)),
        "verdict": match.group(3),
        "recommendation": match.group(4),
    }


def _parse_score_line(line: str) -> dict[str, Any]:
    match = re.search(
        r"train_net_score=([-0-9.]+)\s+validation_net_score=([-0-9.]+)",
        line.strip(),
    )
    if not match:
        return {}
    return {
        "train_net_score": _safe_float(match.group(1)),
        "validation_net_score": _safe_float(match.group(2)),
    }


def _parse_outcomes_line(line: str) -> dict[str, Any]:
    match = re.search(r"train_outcomes=(\{.*?\})\s+validation_outcomes=(\{.*\})$", line.strip())
    if not match:
        return {}
    try:
        train_outcomes = json.loads(match.group(1))
        validation_outcomes = json.loads(match.group(2))
    except json.JSONDecodeError:
        return {}
    return {
        "train_outcomes": train_outcomes,
        "validation_outcomes": validation_outcomes,
    }


def _parse_validation_line(line: str) -> dict[str, Any]:
    match = re.search(r"validation_result=([A-Z_]+)\s+reason=([a-z_]+)$", line.strip())
    if not match:
        return {}
    return {
        "validation_result": match.group(1),
        "validation_reason": match.group(2),
    }


def parse_contexts(report_text: str) -> tuple[list[ParsedContext], dict[str, Any]]:
    section = _extract_context_section(report_text)
    lines = [line.rstrip() for line in section.splitlines() if line.strip()]
    contexts: list[ParsedContext] = []
    contexts_with_empty_validation_outcomes = 0
    missing_required_fields = 0
    warnings: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith("- context: "):
            warnings.append(f"ignored_non_context_line:{line}")
            i += 1
            continue
        block = lines[i:i + 4]
        source_lines = block[:]
        symbol, side, strategy_id, regime, confidence_bucket = _parse_context_line(block[0])
        count_fields = _parse_counts_line(block[1]) if len(block) > 1 else {}
        score_fields = _parse_score_line(block[2]) if len(block) > 2 else {}
        outcome_fields = _parse_outcomes_line(block[3]) if len(block) > 3 else {}
        validation_fields = _parse_validation_line(block[4]) if len(block) > 4 else {}

        # Preferred format is 5 lines per context: first line plus 4 indented lines.
        if len(lines) > i + 4 and lines[i + 4].lstrip().startswith("validation_result="):
            source_lines = lines[i:i + 5]
            validation_fields = _parse_validation_line(lines[i + 4])
            i_step = 5
        else:
            i_step = 4

        context_id = (
            f"{symbol or 'UNKNOWN'}|{side or 'UNKNOWN'}|{strategy_id or 'UNKNOWN'}|"
            f"{regime or 'UNKNOWN'}|{confidence_bucket or 'UNKNOWN'}"
        )
        parsed = ParsedContext(
            context_id=context_id,
            symbol=symbol,
            side=side,
            strategy_id=strategy_id,
            regime=regime,
            confidence_bucket=confidence_bucket,
            train_count=count_fields.get("train_count"),
            validation_count=count_fields.get("validation_count"),
            verdict=count_fields.get("verdict"),
            recommendation=count_fields.get("recommendation"),
            train_net_score=score_fields.get("train_net_score"),
            validation_net_score=score_fields.get("validation_net_score"),
            train_outcomes=outcome_fields.get("train_outcomes"),
            validation_outcomes=outcome_fields.get("validation_outcomes"),
            validation_result=validation_fields.get("validation_result"),
            validation_reason=validation_fields.get("validation_reason"),
            source_lines=source_lines,
        )
        required_values = [
            parsed.context_id,
            parsed.symbol,
            parsed.side,
            parsed.strategy_id,
            parsed.regime,
            parsed.confidence_bucket,
            parsed.train_count,
            parsed.validation_count,
            parsed.verdict,
            parsed.train_net_score,
            parsed.validation_net_score,
            parsed.train_outcomes,
            parsed.validation_outcomes,
            parsed.validation_result,
            parsed.validation_reason,
        ]
        if any(value is None for value in required_values):
            missing_required_fields += 1
        if parsed.validation_outcomes == {}:
            contexts_with_empty_validation_outcomes += 1
        contexts.append(parsed)
        i += i_step

    return contexts, {
        "parsed_contexts_total": len(contexts),
        "contexts_with_empty_validation_outcomes": contexts_with_empty_validation_outcomes,
        "missing_required_fields": missing_required_fields,
        "warnings": warnings,
    }


def apply_stability_filter(ctx: dict[str, Any]) -> str:
    res = ctx.get("validation_result")
    verdict = ctx.get("verdict")

    train_c = ctx.get("train_count", 0)
    val_c = ctx.get("validation_count", 0)

    train_score = ctx.get("train_net_score", 0.0)
    val_score = ctx.get("validation_net_score", 0.0)

    train_outcomes = ctx.get("train_outcomes", {}) or {}
    val_outcomes = ctx.get("validation_outcomes", {}) or {}

    if res == "SKIPPED_LOW_SUPPORT":
        return "INCONCLUSIVE_LOW_POWER"

    if res == "CONTRADICTED":
        return "REJECTED_FALSE_POSITIVE"

    if res != "CONFIRMED":
        return "UNKNOWN"

    enough_support = train_c >= 5 and val_c >= 5

    if not enough_support:
        return "PROMISING_LOW_SUPPORT"

    if verdict == "TOXIC_CONTEXT":
        if train_score < 0 and val_score < 0:
            return "READY_FOR_COUNTERFACTUAL_SIM"
        return "CONFIRMED_BUT_UNSTABLE"

    if verdict == "FAVORABLE_CONTEXT":
        if train_score >= 0 and val_score >= 0:
            return "READY_FOR_COUNTERFACTUAL_SIM"
        return "CONFIRMED_BUT_UNSTABLE"

    if verdict == "POLICY_TOO_STRICT_CANDIDATE":
        train_pts = train_outcomes.get("POLICY_TOO_STRICT", 0)
        train_protected = train_outcomes.get("POLICY_PROTECTED", 0)
        val_pts = val_outcomes.get("POLICY_TOO_STRICT", 0)
        val_protected = val_outcomes.get("POLICY_PROTECTED", 0)

        train_total = train_pts + train_protected
        val_total = val_pts + val_protected

        if train_total == 0 or val_total == 0:
            return "CONFIRMED_BUT_UNSTABLE"

        train_rate = train_pts / train_total
        val_rate = val_pts / val_total

        if train_rate >= 0.60 and val_rate >= 0.50:
            return "READY_FOR_COUNTERFACTUAL_SIM"

        return "CONFIRMED_BUT_UNSTABLE"

    return "CONFIRMED_BUT_UNCLASSIFIED"


def build_manifest(contexts: Sequence[ParsedContext]) -> dict[str, list[dict[str, Any]]]:
    manifest: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in BUCKETS}
    for ctx in contexts:
        record = asdict(ctx)
        bucket = apply_stability_filter(record)
        manifest[bucket].append(record)
    return manifest


def _manifest_total_contexts(manifest: dict[str, list[dict[str, Any]]]) -> int:
    return sum(len(items) for items in manifest.values())


def determine_status(
    *,
    expected_contexts_total: int | None,
    parsed_contexts_total: int,
    manifest_total_contexts: int,
    missing_required_fields: int,
    warnings: Sequence[str],
) -> str:
    if expected_contexts_total is not None and parsed_contexts_total != expected_contexts_total:
        return "FAILED_CONTEXT_PARSE_COUNT_MISMATCH"
    if missing_required_fields != 0:
        return "FAILED_REQUIRED_FIELD_PARSE"
    if manifest_total_contexts != parsed_contexts_total:
        return "FAILED_MANIFEST_CONTEXT_COUNT_MISMATCH"
    if warnings:
        return "COMPLETED_WITH_PARSE_WARNINGS"
    return "COMPLETED"


def build_report(
    *,
    input_path: Path,
    output_manifest_path: Path,
    parser_summary: dict[str, Any],
    summary_counts: dict[str, Any],
    manifest: dict[str, list[dict[str, Any]]],
    status: str,
) -> str:
    manifest_total = _manifest_total_contexts(manifest)
    lines = [
        "# SEMA_ATOM_POC_03B_STABILITY_FILTER_REPORT",
        "",
        "## Verdict",
        "SEMA_ATOM_POC_03B_STATUS:",
        status,
        "",
        "## Scope",
        "- Read-only artifact-driven stability filter between POC_03 validation and POC_04 counterfactual simulation.",
        "- No live logic, YAML policy, gates, enforcement, or PnL simulation.",
        "",
        "## Inputs Read",
        f"- {input_path}",
        "",
        "## Parser Validation",
        f"- parsed_contexts_total: {parser_summary['parsed_contexts_total']}",
        f"- expected_contexts_total: {summary_counts.get('expected_contexts_total')}",
        f"- missing_required_fields: {parser_summary['missing_required_fields']}",
        f"- contexts_with_empty_validation_outcomes: {parser_summary['contexts_with_empty_validation_outcomes']}",
        "",
        "## Manifest Summary",
        f"- READY_FOR_COUNTERFACTUAL_SIM count: {len(manifest['READY_FOR_COUNTERFACTUAL_SIM'])}",
        f"- PROMISING_LOW_SUPPORT count: {len(manifest['PROMISING_LOW_SUPPORT'])}",
        f"- REJECTED_FALSE_POSITIVE count: {len(manifest['REJECTED_FALSE_POSITIVE'])}",
        f"- INCONCLUSIVE_LOW_POWER count: {len(manifest['INCONCLUSIVE_LOW_POWER'])}",
        f"- CONFIRMED_BUT_UNSTABLE count: {len(manifest['CONFIRMED_BUT_UNSTABLE'])}",
        f"- CONFIRMED_BUT_UNCLASSIFIED count: {len(manifest['CONFIRMED_BUT_UNCLASSIFIED'])}",
        f"- UNKNOWN count: {len(manifest['UNKNOWN'])}",
        f"- manifest_total_contexts: {manifest_total}",
        "",
        "## READY_FOR_COUNTERFACTUAL_SIM",
    ]
    if manifest["READY_FOR_COUNTERFACTUAL_SIM"]:
        for item in manifest["READY_FOR_COUNTERFACTUAL_SIM"]:
            lines.append(
                f"- {item['context_id']} verdict={item['verdict']} train_count={item['train_count']} "
                f"validation_count={item['validation_count']} train_net_score={item['train_net_score']} "
                f"validation_net_score={item['validation_net_score']}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## PROMISING_LOW_SUPPORT"])
    if manifest["PROMISING_LOW_SUPPORT"]:
        for item in manifest["PROMISING_LOW_SUPPORT"]:
            lines.append(
                f"- {item['context_id']} verdict={item['verdict']} validation_result={item['validation_result']} "
                f"train_count={item['train_count']} validation_count={item['validation_count']}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## REJECTED_FALSE_POSITIVE"])
    if manifest["REJECTED_FALSE_POSITIVE"]:
        for item in manifest["REJECTED_FALSE_POSITIVE"]:
            lines.append(
                f"- {item['context_id']} verdict={item['verdict']} validation_reason={item['validation_reason']}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## INCONCLUSIVE_LOW_POWER"])
    if manifest["INCONCLUSIVE_LOW_POWER"]:
        for item in manifest["INCONCLUSIVE_LOW_POWER"]:
            lines.append(
                f"- {item['context_id']} verdict={item['verdict']} train_count={item['train_count']} validation_count={item['validation_count']}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## OTHER BUCKETS"])
    for bucket in ("CONFIRMED_BUT_UNSTABLE", "CONFIRMED_BUT_UNCLASSIFIED", "UNKNOWN"):
        lines.append(f"- {bucket}: {len(manifest[bucket])}")
        for item in manifest[bucket]:
            lines.append(
                f"  {item['context_id']} verdict={item['verdict']} validation_result={item['validation_result']}"
            )

    lines.extend(
        [
            "",
            "## Residual Risks",
            "- Markdown parsing remains format-sensitive to the POC_03 report layout, so any future report-shape drift should be treated as a parser contract change.",
            "- `contexts_with_empty_validation_outcomes` is expected for skipped low-support contexts and is not itself a failure.",
            "- `READY_FOR_COUNTERFACTUAL_SIM` remains a candidate gate only; POC_03B does not simulate PnL or alter policy.",
            "",
            "## Next Recommended Step",
            "- SEMA_ATOM_POC_04_COUNTERFACTUAL_POLICY_IMPACT_SIMULATION",
            f"- Use only contexts from `{output_manifest_path.name}` bucket `READY_FOR_COUNTERFACTUAL_SIM`.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def run(
    *,
    input_report: Path = DEFAULT_INPUT_REPORT,
    output_manifest: Path = DEFAULT_OUTPUT_MANIFEST,
    output_report: Path = DEFAULT_OUTPUT_REPORT,
) -> dict[str, Any]:
    report_text = input_report.read_text(encoding="utf-8")
    summary_counts = parse_summary_counts(report_text)
    contexts, parser_summary = parse_contexts(report_text)
    manifest = build_manifest(contexts)
    manifest_total = _manifest_total_contexts(manifest)
    status = determine_status(
        expected_contexts_total=summary_counts.get("expected_contexts_total"),
        parsed_contexts_total=parser_summary["parsed_contexts_total"],
        manifest_total_contexts=manifest_total,
        missing_required_fields=parser_summary["missing_required_fields"],
        warnings=parser_summary["warnings"],
    )
    output_manifest.write_text(_json_dumps(manifest) + "\n", encoding="utf-8")
    report_md = build_report(
        input_path=input_report,
        output_manifest_path=output_manifest,
        parser_summary=parser_summary,
        summary_counts=summary_counts,
        manifest=manifest,
        status=status,
    )
    output_report.write_text(report_md, encoding="utf-8")
    return {
        "status": status,
        "summary_counts": summary_counts,
        "parser_summary": parser_summary,
        "manifest_total_contexts": manifest_total,
        "manifest": manifest,
        "output_manifest": output_manifest,
        "output_report": output_report,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Artifact-driven POC_03B stability filter.")
    parser.add_argument("--input-report", type=Path, default=DEFAULT_INPUT_REPORT)
    parser.add_argument("--output-manifest", type=Path, default=DEFAULT_OUTPUT_MANIFEST)
    parser.add_argument("--output-report", type=Path, default=DEFAULT_OUTPUT_REPORT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run(
        input_report=args.input_report,
        output_manifest=args.output_manifest,
        output_report=args.output_report,
    )
    print(f"status={result['status']}")
    print(f"parsed_contexts_total={result['parser_summary']['parsed_contexts_total']}")
    print(f"expected_contexts_total={result['summary_counts'].get('expected_contexts_total')}")
    print(f"manifest_total_contexts={result['manifest_total_contexts']}")
    print(f"missing_required_fields={result['parser_summary']['missing_required_fields']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
