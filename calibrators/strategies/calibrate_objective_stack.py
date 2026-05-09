#!/usr/bin/env python3
"""Meta or stage-2 calibration stack.

This tool bundles stage-1 strategy candidates and objective-search artifacts.
It is not a stage-1 production calibrator for any single live strategy surface.
"""
from __future__ import annotations
from tools.objective_calibration.search import search_objective_candidates
from tools.objective_calibration.report import render_objective_calibration_report
from tools.objective_calibration.overlay import write_overlay_bundle
from tools.objective_calibration.dataset import build_objective_dataset, load_objective_dataset
from apps.reference.config_loader import ConfigLoader

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw)


def _default_out_dir(scope: str) -> Path:
    return Path(f"reports/objective_calibration/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{scope}")


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _current_strategy_bundle(config_root: Path) -> dict[str, Any]:
    cfg = ConfigLoader(config_root).load_config()
    return {
        "strategy_overlays": {
            "aurora": {"aurora": cfg.strategies.aurora.model_dump(mode="json")},
            "md_amr": {"md_amr": cfg.strategies.md_amr.model_dump(mode="json")},
            "mean_reversion": {"mean_reversion": cfg.strategies.mean_reversion.model_dump(mode="json")},
        }
    }


def _strategy_candidates_from_file(path: Path | None) -> list[dict[str, Any]]:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("candidates"), list):
        out: list[dict[str, Any]] = []
        for item in payload["candidates"]:
            if isinstance(item, dict) and isinstance(item.get("overlay"), dict):
                out.append({"score": float(item.get("score", 0.0)
                           or 0.0), "overlay": item["overlay"]})
        return out
    if isinstance(payload.get("overlay"), dict):
        return [{"score": float(payload.get("score", 0.0) or 0.0), "overlay": payload["overlay"]}]
    return []


def _build_strategy_bundle(
    *,
    config_root: Path,
    aurora_candidates_path: Path | None,
    md_amr_candidates_path: Path | None,
    mr_candidates_path: Path | None,
    top_k: int,
) -> dict[str, Any]:
    baseline = _current_strategy_bundle(config_root)["strategy_overlays"]
    aurora_candidates = _strategy_candidates_from_file(aurora_candidates_path) or [
        {"score": 0.0, "overlay": baseline["aurora"]}]
    md_amr_candidates = _strategy_candidates_from_file(md_amr_candidates_path) or [
        {"score": 0.0, "overlay": baseline["md_amr"]}]
    mr_candidates = _strategy_candidates_from_file(mr_candidates_path) or [
        {"score": 0.0, "overlay": baseline["mean_reversion"]}]
    merged: list[dict[str, Any]] = []
    max_candidates = max(len(aurora_candidates), len(
        md_amr_candidates), len(mr_candidates), 1)
    for idx in range(min(max_candidates, max(1, int(top_k)))):
        aur = aurora_candidates[min(idx, len(aurora_candidates) - 1)]
        md = md_amr_candidates[min(idx, len(md_amr_candidates) - 1)]
        mr = mr_candidates[min(idx, len(mr_candidates) - 1)]
        merged.append(
            {
                "score": float(aur["score"]) + float(md["score"]) + float(mr["score"]),
                "strategy_overlays": {
                    "aurora": aur["overlay"],
                    "md_amr": md["overlay"],
                    "mean_reversion": mr["overlay"],
                },
            }
        )
    return {"candidates": merged}


def _write_strategy_bundle(out_dir: Path, bundle: dict[str, Any]) -> None:
    import yaml

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "candidate_bundle.json").write_text(json.dumps(bundle,
                                                              indent=2, ensure_ascii=False), encoding="utf-8")
    best = ((bundle.get("candidates") or [{}])[0])
    strategy_overlays = best.get(
        "strategy_overlays") if isinstance(best, dict) else {}
    for strategy_id, file_name in (
        ("aurora", "candidate_aurora_strategy_overlay.yaml"),
        ("md_amr", "candidate_md_amr_strategy_overlay.yaml"),
        ("mean_reversion", "candidate_mean_reversion_strategy_overlay.yaml"),
    ):
        overlay = strategy_overlays.get(strategy_id, {}) if isinstance(
            strategy_overlays, dict) else {}
        (out_dir / file_name).write_text(yaml.safe_dump(overlay,
                                                        sort_keys=False, allow_unicode=False), encoding="utf-8")
    (out_dir / "report.md").write_text(
        "# Strategy Calibration Bundle\n\n- Calibration class: meta/stage2.\n- This artifact bundles candidate strategy overlays.\n- It is not a stage-1 production calibrator.\n- It does not mutate canonical YAML automatically.\n",
        encoding="utf-8",
    )


def _resolve_dataset(args: argparse.Namespace):
    if args.dataset_dir:
        return load_objective_dataset(Path(args.dataset_dir))
    return build_objective_dataset(
        recorder_dir=Path(args.recorder_dir),
        wal_dir=Path(args.wal_dir),
        ledger_path=Path(args.ledger_path),
        symbols=args.symbols,
        start=args.start,
        end=args.end,
        tf_sec=int(args.tf_sec),
    )


def _cmd_build_dataset(args: argparse.Namespace) -> int:
    dataset = build_objective_dataset(
        recorder_dir=Path(args.recorder_dir),
        wal_dir=Path(args.wal_dir),
        ledger_path=Path(args.ledger_path),
        symbols=args.symbols,
        start=args.start,
        end=args.end,
        tf_sec=int(args.tf_sec),
    )
    out_dir = Path(
        args.out_dir) if args.out_dir else _default_out_dir("dataset")
    dataset.write(out_dir)
    print(f"Objective dataset written to {out_dir}")
    return 0


def _cmd_strategy(args: argparse.Namespace) -> int:
    out_dir = Path(
        args.out_dir) if args.out_dir else _default_out_dir("strategy")
    bundle = _build_strategy_bundle(
        config_root=Path(args.config_root),
        aurora_candidates_path=Path(
            args.aurora_candidates) if args.aurora_candidates else None,
        md_amr_candidates_path=Path(
            args.md_amr_candidates) if args.md_amr_candidates else None,
        mr_candidates_path=Path(
            args.mean_reversion_candidates) if args.mean_reversion_candidates else None,
        top_k=int(args.top_k),
    )
    _write_strategy_bundle(out_dir, bundle)
    print(f"Strategy candidate bundle written to {out_dir}")
    return 0


def _objective_stage(
    *,
    dataset,
    config_root: Path,
    strategy_bundle_path: Path | None,
    out_dir: Path,
    trials: int,
    top_k: int,
    seed: int,
    min_trade_count: int,
    scope: str,
) -> int:
    candidates = search_objective_candidates(
        realized_df=dataset.realized_trades,
        attempted_df=dataset.attempted_entries,
        config_root=config_root,
        strategy_bundle_path=strategy_bundle_path,
        trials=int(trials),
        top_k=int(top_k),
        seed=int(seed),
        min_trade_count=int(min_trade_count),
    )
    best = candidates[0]
    overlay_paths = write_overlay_bundle(
        out_dir, best_candidate=best, candidates=candidates)
    render_objective_calibration_report(
        out_dir,
        scope=scope,
        dataset_manifest=dataset.manifest,
        best_candidate=best,
        candidate_count=len(candidates),
        overlay_paths=overlay_paths,
    )
    return 0


def _cmd_objective(args: argparse.Namespace) -> int:
    dataset = _resolve_dataset(args)
    out_dir = Path(args.out_dir) if args.out_dir else _default_out_dir(
        "objective")
    out_dir.mkdir(parents=True, exist_ok=True)
    if not args.dataset_dir:
        dataset.write(out_dir / "dataset")
    return _objective_stage(
        dataset=dataset,
        config_root=Path(args.config_root),
        strategy_bundle_path=Path(
            args.strategy_bundle) if args.strategy_bundle else None,
        out_dir=out_dir,
        trials=args.trials,
        top_k=args.top_k,
        seed=args.seed,
        min_trade_count=args.min_trade_count,
        scope="objective",
    )


def _cmd_joint(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir) if args.out_dir else _default_out_dir("joint")
    out_dir.mkdir(parents=True, exist_ok=True)
    strategy_dir = out_dir / "strategy_stage"
    bundle = _build_strategy_bundle(
        config_root=Path(args.config_root),
        aurora_candidates_path=Path(
            args.aurora_candidates) if args.aurora_candidates else None,
        md_amr_candidates_path=Path(
            args.md_amr_candidates) if args.md_amr_candidates else None,
        mr_candidates_path=Path(
            args.mean_reversion_candidates) if args.mean_reversion_candidates else None,
        top_k=int(args.top_k),
    )
    _write_strategy_bundle(strategy_dir, bundle)
    dataset = _resolve_dataset(args)
    if not args.dataset_dir:
        dataset.write(out_dir / "dataset")
    return _objective_stage(
        dataset=dataset,
        config_root=Path(args.config_root),
        strategy_bundle_path=strategy_dir / "candidate_bundle.json",
        out_dir=out_dir / "objective_stage",
        trials=args.trials,
        top_k=args.top_k,
        seed=args.seed,
        min_trade_count=args.min_trade_count,
        scope="joint",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Meta or stage-2 strategy plus objective calibration stack. "
            "Not a stage-1 production surface calibrator."
        )
    )
    parser.add_argument("--config-root", default="config/aurora")
    sub = parser.add_subparsers(dest="command", required=True)

    common_dataset = argparse.ArgumentParser(add_help=False)
    common_dataset.add_argument("--dataset-dir", default=None)
    common_dataset.add_argument("--recorder-dir", default="data/recorder")
    common_dataset.add_argument("--wal-dir", default="ops/wal")
    common_dataset.add_argument(
        "--ledger-path", default="data/order_ledger.db")
    common_dataset.add_argument("--symbols", nargs="+", default=["BTCUSDT"])
    common_dataset.add_argument("--start", type=_parse_date, default=None)
    common_dataset.add_argument("--end", type=_parse_date, default=None)
    common_dataset.add_argument("--tf-sec", type=int, default=300)

    common_search = argparse.ArgumentParser(add_help=False)
    common_search.add_argument("--strategy-bundle", default=None)
    common_search.add_argument("--trials", type=int, default=100)
    common_search.add_argument("--top-k", type=int, default=5)
    common_search.add_argument("--seed", type=int, default=42)
    common_search.add_argument("--min-trade-count", type=int, default=5)

    build_dataset = sub.add_parser("build-dataset", parents=[common_dataset])
    build_dataset.add_argument("--out-dir", default=None)
    build_dataset.set_defaults(func=_cmd_build_dataset)

    strategy = sub.add_parser("strategy")
    strategy.add_argument("--aurora-candidates", default=None)
    strategy.add_argument("--md-amr-candidates", default=None)
    strategy.add_argument("--mean-reversion-candidates", default=None)
    strategy.add_argument("--top-k", type=int, default=5)
    strategy.add_argument("--out-dir", default=None)
    strategy.set_defaults(func=_cmd_strategy)

    objective = sub.add_parser("objective", parents=[
                               common_dataset, common_search])
    objective.add_argument("--out-dir", default=None)
    objective.set_defaults(func=_cmd_objective)

    joint = sub.add_parser("joint", parents=[common_dataset, common_search])
    joint.add_argument("--aurora-candidates", default=None)
    joint.add_argument("--md-amr-candidates", default=None)
    joint.add_argument("--mean-reversion-candidates", default=None)
    joint.add_argument("--out-dir", default=None)
    joint.set_defaults(func=_cmd_joint)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
