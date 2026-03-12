from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .search import ObjectiveCandidate


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")


def write_overlay_bundle(out_dir: Path, *, best_candidate: ObjectiveCandidate, candidates: list[ObjectiveCandidate]) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    domain_path = out_dir / "candidate_domains_objective_engine_overlay.yaml"
    aurora_path = out_dir / "candidate_aurora_objective_overlay.yaml"
    md_amr_path = out_dir / "candidate_md_amr_objective_overlay.yaml"
    mr_path = out_dir / "candidate_mean_reversion_objective_overlay.yaml"
    _write_yaml(domain_path, best_candidate.domain_overlay)
    _write_yaml(aurora_path, best_candidate.strategy_overlays.get("aurora", {}))
    _write_yaml(md_amr_path, best_candidate.strategy_overlays.get("md_amr", {}))
    _write_yaml(mr_path, best_candidate.strategy_overlays.get("mean_reversion", {}))
    (out_dir / "best_trial.json").write_text(
        json.dumps(
            {
                "score": best_candidate.score,
                "summary": best_candidate.summary,
                "domain_overlay": best_candidate.domain_overlay,
                "strategy_overlays": best_candidate.strategy_overlays,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (out_dir / "candidate_bundle.json").write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "score": candidate.score,
                        "summary": candidate.summary,
                        "domain_overlay": candidate.domain_overlay,
                        "strategy_overlays": candidate.strategy_overlays,
                    }
                    for candidate in candidates
                ]
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return {
        "domain_overlay": str(domain_path),
        "aurora_overlay": str(aurora_path),
        "md_amr_overlay": str(md_amr_path),
        "mean_reversion_overlay": str(mr_path),
    }
