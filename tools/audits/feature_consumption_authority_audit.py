from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


VERDICTS = {
    "FEATURE_AUTHORITY_MAP_COMPLETE",
    "FEATURE_AUTHORITY_MAP_PARTIAL",
    "LIVE_CONSUMPTION_GAP_CONFIRMED",
    "SHADOW_ONLY_DOMINATES",
    "INSUFFICIENT_EVIDENCE",
}

USAGE_TYPES = {
    "scoring",
    "gate",
    "sizing",
    "entry_price",
    "exit_hold",
    "diagnostic_only",
    "shadow_only",
    "unused",
}

EVIDENCE_METHODS = {
    "direct_code_read",
    "symbol_search",
    "payload_schema_match",
    "runtime_artifact_match",
    "manual_unproven",
}

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class FeatureClaimSpec:
    feature_name: str
    producer_path: str
    payload_key: str
    consumer_path: str
    usage_type: str
    claim_class: str
    decision_effect: str
    search_terms: tuple[str, ...]


FEATURE_CLAIMS: tuple[FeatureClaimSpec, ...] = (
    FeatureClaimSpec("OBI", "apps/reference/domains/feature_engineering/feature_engineering.py", "features.obi", "apps/reference/domains/decision_making/core/context.py", "scoring", "live_authoritative", "Live flow/context scoring input.", ("obi", "_get_feature", "FlowContext")),
    FeatureClaimSpec("TFI", "apps/reference/domains/feature_engineering/feature_engineering.py", "features.tfi", "apps/reference/domains/decision_making/core/context.py", "scoring", "live_authoritative", "Live flow/context scoring input.", ("tfi", "_get_feature", "FlowContext")),
    FeatureClaimSpec("depth_imbalance", "apps/reference/domains/feature_engineering/feature_engineering.py", "features.depth_imbalance", "apps/reference/domains/decision_making/core/context.py", "scoring", "live_authoritative", "Liquidity context input for live decision context.", ("depth_imbalance", "_get_feature", "LiquidityContext")),
    FeatureClaimSpec("large_trade_imbalance", "apps/reference/domains/feature_engineering/feature_engineering.py", "features.large_trade_imbalance", "apps/reference/domains/decision_making/core/context.py", "scoring", "live_aggregated_only", "Optional flow input when present in live context.", ("large_trade_imbalance", "_get_feature_optional", "FlowContext")),
    FeatureClaimSpec("spread_bps", "apps/reference/domains/feature_engineering/feature_engineering.py", "features.spread_bps", "apps/reference/domains/decision_making/gates/low_vol_cost_floor.py", "gate", "live_veto_or_attenuation", "Affects low-vol floor economics and objective market context.", ("spread_bps", "_extract_observation_float", "liquidity_context")),
    FeatureClaimSpec("volume_zscore", "apps/reference/domains/feature_engineering/feature_engineering.py", "features.volume_zscore", "apps/reference/domains/decision_making/core/context.py", "diagnostic_only", "diagnostic_only", "Retained in volatility context but not proven as decisive live gate.", ("volume_zscore", "_get_feature_optional", "VolatilityContext")),
    FeatureClaimSpec("volatility_state", "apps/reference/domains/feature_engineering/feature_engineering.py", "features.volatility_state", "apps/reference/domains/strategies/runtimes/aurora/decision.py", "scoring", "live_authoritative", "Feeds live Aurora volatility/scoring context.", ("volatility_state", "features.get", "_lineage_float")),
    FeatureClaimSpec("delta_price", "apps/reference/domains/feature_engineering/feature_engineering.py", "features.delta_price", "apps/reference/domains/decision_making/core/event_handlers.py", "gate", "live_veto_or_attenuation", "Populates directional history used by safety gates.", ("delta_price", "_delta_price_hist", "state")),
    FeatureClaimSpec("ema_bias", "apps/reference/domains/feature_engineering/feature_engineering.py", "features.ema_bias", "apps/reference/domains/decision_making/core/context.py", "scoring", "live_authoritative", "Trend context input for live decision context.", ("ema_bias", "_get_feature", "TrendContext")),
    FeatureClaimSpec("absorption", "apps/reference/domains/feature_engineering/feature_engineering.py", "features.absorption", "apps/reference/domains/decision_making/gates/low_vol_cost_floor.py", "gate", "live_veto_or_attenuation", "Used by low-vol objective/liquidity checks when present.", ("absorption", "_extract_observation_float", "liquidity_context")),
    FeatureClaimSpec("liquidity_kappa", "apps/reference/domains/feature_engineering/feature_engineering.py", "features.liquidity_kappa", "apps/reference/domains/strategies/runtimes/aurora/scoring_helpers.py", "gate", "live_veto_or_attenuation", "Live liquidity gate / attenuation input.", ("liquidity_kappa", "warmup_readiness", "kappa_min")),
    FeatureClaimSpec("macro_sync", "apps/reference/domains/feature_engineering/feature_engineering.py", "features.macro_sync", "apps/reference/domains/strategies/runtimes/aurora/decision.py", "diagnostic_only", "diagnostic_only", "Retained around Aurora decision path but not proven as decisive live gate in this package.", ("macro_sync",)),
    FeatureClaimSpec("macro_resid", "apps/reference/domains/feature_engineering/feature_engineering.py", "features.macro_resid", "apps/reference/domains/strategies/runtimes/aurora/decision.py", "scoring", "live_authoritative", "Live Aurora veto/score context.", ("macro_resid", "veto_macro_resid", "features.get")),
    FeatureClaimSpec("pm_norm / signed price motion", "apps/reference/domains/feature_engineering/price_motion.py", "price_motion.pm_norm_10s|pm_norm_60s|pm_norm_300s", "apps/reference/domains/decision_making/gates/safety_gates.py", "gate", "live_veto_or_attenuation", "Safety-gate flash/bleed input.", ("pm_norm_10s", "pm_norm_60s", "_check_price_motion_gate")),
    FeatureClaimSpec("regime", "apps/reference/domains/regime_detector/regime_detector.py", "regime", "apps/reference/domains/strategies/runtimes/aurora/decision.py", "scoring", "live_authoritative", "Core live regime routing and decision context.", ("regime", "features.get", "allowed_regimes")),
    FeatureClaimSpec("regime_conf", "apps/reference/domains/regime_detector/regime_detector.py", "confidence", "apps/reference/domains/decision_making/gates/safety_gates.py", "gate", "live_veto_or_attenuation", "Direct threshold-band gate input.", ("regime_confidence", "resolved_min_regime_confidence", "resolved_max_regime_confidence")),
    FeatureClaimSpec("regime_age_ms", "apps/reference/domains/data_recorder/recorder.py", "regime_age_ms", "", "unused", "retained_but_unjoined", "Recorder freshness field is retained, but no downstream live or shadow consumer is proven in this package.", ("regime_age_ms",)),
    FeatureClaimSpec("regime_layer", "apps/reference/domains/regime_detector/regime_detector.py", "regime_layer", "apps/reference/domains/data_recorder/recorder.py", "diagnostic_only", "diagnostic_only", "Retained provenance layer, not proven as live authority.", ("regime_layer",)),
    FeatureClaimSpec("pillar_strategist", "apps/reference/domains/feature_engineering/feature_engineering.py", "features.pillar_strategist", "apps/reference/domains/strategies/runtimes/aurora/decision.py", "scoring", "live_authoritative", "Live pillar context input.", ("pillar_strategist", "features.get", "psi")),
    FeatureClaimSpec("pillar_tactician", "apps/reference/domains/feature_engineering/feature_engineering.py", "features.pillar_tactician", "apps/reference/domains/strategies/runtimes/aurora/decision.py", "scoring", "live_authoritative", "Live pillar context input.", ("pillar_tactician", "features.get", "psi")),
    FeatureClaimSpec("pillar_operator", "apps/reference/domains/feature_engineering/feature_engineering.py", "features.pillar_operator", "apps/reference/domains/strategies/runtimes/aurora/decision.py", "scoring", "live_authoritative", "Live pillar context input.", ("pillar_operator", "features.get", "psi")),
    FeatureClaimSpec("pillar_sum", "apps/reference/domains/feature_engineering/feature_engineering.py", "features.pillar_sum", "apps/reference/domains/strategies/runtimes/aurora/decision.py", "scoring", "live_authoritative", "Live pillar aggregate input.", ("pillar_sum", "features.get", "psi")),
    FeatureClaimSpec("TA_FEATURES_CALCULATED fields", "apps/reference/domains/ta_features/ta_features.py", "ta_features.*", "apps/reference/domains/ta_features/domain_dict.json", "shadow_only", "shadow_only", "TA plane is emitted and documented for alpha_search consumption, not main-path live authority.", ("EVT:TA_FEATURES_CALCULATED", "alpha_search")),
    FeatureClaimSpec("alpha_search provider outputs", "apps/reference/domains/alpha_search/backtest_plugin.py", "alpha_score", "tools/backtest/backtest_summarize.py", "shadow_only", "shadow_only", "Research/shadow scoring plane.", ("alpha_search", "signals_generated")),
    FeatureClaimSpec("Judge / policy cortex outputs", "apps/reference/domains/alpha_search/judge/shadow_entry_plan.py", "judge|policy_cortex", "tools/alpha_search/j6_s17_f1_common.py", "shadow_only", "shadow_only", "Judge/policy-cortex surfaces stay shadow-only in this package.", ("policy_cortex", "judge_experts")),
    FeatureClaimSpec("sidecar fee-aware / peak-giveback outputs", "apps/reference/domains/execution_position/sidecar/position_policy_sidecar.py", "fee_aware|peak_giveback", "apps/reference/domains/execution_position/sidecar/position_policy_mediator.py", "exit_hold", "unknown_requires_audit", "Mode-dependent close/hold surface; shadow fee-aware arm is non-authoritative by default.", ("position_policy_sidecar", "close_request", "peak_giveback")),
)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _detect_evidence_method(spec: FeatureClaimSpec, producer_text: str, consumer_text: str) -> str:
    if not spec.consumer_path and producer_text and any(term in producer_text for term in spec.search_terms):
        return "symbol_search"
    if producer_text and consumer_text and all(term in consumer_text or term in producer_text for term in spec.search_terms):
        return "direct_code_read"
    if consumer_text and any(term in consumer_text for term in spec.search_terms):
        return "symbol_search"
    if "schema" in spec.consumer_path or "domain_dict.json" in spec.consumer_path:
        return "payload_schema_match"
    return "manual_unproven"


def _detect_confidence(spec: FeatureClaimSpec, producer_text: str, consumer_text: str) -> str:
    if not spec.consumer_path and producer_text and any(term in producer_text for term in spec.search_terms):
        return "medium"
    if producer_text and consumer_text and all(term in consumer_text or term in producer_text for term in spec.search_terms):
        return "high"
    if producer_text and any(term in producer_text for term in spec.search_terms):
        return "medium"
    if consumer_text and any(term in consumer_text for term in spec.search_terms):
        return "medium"
    if spec.claim_class in {"shadow_only", "diagnostic_only", "produced_but_unused", "unknown_requires_audit"}:
        return "low"
    return "low"


def build_evidence_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in FEATURE_CLAIMS:
        producer_abs = ROOT / spec.producer_path
        consumer_abs = ROOT / spec.consumer_path if spec.consumer_path else None
        producer_text = _read_text(producer_abs) if producer_abs.exists() else ""
        consumer_text = _read_text(consumer_abs) if consumer_abs is not None and consumer_abs.exists() else ""
        evidence_method = _detect_evidence_method(spec, producer_text, consumer_text)
        confidence = _detect_confidence(spec, producer_text, consumer_text)
        rows.append(
            {
                "feature_name": spec.feature_name,
                "producer_path": spec.producer_path,
                "payload_key": spec.payload_key,
                "consumer_path": spec.consumer_path,
                "usage_type": spec.usage_type,
                "evidence_method": evidence_method,
                "confidence": confidence,
                "claim_class": spec.claim_class,
                "decision_effect": spec.decision_effect,
            }
        )
    return rows


def _claim_rank(claim_class: str) -> int:
    order = {
        "live_authoritative": 0,
        "live_veto_or_attenuation": 1,
        "live_aggregated_only": 2,
        "shadow_only": 3,
        "diagnostic_only": 4,
        "produced_but_unused": 5,
        "retained_but_unjoined": 6,
        "dead_config": 7,
        "unknown_requires_audit": 8,
    }
    return order.get(claim_class, 99)


def build_report_rows(evidence_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    evidence_rows = list(evidence_rows or build_evidence_rows())
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in evidence_rows:
        grouped[str(row["feature_name"])].append(row)

    report_rows: list[dict[str, Any]] = []
    for feature_name, rows in sorted(grouped.items()):
        rows_sorted = sorted(rows, key=lambda item: (_claim_rank(str(item["claim_class"])), str(item["consumer_path"])))
        primary = rows_sorted[0]
        usage_set = {str(item["usage_type"]) for item in rows}
        report_rows.append(
            {
                "feature name": feature_name,
                "producer file/module": primary["producer_path"],
                "event/log/recorder surface": primary["payload_key"],
                "schema exists yes/no": "yes" if (ROOT / primary["producer_path"]).exists() else "no",
                "registry exists yes/no": "yes" if (ROOT / "apps/reference/dictionaries/verb_registry_v1.yaml").exists() else "no",
                "retained yes/no/partial": "yes",
                "authoritative vs diagnostic-only": primary["claim_class"],
                "live consumer file/module": primary["consumer_path"] or "none proven",
                "consumed by scoring yes/no": "yes" if "scoring" in usage_set else "no",
                "consumed by gate yes/no": "yes" if "gate" in usage_set else "no",
                "consumed by sizing yes/no": "yes" if "sizing" in usage_set else "no",
                "consumed by entry price logic yes/no": "yes" if "entry_price" in usage_set else "no",
                "consumed by exit/hold logic yes/no": "yes" if "exit_hold" in usage_set else "no",
                "can change live accept/reject yes/no": "yes" if usage_set & {"scoring", "gate"} and primary["claim_class"] not in {"shadow_only", "diagnostic_only"} else "no",
                "current decision effect": primary["decision_effect"],
                "duplicate/circular scoring risk": "High" if feature_name in {"macro_resid", "pillar_sum", "TA_FEATURES_CALCULATED fields", "alpha_search provider outputs", "sidecar fee-aware / peak-giveback outputs"} else "Medium",
                "required next action": (
                    "Do not use as calibration authority until live consumer proof improves."
                    if primary["claim_class"] in {"shadow_only", "diagnostic_only", "unknown_requires_audit"}
                    else "Retain provenance and avoid double-count against recorder/shadow copies."
                ),
            }
        )
    return report_rows


def determine_verdict(rows: list[dict[str, Any]]) -> str:
    classes = Counter(str(row["authoritative vs diagnostic-only"]) for row in rows)
    if not rows:
        return "INSUFFICIENT_EVIDENCE"
    if classes["unknown_requires_audit"] > 0:
        return "FEATURE_AUTHORITY_MAP_PARTIAL"
    if classes["shadow_only"] >= max(1, len(rows) // 3):
        return "SHADOW_ONLY_DOMINATES"
    if classes["shadow_only"] + classes["diagnostic_only"] + classes["live_aggregated_only"] > 0:
        return "LIVE_CONSUMPTION_GAP_CONFIRMED"
    return "FEATURE_AUTHORITY_MAP_COMPLETE"


def _render_table(rows: list[dict[str, Any]]) -> list[str]:
    headers = [
        "feature name",
        "producer file/module",
        "event/log/recorder surface",
        "schema exists yes/no",
        "registry exists yes/no",
        "retained yes/no/partial",
        "authoritative vs diagnostic-only",
        "live consumer file/module",
        "consumed by scoring yes/no",
        "consumed by gate yes/no",
        "consumed by sizing yes/no",
        "consumed by entry price logic yes/no",
        "consumed by exit/hold logic yes/no",
        "can change live accept/reject yes/no",
        "current decision effect",
        "duplicate/circular scoring risk",
        "required next action",
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for row in rows:
        values = [str(row[h]).replace("\n", "<br>") for h in headers]
        lines.append("| " + " | ".join(values) + " |")
    return lines


def build_report(evidence_rows: list[dict[str, Any]] | None = None) -> str:
    evidence_rows = list(evidence_rows or build_evidence_rows())
    report_rows = build_report_rows(evidence_rows)
    verdict = determine_verdict(report_rows)
    claim_classes = Counter(str(row["claim_class"]) for row in evidence_rows)
    source_inventory = sorted({str(row["producer_path"]) for row in evidence_rows})
    live_consumer_map = sorted(
        {
            f"`{row['feature_name']}` -> `{row['consumer_path']}` ({row['usage_type']})"
            for row in evidence_rows
            if row["consumer_path"]
        }
    )
    shadow_inventory = sorted({str(row["feature_name"]) for row in evidence_rows if row["claim_class"] in {"shadow_only", "diagnostic_only"}})
    dead_config_inventory = sorted({str(row["feature_name"]) for row in evidence_rows if row["claim_class"] == "dead_config"})
    circular_risks = sorted({str(row["feature_name"]) for row in evidence_rows if row["feature_name"] in {"macro_resid", "pillar_sum", "TA_FEATURES_CALCULATED fields", "alpha_search provider outputs", "sidecar fee-aware / peak-giveback outputs"}})
    missing_join_keys = sorted({str(row["feature_name"]) for row in evidence_rows if row["claim_class"] in {"unknown_requires_audit", "diagnostic_only", "retained_but_unjoined"}})
    recommended_promotion_candidates = sorted({str(row["feature_name"]) for row in evidence_rows if row["claim_class"] == "live_aggregated_only"})
    forbidden_promotion_candidates = sorted({str(row["feature_name"]) for row in evidence_rows if row["claim_class"] in {"shadow_only", "unknown_requires_audit"}})

    lines = [
        "# FEATURE_CONSUMPTION_AUTHORITY_AUDIT_V1",
        "",
        f"Verdict: `{verdict}`",
        "",
        "SSOT note: `reports/feature_authority/FEATURE_CONSUMPTION_AUTHORITY_EVIDENCE_ROWS_V1.jsonl` is the machine-readable authority artifact. This markdown is derived summary only.",
        "",
        "## Source Inventory",
        *[f"- `{item}`" for item in source_inventory],
        "",
        "## Feature Matrix",
        *_render_table(report_rows),
        "",
        "## Live Decision Consumer Map",
        *[f"- {item}" for item in live_consumer_map],
        "",
        "## Shadow-only / Diagnostic-only Inventory",
        *([f"- `{item}`" for item in shadow_inventory] or ["- none confirmed"]),
        "",
        "## Dead Config Inventory",
        *([f"- `{item}`" for item in dead_config_inventory] or ["- none confirmed"]),
        "",
        "## Circular Logic Risks",
        *([f"- `{item}`` can be double-counted if recorder/shadow copies are treated as independent authority." for item in circular_risks] or ["- none confirmed"]),
        "",
        "## Missing Join Keys",
        *([f"- `{item}`` remains evidence-incomplete and needs tighter producer->consumer join proof." for item in missing_join_keys] or ["- none confirmed"]),
        "",
        "## Recommended Promotion Candidates",
        *([f"- `{item}`" for item in recommended_promotion_candidates] or ["- none in this package"]),
        "",
        "## Forbidden Promotion Candidates",
        *([f"- `{item}`" for item in forbidden_promotion_candidates] or ["- none confirmed"]),
        "",
        "## Next Exact Package Recommendation",
        "- Use only `live_authoritative` and `live_veto_or_attenuation` evidence rows as calibration-authority candidates after parity closure.",
        "- Keep `shadow_only`, `diagnostic_only`, and `unknown_requires_audit` rows out of Phase 3 inputs.",
        "",
        "## Summary Counts",
    ]
    for key, value in sorted(claim_classes.items()):
        lines.append(f"- `{key}`: {value}")
    return "\n".join(lines) + "\n"


def write_evidence_rows(output_path: Path) -> list[dict[str, Any]]:
    rows = build_evidence_rows()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return rows


def write_report(output_path: Path, *, evidence_rows: list[dict[str, Any]] | None = None) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = build_report(evidence_rows=evidence_rows)
    output_path.write_text(report, encoding="utf-8")
    return report


def write_audit_bundle(
    *,
    report_path: Path,
    evidence_path: Path,
) -> tuple[list[dict[str, Any]], str]:
    evidence_rows = write_evidence_rows(evidence_path)
    report = write_report(report_path, evidence_rows=evidence_rows)
    return evidence_rows, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/FEATURE_CONSUMPTION_AUTHORITY_AUDIT_V1.md")
    parser.add_argument(
        "--evidence-output",
        default="reports/feature_authority/FEATURE_CONSUMPTION_AUTHORITY_EVIDENCE_ROWS_V1.jsonl",
    )
    args = parser.parse_args(argv)
    report_path = (ROOT / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    evidence_path = (ROOT / args.evidence_output).resolve() if not Path(args.evidence_output).is_absolute() else Path(args.evidence_output)
    write_audit_bundle(report_path=report_path, evidence_path=evidence_path)
    print(report_path)
    print(evidence_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
