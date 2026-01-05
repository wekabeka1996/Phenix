# SPDX-License-Identifier: MIT
from __future__ import annotations

import csv
import json
import math
import os
import random
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from .genome import Genome
from .cvar_policy import cvar_estimate
from living_latent.system.paths import get_logs_dir, get_runs_dir


def _as_losses(x: Any) -> List[float]:
    from living_latent.r2.cvar_policy import _as_loss_series  # reuse helper
    seq = _as_loss_series(x)
    return list(seq or [])


def _iqr_scale(xs: Sequence[float]) -> float:
    if not xs:
        return 1.0
    xs = sorted(xs)
    n = len(xs)
    q5 = xs[max(0, int(0.05 * (n - 1)))]
    q95 = xs[int(0.95 * (n - 1))]
    s = max(1e-9, (q95 - q5))
    return float(s)


def fitness(j_series: Sequence[float], tau: float, exp_weight: float = 0.0) -> float:
    # Loss series from J: losses = -J
    losses = [-float(v) for v in j_series]
    if not losses:
        # Fallback on empty: mean-var proxy over J
        if not j_series:
            return 0.0
        m = sum(j_series) / max(1, len(j_series))
        var = 0.0
        if len(j_series) > 1:
            mu = m
            var = sum((x - mu) ** 2 for x in j_series) / (len(j_series) - 1)
        return -m - 0.1 * var
    # CVaR tail of losses
    cvar = cvar_estimate(losses, tau)
    # Stability bonus: penalize variance of J; normalize to [~ -1, 0]
    if len(j_series) > 1:
        mu = sum(j_series) / len(j_series)
        var = sum((x - mu) ** 2 for x in j_series) / (len(j_series) - 1)
    else:
        var = 0.0
    scale = _iqr_scale(j_series)
    stab = -min(1.0, var / (scale * scale + 1e-12))
    return -float(cvar) + 0.1 * float(stab)


def _load_run_bridges(run_dir: Path) -> List[float]:
    # Collect candidate J or rewards from bridge logs
    js: List[float] = []
    bdir = run_dir / 'logs' / 'bridges'
    if bdir.exists():
        for fp in sorted(bdir.glob('*.json')):
            try:
                rec = json.loads(fp.read_text(encoding='utf-8'))
                # prefer J_samples, else J, else rewards
                if isinstance(rec, dict):
                    if 'J_samples' in rec and isinstance(rec['J_samples'], list):
                        js.extend([float(v) for v in rec['J_samples']])
                    elif 'J' in rec:
                        js.append(float(rec['J']))
                    elif 'rewards' in rec and isinstance(rec['rewards'], list):
                        js.extend([float(v) for v in rec['rewards']])
            except Exception:
                continue
    return js


def _make_logs_dirs() -> Tuple[Path, Path]:
    logs = Path(get_logs_dir()) / 'evolve'
    reports = logs  # keep in same evolve folder
    logs.mkdir(parents=True, exist_ok=True)
    # README once
    readme = logs / 'README.md'
    if not readme.exists():
        readme.write_text(
            """# Evolve Logs\n\n- ledger.csv: append-only log of evolution rounds\n- round_<n>.json: snapshot of top-1 genome and metrics per round\n""",
            encoding='utf-8',
        )
    return logs, reports


def _ledger_writer(path: Path) -> Tuple[csv.writer, any]:
    new = not path.exists()
    f = path.open('a', newline='', encoding='utf-8')
    w = csv.writer(f)
    if new:
        w.writerow(['round', 'idx', 'fitness', 'p', 'q', 'lam', 'kappa', 'rho', 'ups'])
    return w, f


def tournament_select(pop: List[Tuple[Genome, float]], k: int, rnd: random.Random) -> Genome:
    cand = rnd.sample(pop, k=min(k, len(pop)))
    # Higher fitness is better
    cand.sort(key=lambda t: t[1], reverse=True)
    return cand[0][0]


def evolve(rounds: int = 10, pop_size: int = 12, k: int = 3, tau: float = 0.05, seed: int | None = None,
           run: str | None = None) -> Dict[str, Any]:
    rnd = random.Random(seed)
    logs_dir, reports_dir = _make_logs_dirs()
    ledger_path = logs_dir / 'ledger.csv'
    ledger, f = _ledger_writer(ledger_path)

    # Data source
    j_series: List[float]
    if run:
        runs_dir = Path(get_runs_dir())
        run_dir = Path(run)
        run_dir = run_dir if run_dir.is_dir() else (runs_dir / run)
        j_series = _load_run_bridges(run_dir)
        if not j_series:
            # fallback to synthetic
            j_series = [math.sin(0.1 * i) + rnd.gauss(0, 0.05) for i in range(200)]
    else:
        # Synthetic stable mock
        j_series = [math.sin(0.1 * i) + rnd.gauss(0, 0.05) for i in range(200)]

    # Initialize population
    pop = [Genome.sample(rnd.randrange(10**9)) for _ in range(pop_size)]

    best: Tuple[Genome, float] | None = None
    snapshots: List[Path] = []
    for r in range(1, rounds + 1):
        scored: List[Tuple[Genome, float]] = []
        for g in pop:
            fit = fitness(j_series, tau)
            scored.append((g, fit))
        scored.sort(key=lambda t: t[1], reverse=True)
        if best is None or scored[0][1] > best[1]:
            best = scored[0]

        # Log ledger
        for idx, (g, fit) in enumerate(scored):
            row = [r, idx, f"{fit:.6f}", g.p, g.q, g.lam, g.kappa, g.rho, g.ups]
            ledger.writerow(row)
        f.flush()

        # Snapshot top-1
        snap = {
            'round': r,
            'top1': {'fitness': scored[0][1], 'genome': scored[0][0].to_dict()},
            'population': [{'fitness': s, 'genome': g.to_dict()} for g, s in scored[:min(5, len(scored))]],
        }
        snap_path = reports_dir / f'round_{r}.json'
        snap_path.write_text(json.dumps(snap, indent=2), encoding='utf-8')
        snapshots.append(snap_path)

        # Next generation via tournament and mutation
        next_pop: List[Genome] = []
        while len(next_pop) < pop_size:
            parent = tournament_select(scored, k, rnd)
            child = parent.mutate(rnd.randrange(10**9), scale=0.1)
            next_pop.append(child)
        pop = next_pop

    # Save champion of the last round as a convenience
    champion_path = reports_dir / 'champion_round.json'
    if snapshots:
        try:
            last = json.loads(snapshots[-1].read_text(encoding='utf-8'))
            (champion_path).write_text(json.dumps(last.get('top1', {}), indent=2), encoding='utf-8')
        except Exception:
            pass

    return {
        'best': {'fitness': best[1], 'genome': best[0].to_dict()} if best else None,
        'ledger': str(ledger_path),
        'snapshots': [str(p) for p in snapshots],
        'champion': str(champion_path),
    }


def main(argv: List[str] | None = None) -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=10)
    ap.add_argument('--pop', type=int, default=12)
    ap.add_argument('--k', type=int, default=3)
    ap.add_argument('--tau', type=float, default=0.05)
    ap.add_argument('--seed', type=int, default=None)
    ap.add_argument('--run', default=None, help='RUN_ID or path')
    ap.add_argument('--root', default=None, help='Override memory root')
    args = ap.parse_args(argv)

    if args.root:
        os.environ['LLA_MEMORY_ROOT'] = str(Path(args.root).expanduser().resolve())
    res = evolve(rounds=args.rounds, pop_size=args.pop, k=args.k, tau=args.tau, seed=args.seed, run=args.run)
    print(json.dumps(res, indent=2))


if __name__ == '__main__':
    main()
