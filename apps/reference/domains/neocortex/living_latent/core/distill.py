# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from living_latent.system.paths import get_logs_dir, get_runs_dir
from .genome import Genome
from .policy_prior import fit_linear_prior, LinearPrior


def _read_champion(logs_dir: Path) -> Dict[str, Any] | None:
    champ = logs_dir / 'evolve' / 'champion_round.json'
    if champ.exists():
        try:
            return json.loads(champ.read_text(encoding='utf-8'))
        except Exception:
            return None
    return None


def _collect_features(run_dir: Path) -> Tuple[List[List[float]], List[float]]:
    """Very small mock feature collector: reads bridges/*.json and extracts features and dJ.
    Returns X, y where y corresponds to Delta-J (here: J itself as proxy).
    """
    X: List[List[float]] = []
    y: List[float] = []
    bdir = run_dir / 'logs' / 'bridges'
    if not bdir.exists():
        return X, y
    for fp in sorted(bdir.glob('*.json')):
        try:
            rec = json.loads(fp.read_text(encoding='utf-8'))
        except Exception:
            continue
        # features: [dJ, dEFE, dEmp, dHomeo] if present, else zeros
        feats = [0.0, 0.0, 0.0, 0.0]
        for i, k in enumerate(['dJ', 'dEFE', 'dEmp', 'dHomeo']):
            if isinstance(rec, dict) and k in rec:
                try:
                    feats[i] = float(rec[k])
                except Exception:
                    feats[i] = 0.0
        # target proxy: J (or mean of J_samples)
        target = None
        if isinstance(rec, dict):
            if 'J' in rec:
                try:
                    target = float(rec['J'])
                except Exception:
                    target = None
            elif 'J_samples' in rec and isinstance(rec['J_samples'], list) and rec['J_samples']:
                target = float(sum(rec['J_samples']) / len(rec['J_samples']))
        if target is None:
            continue
        X.append(feats)
        y.append(target)
    return X, y


def export_policy_prior(run: str | None = None, round_id: int | None = None, use_last: bool = True) -> Dict[str, Any]:
    logs_root = Path(get_logs_dir())
    runs_root = Path(get_runs_dir())
    # decide run directory
    run_dir = None
    if run:
        p = Path(run)
        run_dir = p if p.is_dir() else (runs_root / run)
    else:
        # default to last run from evolution if present in logs path
        run_dir = logs_root.parent  # fallback to memory root context
    if run_dir is None or not run_dir.exists():
        raise FileNotFoundError("Run directory not found")

    # Load champion hyperparams if available
    champion = _read_champion(logs_root)
    hparams = {}
    if champion and isinstance(champion, dict) and 'genome' in champion:
        hparams = champion['genome']

    X, y = _collect_features(run_dir)
    if len(X) < 4:
        # fallback synthetic
        X = [[0.0, 0.0, 0.0, 0.0], [0.5, -0.2, 0.1, 0.0], [-0.1, 0.3, 0.2, -0.2], [0.2, 0.2, -0.1, 0.1]]
        y = [0.0, 0.2, -0.1, 0.05]

    prior = fit_linear_prior(X, y)

    out_dir = logs_root / 'evolve'
    out_dir.mkdir(parents=True, exist_ok=True)
    # save model
    state = prior.state_dict()
    (out_dir / 'policy_prior.pt').write_text(json.dumps(state), encoding='utf-8')
    # save metadata
    meta = {
        'model': 'LinearPrior',
        'features': ['dJ', 'dEFE', 'dEmp', 'dHomeo'],
        'target': 'J (proxy)',
        'champion_hparams': hparams,
        'samples': len(X),
    }
    (out_dir / 'policy_prior.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    return {'model_path': str(out_dir / 'policy_prior.pt'), 'meta_path': str(out_dir / 'policy_prior.json')}


def main(argv: List[str] | None = None) -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', default=None)
    ap.add_argument('--round', type=int, default=None)
    ap.add_argument('--last', action='store_true', default=False)
    ap.add_argument('--root', default=None)
    args = ap.parse_args(argv)
    if args.root:
        os.environ['LLA_MEMORY_ROOT'] = str(Path(args.root).expanduser().resolve())
    res = export_policy_prior(run=args.run, round_id=args.round, use_last=args.last)
    print(json.dumps(res, indent=2))


if __name__ == '__main__':
    main()
