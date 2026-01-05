# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

"""R2 Attractors construction.

SPEC: docs/R2_acceptance.md (Attractors) – skeleton implementation.

Build attractors from top-K bridges (by dJ) using simple k-means in feature space.
Fallbacks keep code dependency-light (no sklearn) per project conventions.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Sequence
import math, random

@dataclass
class Attractor:
    id: str
    center: list[float]
    members: list[str]  # bridge_ids
    stats: dict

# +++ ADD: simple deterministic k-means (Lloyd) implementation

def _kmeans(X: Sequence[Sequence[float]], k: int, max_iter: int = 50, seed: int = 42):
    if k <= 0:
        raise ValueError("k must be >0")
    n = len(X)
    if n == 0:
        return [], []
    dim = len(X[0]) if X[0] else 0
    rnd = random.Random(seed)
    if k > n:
        k = n
    # Init: choose k distinct points
    init_idx = list(range(n))
    rnd.shuffle(init_idx)
    centers = [list(X[i]) for i in init_idx[:k]]
    labels = [0]*n
    def _dist2(a,b):
        return sum((ai-bi)**2 for ai,bi in zip(a,b))
    for _ in range(max_iter):
        changed = False
        # assign
        for i, x in enumerate(X):
            best = 0; best_d = math.inf
            for ci,c in enumerate(centers):
                d = _dist2(x,c)
                if d < best_d:
                    best_d = d; best = ci
            if labels[i] != best:
                labels[i] = best; changed = True
        # recompute
        sums = [[0.0]*dim for _ in centers]
        counts = [0]*len(centers)
        for lab, x in zip(labels, X):
            counts[lab] += 1
            for j,v in enumerate(x):
                sums[lab][j] += v
        for ci in range(len(centers)):
            if counts[ci] > 0:
                centers[ci] = [s/counts[ci] for s in sums[ci]]
            # else keep old center
        if not changed:
            break
    return labels, centers


def build_attractors(bridges_eval: List[Dict[str, Any]], cfg: Dict[str, Any]) -> List[Attractor]:
    """Construct attractors from top-K bridges by dJ.

    Steps:
      1. Sample top_k_source by descending dJ.
      2. Extract feature matrix (cfg.r2.attractors.features).
      3. Cluster via k-means (skeleton; future: plug GMM/DBSCAN via config method).
      4. Package Attractor objects (id=A<cluster_id>). Skips clusters < min_cluster_size.
    """
    if not bridges_eval:
        return []
    r2c = (cfg.get('r2') or {}).get('attractors') or {}
    top_k = int(r2c.get('top_k_source', 100) or 100)
    feats = r2c.get('features') or ['dJ','dEFE','dEmp','dHomeo']
    min_cluster_size = int(r2c.get('min_cluster_size', 1) or 1)
    rows = sorted(bridges_eval, key=lambda x: x.get('dJ',0.0), reverse=True)[:top_k]
    if not rows:
        return []
    X = [[float(r.get(f,0.0)) for f in feats] for r in rows]
    ids = [r.get('bridge_id') for r in rows]
    method = r2c.get('method','kmeans')
    k = int(r2c.get('k',3) or 3)
    if method != 'kmeans':
        # Future: implement alt methods; fallback to kmeans
        method = 'kmeans'
    labels, centers = _kmeans(X, k)
    clusters: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        clusters.setdefault(lab, []).append(i)
    out: list[Attractor] = []
    for lab, idxs in clusters.items():
        if len(idxs) < min_cluster_size:
            continue
        members = [ids[i] for i in idxs]
        center = centers[lab]
        out.append(Attractor(id=f"A{lab}", center=center, members=members, stats={'size': len(members), 'features': feats}))
    return out
