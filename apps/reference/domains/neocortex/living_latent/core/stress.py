# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import math
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from living_latent.system.paths import get_logs_dir
from .cvar_policy import cvar_gate


def _heavy_tail(n: int, seed: int = 0) -> List[Tuple[dict, dict]]:
    rnd = random.Random(seed)
    pairs = []
    for _ in range(n):
        base = {"losses": [rnd.random() * 0.3 for _ in range(90)] + [rnd.random() * 0.5 for _ in range(10)]}
        # candidate has rare large spikes -> worse tail
        cand = {"losses": [rnd.random() * 0.3 for _ in range(85)] + [rnd.random() * 1.5 + 0.5 for _ in range(15)]}
        pairs.append((cand, base))
    return pairs


def _regime_shift(n: int, seed: int = 1) -> List[Tuple[dict, dict]]:
    rnd = random.Random(seed)
    pairs = []
    for _ in range(n):
        base = {"losses": [0.2 + 0.05 * rnd.random() for _ in range(50)] + [0.3 + 0.05 * rnd.random() for _ in range(50)]}
        cand = {"losses": [0.2 + 0.05 * rnd.random() for _ in range(70)] + [0.5 + 0.1 * rnd.random() for _ in range(30)]}
        pairs.append((cand, base))
    return pairs


def _sparse_shock(n: int, seed: int = 2) -> List[Tuple[dict, dict]]:
    rnd = random.Random(seed)
    pairs = []
    for _ in range(n):
        base = {"losses": [rnd.random() * 0.2 for _ in range(100)]}
        cand = {"losses": [rnd.random() * 0.2 for _ in range(95)] + [2.0 + rnd.random() for _ in range(5)]}
        pairs.append((cand, base))
    return pairs


def _drift(n: int, seed: int = 3) -> List[Tuple[dict, dict]]:
    rnd = random.Random(seed)
    pairs = []
    for _ in range(n):
        base_losses = []
        x = 0.2
        for i in range(100):
            x += rnd.uniform(-0.01, 0.01)
            base_losses.append(max(0.0, x))
        cand_losses = [v * (1.0 + 0.05 * rnd.random()) for v in base_losses]
        pairs.append(({"losses": cand_losses}, {"losses": base_losses}))
    return pairs


def _eval_pairs(pairs: Sequence[Tuple[dict, dict]] , params: dict) -> dict:
    ok = 0
    false_accept = 0
    false_reject = 0
    total = 0
    for cand, base in pairs:
        total += 1
        accept, _ = cvar_gate(
            cand,
            base,
            tau=params.get("tau", 0.05),
            min_threshold=params.get("min_threshold", 0.0),
            enabled=True,
            exp_weight=params.get("exp_weight", 0.0),
            winsor_p=params.get("winsor_p", 0.005),
        )
        # In these scenarios, candidate is designed to be worse than base
        is_worse = True
        if accept:
            false_accept += 1
        else:
            ok += 1
    return {
        "ok_ratio": ok / max(1, total),
        "false_accepts": false_accept,
        "false_rejects": false_reject,
        "total": total,
    }


def run_calibration(seed: int = 0) -> dict:
    grids = {
        "tau": [0.01, 0.05, 0.10],
        "min_threshold": [0.0, -0.05, -0.10],
        "exp_weight": [0.0, 0.1, 0.2],
    }
    winsor_p = 0.005
    scenarios = {
        "heavy_tail": _heavy_tail(20, seed),
        "regime_shift": _regime_shift(15, seed + 1),
        "sparse_shock": _sparse_shock(15, seed + 2),
        "drift": _drift(10, seed + 3),
    }
    best = {"score": -1.0, "params": None}
    results: Dict[str, Any] = {"grid": grids, "scenarios": {}, "selected": None}
    for tau in grids["tau"]:
        for mt in grids["min_threshold"]:
            for ew in grids["exp_weight"]:
                params = {"tau": tau, "min_threshold": mt, "exp_weight": ew, "winsor_p": winsor_p}
                agg_ok = 0.0
                agg_total = 0
                fa = 0
                scen_res = {}
                for name, pairs in scenarios.items():
                    r = _eval_pairs(pairs, params)
                    scen_res[name] = r
                    agg_ok += r["ok_ratio"]
                    agg_total += r["total"]
                    fa += r["false_accepts"]
                score = agg_ok / max(1, len(scenarios)) - 0.001 * fa
                if score > best["score"]:
                    best = {"score": score, "params": params}
                results["scenarios"][f"tau={tau},mt={mt},ew={ew}"] = scen_res
    results["selected"] = {"params": best["params"], "score": best["score"]}
    # write report
    out_dir = Path(get_logs_dir()) / 'cvar_calib'
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    report_path = out_dir / f'report_{ts}.json'
    report_path.write_text(json.dumps(results, indent=2), encoding='utf-8')
    results["report_path"] = str(report_path)
    return results


def main(argv: List[str] | None = None) -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=0)
    args = ap.parse_args(argv)
    res = run_calibration(seed=args.seed)
    print(json.dumps({"report": res.get("report_path"), "selected": res.get("selected")}, indent=2))


if __name__ == '__main__':
    main()