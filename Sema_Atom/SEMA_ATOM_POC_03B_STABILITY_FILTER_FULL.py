from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION as poc03


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT_SIDECAR = REPO_ROOT / "SEMA_ATOM_POC_03_EVALUATION_SIDECAR_V01.json"
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
PRIMARY_READY_SUPPORT_QUALITIES = {"SUFFICIENT", "STRONG"}
CANONICAL_OUTCOME_CODES = set(poc03.CANONICAL_OUTCOME_CODES)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def _empty_manifest() -> dict[str, list[dict[str, Any]]]:
    return {bucket: [] for bucket in BUCKETS}


def _manifest_total_contexts(manifest: dict[str, list[dict[str, Any]]]) -> int:
    return sum(len(items) for items in manifest.values())


def load_sidecar(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_sidecar_contract(sidecar: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    try:
        poc03.validate_sidecar_payload(sidecar)
    except ValueError as exc:
        errors.append(f"schema_validation:{exc}")

    schema_id = sidecar.get("schema_id")
    schema_version = sidecar.get("schema_version")
    reported_contexts_total = sidecar.get("contexts_total")
    contexts = sidecar.get("contexts")
    if not isinstance(contexts, list):
        errors.append("contexts:not_array")
        contexts = []

    if schema_id != poc03.SIDECAR_SCHEMA_ID:
        errors.append(f"schema_id_mismatch:{schema_id}")
    if schema_version != poc03.SIDECAR_SCHEMA_VERSION:
        errors.append(f"schema_version_mismatch:{schema_version}")
    if reported_contexts_total != len(contexts):
        errors.append(
            f"contexts_total_mismatch:{reported_contexts_total}!={len(contexts)}")

    seen_context_keys: set[str] = set()
    for index, context in enumerate(contexts):
        if not isinstance(context, dict):
            errors.append(f"contexts[{index}]:not_object")
            continue
        context_key = str(context.get("context_key") or "")
        symbol = str(context.get("symbol") or "")
        side = str(context.get("side") or "")
        strategy_id = str(context.get("strategy_id") or "")
        regime = str(context.get("regime") or "")
        confidence_bucket = str(context.get("confidence_bucket") or "")
        expected_context_key = "|".join(
            (symbol, side, strategy_id, regime, confidence_bucket))

        if not strategy_id:
            errors.append(f"contexts[{index}]:missing_strategy_id")
        if context_key != expected_context_key:
            errors.append(
                f"contexts[{index}]:context_key_mismatch:{context_key}!={expected_context_key}")
        if context_key in seen_context_keys:
            errors.append(
                f"contexts[{index}]:duplicate_context_key:{context_key}")
        seen_context_keys.add(context_key)

        for block_name in ("train_outcomes", "validation_outcomes"):
            outcomes = context.get(block_name) or {}
            if not isinstance(outcomes, dict):
                errors.append(f"contexts[{index}]:{block_name}:not_object")
                continue
            unknown_labels = sorted(set(outcomes) - CANONICAL_OUTCOME_CODES)
            if unknown_labels:
                errors.append(
                    f"contexts[{index}]:{block_name}:non_canonical:{','.join(unknown_labels)}")

    return {
        "ok": not errors,
        "schema_id": schema_id,
        "schema_version": schema_version,
        "reported_contexts_total": reported_contexts_total,
        "parsed_contexts_total": len(contexts),
        "unique_context_keys": len(seen_context_keys),
        "errors": errors,
    }


def apply_stability_filter(ctx: dict[str, Any]) -> str:
    validation_result = ctx.get("validation_result")
    verdict = ctx.get("verdict")
    support_quality = ctx.get("support_quality")
    low_power_reason = ctx.get("low_power_reason")

    train_count = ctx.get("train_count", 0)
    validation_count = ctx.get("validation_count", 0)
    train_score = ctx.get("train_net_score", 0.0)
    validation_score = ctx.get("validation_net_score", 0.0)

    train_outcomes = ctx.get("train_outcomes", {}) or {}
    validation_outcomes = ctx.get("validation_outcomes", {}) or {}

    if validation_result == "SKIPPED_LOW_SUPPORT":
        return "INCONCLUSIVE_LOW_POWER"

    if validation_result == "CONTRADICTED":
        return "REJECTED_FALSE_POSITIVE"

    if validation_result != "CONFIRMED":
        return "INCONCLUSIVE_LOW_POWER" if low_power_reason not in {None, "NONE"} else "UNKNOWN"

    if support_quality == "INSUFFICIENT":
        return "INCONCLUSIVE_LOW_POWER"

    if support_quality == "BORDERLINE":
        return "PROMISING_LOW_SUPPORT"

    if support_quality not in PRIMARY_READY_SUPPORT_QUALITIES:
        return "UNKNOWN"

    if verdict == "TOXIC_CONTEXT":
        if train_score < 0 and validation_score < 0:
            return "READY_FOR_COUNTERFACTUAL_SIM"
        return "CONFIRMED_BUT_UNSTABLE"

    if verdict == "FAVORABLE_CONTEXT":
        if train_score >= 0 and validation_score >= 0:
            return "READY_FOR_COUNTERFACTUAL_SIM"
        return "CONFIRMED_BUT_UNSTABLE"

    if verdict == "POLICY_TOO_STRICT_CANDIDATE":
        train_pts = train_outcomes.get("POLICY_TOO_STRICT", 0)
        train_protected = train_outcomes.get("POLICY_PROTECTED", 0)
        validation_pts = validation_outcomes.get("POLICY_TOO_STRICT", 0)
        validation_protected = validation_outcomes.get("POLICY_PROTECTED", 0)

        train_total = train_pts + train_protected
        validation_total = validation_pts + validation_protected
        if train_total == 0 or validation_total == 0:
            return "CONFIRMED_BUT_UNSTABLE"

        train_rate = train_pts / train_total
        validation_rate = validation_pts / validation_total
        if train_rate >= 0.60 and validation_rate >= 0.50:
            return "READY_FOR_COUNTERFACTUAL_SIM"
        return "CONFIRMED_BUT_UNSTABLE"

    if isinstance(train_count, int) and isinstance(validation_count, int) and train_count >= 5 and validation_count >= 5:
        return "CONFIRMED_BUT_UNCLASSIFIED"
    return "UNKNOWN"


def build_manifest(contexts: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    manifest = _empty_manifest()
    for context in contexts:
        record = dict(context)
        record["context_id"] = record["context_key"]
        bucket = apply_stability_filter(record)
        manifest[bucket].append(record)
    return manifest


def determine_status(*, sidecar_validation: dict[str, Any], manifest_total_contexts: int) -> str:
    if not sidecar_validation["ok"]:
        return "FAILED_SIDECAR_SCHEMA_VALIDATION"
    if manifest_total_contexts != sidecar_validation["parsed_contexts_total"]:
        return "FAILED_MANIFEST_CONTEXT_COUNT_MISMATCH"
    return "COMPLETED"


def build_report(
    *,
    input_sidecar_path: Path,
    output_manifest_path: Path,
    sidecar_validation: dict[str, Any],
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
        "- Read-only JSON-sidecar-driven stability filter between POC_03 validation and POC_04 counterfactual simulation.",
        "- Markdown is human-readable only and is not used as transport.",
        "- No live logic, YAML policy, gates, enforcement, or PnL simulation.",
        "",
        "## Inputs Read",
        f"- {input_sidecar_path}",
        "",
        "## Sidecar Validation",
        f"- schema_id: {sidecar_validation.get('schema_id')}",
        f"- schema_version: {sidecar_validation.get('schema_version')}",
        f"- reported_contexts_total: {sidecar_validation.get('reported_contexts_total')}",
        f"- parsed_contexts_total: {sidecar_validation.get('parsed_contexts_total')}",
        f"- unique_context_keys: {sidecar_validation.get('unique_context_keys')}",
        f"- validation_error_count: {len(sidecar_validation.get('errors', []))}",
    ]
    if sidecar_validation.get("errors"):
        lines.extend(["", "## Validation Errors"])
        for error in sidecar_validation["errors"]:
            lines.append(f"- {error}")

    lines.extend(
        [
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
    )
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
                f"- {item['context_id']} verdict={item['verdict']} support_quality={item['support_quality']} "
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
                f"- {item['context_id']} verdict={item['verdict']} low_power_reason={item['low_power_reason']}"
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
            "- POC_03B now fails closed when the JSON sidecar is missing or violates the schema contract.",
            "- `BORDERLINE` support never promotes a context into `READY_FOR_COUNTERFACTUAL_SIM`.",
            "- `READY_FOR_COUNTERFACTUAL_SIM` remains a candidate gate only; POC_03B does not simulate PnL or alter policy.",
            "",
            "## Next Recommended Step",
            "- SEMA_ATOM_REFERENCE_PRICE_RECOVERY_POLICY_V01",
            f"- Preserve `{output_manifest_path.name}` as the only POC_03B candidate transport for downstream consumers.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def run(
    *,
    input_sidecar: Path = DEFAULT_INPUT_SIDECAR,
    output_manifest: Path = DEFAULT_OUTPUT_MANIFEST,
    output_report: Path = DEFAULT_OUTPUT_REPORT,
) -> dict[str, Any]:
    manifest = _empty_manifest()
    sidecar_validation = {
        "ok": False,
        "schema_id": None,
        "schema_version": None,
        "reported_contexts_total": None,
        "parsed_contexts_total": 0,
        "unique_context_keys": 0,
        "errors": [],
    }

    try:
        sidecar = load_sidecar(input_sidecar)
    except FileNotFoundError:
        sidecar_validation["errors"] = [
            f"missing_input_sidecar:{input_sidecar}"]
        status = "FAILED_SIDECAR_SCHEMA_VALIDATION"
    except json.JSONDecodeError as exc:
        sidecar_validation["errors"] = [f"invalid_json:{exc.msg}"]
        status = "FAILED_SIDECAR_SCHEMA_VALIDATION"
    else:
        sidecar_validation = validate_sidecar_contract(sidecar)
        if sidecar_validation["ok"]:
            manifest = build_manifest(sidecar.get("contexts") or [])
        status = determine_status(
            sidecar_validation=sidecar_validation,
            manifest_total_contexts=_manifest_total_contexts(manifest),
        )

    output_manifest.write_text(_json_dumps(manifest) + "\n", encoding="utf-8")
    report_md = build_report(
        input_sidecar_path=input_sidecar,
        output_manifest_path=output_manifest,
        sidecar_validation=sidecar_validation,
        manifest=manifest,
        status=status,
    )
    output_report.write_text(report_md, encoding="utf-8")
    return {
        "status": status,
        "sidecar_validation": sidecar_validation,
        "manifest_total_contexts": _manifest_total_contexts(manifest),
        "manifest": manifest,
        "output_manifest": output_manifest,
        "output_report": output_report,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Artifact-driven POC_03B stability filter.")
    parser.add_argument("--input-sidecar", type=Path,
                        default=DEFAULT_INPUT_SIDECAR)
    parser.add_argument("--output-manifest", type=Path,
                        default=DEFAULT_OUTPUT_MANIFEST)
    parser.add_argument("--output-report", type=Path,
                        default=DEFAULT_OUTPUT_REPORT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run(
        input_sidecar=args.input_sidecar,
        output_manifest=args.output_manifest,
        output_report=args.output_report,
    )
    print(f"status={result['status']}")
    print(
        f"parsed_contexts_total={result['sidecar_validation']['parsed_contexts_total']}")
    print(
        f"reported_contexts_total={result['sidecar_validation']['reported_contexts_total']}")
    print(f"manifest_total_contexts={result['manifest_total_contexts']}")
    print(
        f"validation_error_count={len(result['sidecar_validation']['errors'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
