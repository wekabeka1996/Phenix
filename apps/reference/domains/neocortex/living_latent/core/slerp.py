# SPDX-License-Identifier: MIT
from __future__ import annotations
from dataclasses import dataclass, asdict
import numpy as np
import time, json
from pathlib import Path
from typing import Callable


# HF4: runtime cached last valence
_LATEST_VALENCE = 0.0


@dataclass
class BridgePlan:
    points: np.ndarray
    J: float
    valid: bool
    meta: dict


def _normalize(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    if n == 0:
        return v
    return v / n


def _slerp(p0: np.ndarray, p1: np.ndarray, t: float) -> np.ndarray:
    # unit vectors assumed
    dot = np.clip(np.dot(p0, p1), -1.0, 1.0)
    if dot > 0.9999:
        return (1 - t) * p0 + t * p1
    theta = np.arccos(dot)
    return (np.sin((1 - t) * theta) / np.sin(theta)) * p0 + (np.sin(t * theta) / np.sin(theta)) * p1


def plan_slerp(z_start: np.ndarray, z_goal: np.ndarray, cfg: dict, proxies: dict | None = None) -> BridgePlan:
    try:
        steps = int(cfg.get('steps', 16))
    except Exception:
        steps = 16
    p0 = _normalize(np.asarray(z_start, dtype=float))
    p1 = _normalize(np.asarray(z_goal, dtype=float))
    points = []
    for i in range(steps + 1):
        t = i / float(steps)
        pt = _slerp(p0, p1, t)
        points.append(pt.tolist())

    pts = np.array(points)
    # compute energy
    diffs = np.diff(pts, axis=0)
    energy = float(np.sum(diffs ** 2))

    # proxies
    proxies = proxies or {}
    efe_fn = proxies.get('efe', lambda pts: 0.0)
    ood_fn = proxies.get('ood', lambda pts: 0.0)
    val_fn = proxies.get('valence', lambda pts: 0.0)

    efe = float(efe_fn(pts))
    ood = float(ood_fn(pts))
    val = float(val_fn(pts))

    weights = cfg.get('weights', {}) if isinstance(cfg, dict) else {}
    a = float(weights.get('alpha', 1.0))
    b = float(weights.get('beta', 1.0))
    g = float(weights.get('gamma', 0.1))
    d = float(weights.get('delta', 0.5))

    J0 = a * efe + b * ood + g * energy - d * val

    # one-step guided improve: simple smoothing step that reduces energy
    pts2 = pts.copy()
    if pts2.shape[0] >= 3:
        # simple Laplacian smoothing on interior points
        for i in range(1, pts2.shape[0] - 1):
            pts2[i] = 0.5 * (pts2[i - 1] + pts2[i + 1])

    diffs2 = np.diff(pts2, axis=0)
    energy2 = float(np.sum(diffs2 ** 2))
    efe2 = float(efe_fn(pts2))
    ood2 = float(ood_fn(pts2))
    val2 = float(val_fn(pts2))
    J1 = a * efe2 + b * ood2 + g * energy2 - d * val2

    meta = {
        'energy': energy,
        'energy_after': energy2,
        'delta_J': float(J1 - J0),
        'efe': efe,
        'ood': ood,
        'valence': val,
    }

    # persist
    saved_path = ''
    try:
        ts = time.strftime('%Y%m%d_%H%M%S')
        run_dir = Path('runs') / ts / 'bridges'
        run_dir.mkdir(parents=True, exist_ok=True)
        outp = run_dir / f'bridge_{ts}.json'
        dump = {'points': pts2.tolist(), 'J': float(J1), 'meta': meta}
        # Best-effort: compute CVaR tail and annotate meta before persisting (non-fatal)
        try:
            from living_latent.risk.cvar import cvar_tail
            from living_latent.risk.sampler import draw_risk_samples
            try:
                import yaml as _yaml
                rconf_path = Path('living_latent/cfg/risk.yaml')
                if rconf_path.exists():
                    rconf = _yaml.safe_load(rconf_path.read_text(encoding='utf-8')) or {}
                else:
                    rconf = {}
            except Exception:
                rconf = {}

            _RISK_ALPHA = float(rconf.get('alpha', 0.95) or 0.95)
            _RISK_LAMBDA = float(rconf.get('lambda', 0.5) or 0.5)
            _RISK_NS = int(rconf.get('samples', 256) or 256)
            _RISK_MODE = str(rconf.get('mode', 'mc')).lower()
            seed = int(time.time()) & 0x7fffffff
            samples = draw_risk_samples(meta, n=_RISK_NS, seed=seed, mode=_RISK_MODE)
            cvar_val = float(cvar_tail(samples, _RISK_ALPHA))
            dump['J'] = float(dump.get('J', 0.0)) + (_RISK_LAMBDA * cvar_val)
            dump['meta']['cvar'] = cvar_val
            dump['meta']['cvar_alpha'] = _RISK_ALPHA
            dump['meta']['cvar_lambda'] = _RISK_LAMBDA
            dump['meta']['risk_mode'] = _RISK_MODE
            dump['meta']['risk_ns'] = int(_RISK_NS)
        except Exception:
            # sampling or cvar computation failed; continue without risk fields
            pass
        # Ensure valence present (HF4)
        try:
            dump.setdefault('meta', {})
            dump['meta'].setdefault('valence', float(_LATEST_VALENCE))
        except Exception:
            pass

        # --- R3-B: realtime safety thresholds & alerts ---
        try:
            import yaml as _yaml
            _sconf_path = Path('living_latent/cfg/safety.yaml')
            if _sconf_path.exists():
                _SAFETY_CFG = _yaml.safe_load(_sconf_path.read_text(encoding='utf-8')) or {}
            else:
                _SAFETY_CFG = {}
        except Exception:
            _SAFETY_CFG = {}

        _LIM = _SAFETY_CFG.get('limits', {}) or {}
        _HARD_STOP = bool(_SAFETY_CFG.get('hard_stop', False))

        def _f(x, d=0.0):
            try:
                v = float(x)
                if v != v or v == float('inf') or v == float('-inf'):
                    return d
                return v
            except Exception:
                return d

        def _safety_check(meta: dict) -> list:
            flags = []
            cvar = _f(meta.get('cvar'))
            val = _f(meta.get('valence'))
            pval = _f(meta.get('arma_lb_pval'), 1.0)
            if cvar > _f(_LIM.get('cvar_max'), 1e9):
                flags.append('S_CVAR')
            if val > _f(_LIM.get('valence_max'), 1e9):
                flags.append('S_VALENCE')
            if pval < _f(_LIM.get('arma_pval_min'), 0.0):
                flags.append('S_ARMA')
            return flags

        try:
            s_flags = _safety_check(dump.get('meta', {}))
            if s_flags:
                try:
                    from living_latent.telemetry.blackbox import log_event
                    log_event('SAFETY_TRIP', {'flags': s_flags, 'meta': {k: dump.get('meta', {}).get(k) for k in ('cvar','valence','arma_lb_pval')}})
                except Exception:
                    # best-effort: append to blackbox log
                    try:
                        _bbp = run_dir.parent / 'blackbox.jsonl'
                        with _bbp.open('a', encoding='utf-8') as _fbb:
                            _fbb.write(json.dumps({'event':'SAFETY_TRIP','flags':s_flags,'meta':{k: dump.get('meta',{}).get(k) for k in ('cvar','valence','arma_lb_pval')}}) + '\n')
                    except Exception:
                        pass
                if _HARD_STOP:
                    raise RuntimeError(f"SAFETY_TRIP: {s_flags}")
        except Exception:
            pass
        outp.write_text(json.dumps(dump), encoding='utf-8')
        saved_path = str(outp)
        # run ARMA diagnostics (best-effort)
        try:
            from living_latent.validators.pipeline import bridge_arma_diagnostics
            diag_out = bridge_arma_diagnostics(saved_path, out_run_logs=str(Path('runs') / ts / 'arma_diag.jsonl'))
            # merge into meta
            if diag_out:
                meta['arma_best_p'] = diag_out.get('arma_best_p')
                meta['arma_lb_pval'] = diag_out.get('arma_lb_pval')
                meta['spec_peak_freq'] = diag_out.get('spec_peak_freq')
                meta['spec_peak_val'] = diag_out.get('spec_peak_val')
        except Exception:
            pass
    except Exception:
        saved_path = ''

    return BridgePlan(points=pts2, J=float(J1), valid=True, meta={**meta, 'saved': saved_path})
