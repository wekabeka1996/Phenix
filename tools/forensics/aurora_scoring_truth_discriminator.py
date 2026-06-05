from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.reference.shared.decision_primitives.score_lineage import (  # noqa: E402
    COMPATIBILITY_ONLY,
    LIVE_AUTHORITATIVE,
    SCORE_FIELD_REGISTRY,
    SHADOW_ONLY,
)


CALIBRATOR_SYNTHETIC = "CALIBRATOR_SYNTHETIC"
UNKNOWN = "UNKNOWN"

AUTHORITY_STATUS_MAP = {
    "live_authoritative": "LIVE_AUTHORITATIVE",
    "shadow_only": "SHADOW_ONLY",
    "compatibility_only": "COMPATIBILITY_ONLY",
    "deprecated_alias": "COMPATIBILITY_ONLY",
}

REQUIRED_SURFACES = (
    "apps/reference/domains/feature_engineering",
    "apps/reference/domains/strategies/runtimes/aurora",
    "apps/reference/shared/decision_primitives/scoring_kernel.py",
    "apps/reference/shared/decision_primitives/score_lineage.py",
    "apps/reference/domains/decision_making/gateway/strategy_gateway.py",
    "apps/reference/domains/decision_making/gates/low_vol_cost_floor.py",
    "apps/reference/domains/decision_making/gates/objective_gate_evaluator.py",
    "apps/reference/domains/decision_making/intent",
    "calibrators",
    "tools/forensics",
    "config/aurora/strategies/aurora.yaml",
    "config/aurora/domains.yaml",
    "config/alpha_search.yaml",
)

FIELD_ORDER = (
    "pillar_sum",
    "pillar_tactician",
    "pillar_operator",
    "pillar_strategist",
    "linear_score",
    "raw_score",
    "decision_score",
    "sizing_score",
    "score",
    "final_score",
    "signal_score",
    "objective_score",
    "strategy_confidence",
    "judge_confidence",
    "score_lineage",
)


@dataclass(frozen=True)
class SurfaceHit:
    path: str
    line: int
    text: str


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _iter_files(root: Path, surfaces: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for surface in surfaces:
        path = root / surface
        if not path.exists():
            continue
        if path.is_file():
            files.append(path)
            continue
        files.extend(
            p
            for p in path.rglob("*")
            if p.is_file()
            and p.suffix.lower() in {".py", ".yaml", ".yml", ".json", ".md"}
            and ".pytest_cache" not in p.parts
            and "__pycache__" not in p.parts
        )
    return sorted(set(files))


def _search(files: list[Path], root: Path, term: str) -> list[SurfaceHit]:
    hits: list[SurfaceHit] = []
    pattern = re.compile(re.escape(term))
    for path in files:
        text = _read(path)
        for idx, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                hits.append(
                    SurfaceHit(
                        path=str(path.relative_to(root)).replace("\\", "/"),
                        line=idx,
                        text=line.strip()[:220],
                    )
                )
    return hits


def _registry_authority(field: str) -> str:
    contract = SCORE_FIELD_REGISTRY.get(field)
    if contract is None:
        return UNKNOWN
    return AUTHORITY_STATUS_MAP.get(contract.live_authority_status, UNKNOWN)


def _first_paths(hits: list[SurfaceHit], limit: int = 8) -> list[str]:
    seen: list[str] = []
    for hit in hits:
        item = f"{hit.path}:{hit.line}"
        if item not in seen:
            seen.append(item)
        if len(seen) >= limit:
            break
    return seen


def _contains_callsite(text: str, field: str) -> bool:
    return field in text


def _config_geometry(root: Path) -> dict[str, Any]:
    path = root / "config/aurora/strategies/aurora.yaml"
    if not path.exists():
        return {
            "status": "MISSING",
            "admission_mode": None,
            "sizing_mode": None,
        }
    text = _read(path)
    admission = re.search(r"^\s*admission_mode:\s*([A-Za-z0-9_]+)\s*$", text, re.M)
    sizing = re.search(r"^\s*sizing_mode:\s*([A-Za-z0-9_]+)\s*$", text, re.M)
    return {
        "status": "PRESENT",
        "admission_mode": admission.group(1) if admission else None,
        "sizing_mode": sizing.group(1) if sizing else None,
    }


def _producer_for(field: str, hit_paths: list[str]) -> str:
    if field == "pillar_sum":
        producer_hits = [
            path
            for path in hit_paths
            if "feature_engineering" in path
            or "data_recorder" in path
            or "calibrators/" in path
        ]
        if producer_hits:
            return "PARTIAL: feature/calibrator candidate paths found"
        return "UNKNOWN"
    if field in {"pillar_tactician", "pillar_operator", "pillar_strategist"}:
        return "UNKNOWN"
    if field == "linear_score":
        return "optional QuadraticScoringKernel.compute arg"
    if field in {"raw_score", "decision_score", "sizing_score"}:
        return "QuadraticScoringKernel.compute"
    if field == "score":
        return "Aurora scoring payload compatibility alias"
    if field in {"final_score", "signal_score"}:
        return "StrategyGateway / Aurora trace compatibility assembly"
    if field == "objective_score":
        return "objective_gate_evaluator"
    if field in {"strategy_confidence", "judge_confidence"}:
        return "candidate trace/objective/Judge helper surfaces"
    if field == "score_lineage":
        return "score_lineage builders in Aurora/StrategyGateway"
    return "UNKNOWN"


def _consumers_for(field: str, hit_paths: list[str]) -> str:
    consumers = []
    if any("scoring_kernel.py" in path for path in hit_paths):
        consumers.append("QuadraticScoringKernel")
    if any("aurora/decision.py" in path for path in hit_paths):
        consumers.append("Aurora decision path")
    if any("strategy_gateway.py" in path for path in hit_paths):
        consumers.append("StrategyGateway")
    if any("low_vol_cost_floor.py" in path for path in hit_paths):
        consumers.append("low_vol_cost_floor")
    if any("objective_gate_evaluator.py" in path for path in hit_paths):
        consumers.append("objective_gate_evaluator")
    if any("calibrators/" in path for path in hit_paths):
        consumers.append("calibrators")
    if any("config/" in path for path in hit_paths):
        consumers.append("config surface")
    return ", ".join(consumers) if consumers else "UNKNOWN"


def _runtime_active(field: str, hit_paths: list[str]) -> str:
    if field in {"pillar_sum", "raw_score", "decision_score", "sizing_score", "score_lineage"}:
        return "YES_BY_CODE_PATH"
    if field in {"score", "final_score", "signal_score"}:
        return "YES_COMPATIBILITY_OR_TRACE"
    if field in {"strategy_confidence", "judge_confidence"}:
        return "CANDIDATE_OR_SHADOW"
    if field == "linear_score":
        return "OPTIONAL_ARG_PATH"
    if field.startswith("pillar_"):
        return "TRACE_ONLY_OR_UNKNOWN"
    return "UNKNOWN"


def build_summary(root: Path = REPO_ROOT) -> dict[str, Any]:
    root = root.resolve()
    files = _iter_files(root, REQUIRED_SURFACES)
    all_text_by_path = {
        str(path.relative_to(root)).replace("\\", "/"): _read(path)
        for path in files
    }
    hits_by_field = {field: _search(files, root, field) for field in FIELD_ORDER}
    geometry = _config_geometry(root)

    producer_consumer_map: list[dict[str, Any]] = []
    for field in FIELD_ORDER:
        hits = hits_by_field[field]
        hit_paths = _first_paths(hits, limit=12)
        status = _registry_authority(field)
        if field in {"pillar_tactician", "pillar_operator", "pillar_strategist"}:
            status = UNKNOWN
        if field == "score_lineage":
            status = LIVE_AUTHORITATIVE.upper()
        if field == "pillar_sum" and any("calibrators/" in path for path in hit_paths):
            unresolved = "Producer is only partially mapped; live FeatureEngineering ownership not proven."
        elif not hits:
            unresolved = "No hit in required surfaces."
        else:
            unresolved = ""
        producer_consumer_map.append(
            {
                "field_or_surface": field,
                "producer": _producer_for(field, hit_paths),
                "consumers": _consumers_for(field, hit_paths),
                "authority_status": status,
                "runtime_active": _runtime_active(field, hit_paths),
                "evidence": hit_paths,
                "unresolved_gap": unresolved,
            }
        )

    scoring_kernel_text = all_text_by_path.get(
        "apps/reference/shared/decision_primitives/scoring_kernel.py", ""
    )
    config_loader_text = all_text_by_path.get(
        "apps/reference/domains/strategies/runtimes/aurora/config_loader.py", ""
    )
    decision_text = all_text_by_path.get(
        "apps/reference/domains/strategies/runtimes/aurora/decision.py", ""
    )
    low_vol_text = all_text_by_path.get(
        "apps/reference/domains/decision_making/gates/low_vol_cost_floor.py", ""
    )

    signal_weights_in_kernel_signature = "signal_weights:" in scoring_kernel_text
    signal_weights_read_in_kernel = bool(
        re.search(r"signal_weights\W*(?:\.get|\[| in )", scoring_kernel_text)
    )
    feature_neutrals_read_in_kernel = bool(
        re.search(r"feature_neutrals\W*(?:\.get|\[| in )", scoring_kernel_text)
    )
    upstream_signal_surface = (
        _contains_callsite(config_loader_text, "signal_weights")
        or _contains_callsite(decision_text, "_get_signal_weights")
    )
    upstream_feature_neutral_surface = (
        _contains_callsite(config_loader_text, "feature_neutrals")
        or _contains_callsite(decision_text, "_get_feature_neutrals")
    )

    if signal_weights_read_in_kernel:
        signal_verdict = "SIGNAL_WEIGHTS_RUNTIME_EFFECT_PROVEN"
    elif upstream_signal_surface:
        signal_verdict = "SIGNAL_WEIGHTS_EFFECT_BLOCKED_BY_MISSING_TEST_SEAM"
    else:
        signal_verdict = "SIGNAL_WEIGHTS_DEAD_CONFIG_CONFIRMED"

    if feature_neutrals_read_in_kernel:
        feature_verdict = "FEATURE_NEUTRALS_RUNTIME_EFFECT_PROVEN"
    elif upstream_feature_neutral_surface:
        feature_verdict = "FEATURE_NEUTRALS_EFFECT_BLOCKED_BY_MISSING_TEST_SEAM"
    else:
        feature_verdict = "FEATURE_NEUTRALS_DEAD_FOR_LIVE_AURORA"

    if (
        geometry.get("admission_mode") == "linear"
        and geometry.get("sizing_mode") == "quadratic"
    ):
        quadratic_verdict = "QUADRATIC_USED_FOR_SIZING_ONLY"
    else:
        quadratic_verdict = "QUADRATIC_MIXED_SEMANTICS_FOUND"

    downstream_lineage = {
        "low_vol_uses_find_score_lineage_record": "find_score_lineage_record" in low_vol_text,
        "low_vol_signed_sources": ["signal_score", "final_score"],
        "low_vol_shadow_candidate_sources": ["judge_confidence", "strategy_confidence"],
        "legacy_aliases_reported": [
            "score",
            "final_score",
            "final_score_raw",
            "signal_score",
        ],
        "status": "LOW_VOL_CONSUMES_COMPATIBILITY_ALIAS",
    }

    facts = [
        "QuadraticScoringKernel.compute resolves s_linear from linear_score or features['pillar_sum'].",
        "QuadraticScoringKernel.compute accepts signal_weights and feature_neutrals for call-site compatibility.",
        "Current Aurora YAML decision geometry is admission_mode=%s, sizing_mode=%s."
        % (geometry.get("admission_mode"), geometry.get("sizing_mode")),
        "Aurora decision payload includes raw_score, decision_score, sizing_score and score_lineage.",
        "Aurora objective gate pass can replace result.score with objective_score.",
        "low_vol_cost_floor uses score lineage helpers and compatibility score aliases.",
    ]

    inferences = [
        "Kernel-level signal_weights and feature_neutrals are not live scoring inputs when pillar_sum is held fixed.",
        "Current config makes quadratic geometry a sizing transform while admission remains linear.",
        "pillar_sum remains the key upstream aggregate input, but its exact live producer needs a stronger runtime seam.",
    ]

    unknowns = [
        "Exact live FeatureEngineering producer ownership for pillar_sum.",
        "Whether any upstream pillar_sum producer reads aurora.decision.signal_weights before kernel invocation.",
        "Whether any upstream pillar_sum producer reads feature_neutrals before kernel invocation.",
        "Whether runtime captures include enough score_lineage for all rejected/deferred paths.",
    ]

    return {
        "facts": facts,
        "inferences": inferences,
        "unknowns": unknowns,
        "producer_consumer_map": producer_consumer_map,
        "testability_gaps": [
            {
                "gap": "No production-neutral fixture seam was found that proves full Aurora handler perturbation from YAML signal_weights through live FeatureEngineering pillar_sum production.",
                "verdict": "SIGNAL_WEIGHTS_EFFECT_BLOCKED_BY_MISSING_TEST_SEAM",
            },
            {
                "gap": "feature_neutrals has Judge/config surfaces and Aurora call-site surfaces, but live Aurora scoring effect beyond kernel invariance is not proven without a full upstream producer seam.",
                "verdict": "FEATURE_NEUTRALS_EFFECT_BLOCKED_BY_MISSING_TEST_SEAM",
            },
        ],
        "verdicts": {
            "signal_weights_effect": signal_verdict,
            "feature_neutrals_effect": feature_verdict,
            "quadratic_logic_classification": quadratic_verdict,
            "downstream_gate_lineage_status": downstream_lineage["status"],
            "pillar_sum_producer_status": "PARTIALLY_MAPPED_UNPROVEN_LIVE_OWNER",
        },
        "geometry": geometry,
        "downstream_lineage": downstream_lineage,
        "surface_counts": {
            field: len(hits) for field, hits in hits_by_field.items()
        },
        "scanned_files_count": len(files),
        "required_surfaces": {
            surface: "PRESENT" if (root / surface).exists() else "MISSING"
            for surface in REQUIRED_SURFACES
        },
    }


def _to_markdown(summary: dict[str, Any]) -> str:
    lines = ["# Aurora Scoring Truth Discriminator Summary", ""]
    for section in ("facts", "inferences", "unknowns"):
        lines.append(f"## {section.title()}")
        for item in summary[section]:
            lines.append(f"- {item}")
        lines.append("")
    lines.append("## Verdicts")
    for key, value in summary["verdicts"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Producer Consumer Map")
    lines.append("| field | producer | consumers | authority | runtime_active | unresolved |")
    lines.append("|---|---|---|---|---|---|")
    for row in summary["producer_consumer_map"]:
        lines.append(
            "| {field_or_surface} | {producer} | {consumers} | {authority_status} | {runtime_active} | {unresolved_gap} |".format(
                **row
            )
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Aurora scoring truth discriminator."
    )
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)

    summary = build_summary(Path(args.repo_root))
    if args.format == "json":
        rendered = json.dumps(summary, indent=2, sort_keys=True)
    else:
        rendered = _to_markdown(summary)

    if args.output:
        Path(args.output).write_text(rendered + ("\n" if not rendered.endswith("\n") else ""), encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
