# SPDX-License-Identifier: MIT
from __future__ import annotations

"""Path resolution utilities.

Resolution order (memory root):
 1) Environment variables.
        - LLA_MEMORY_ROOT has highest authority; when set it is written to stamp and
            becomes the anchor for logs/runs (unless LLA_LOGS_DIR / LLA_RUNS_DIR override).
        - LLA_DATA_ROOT only influences autodetect search space for World*.pt.
 2) paths.yaml (paths.memory_root)
 3) Stamp file (persisted last resolved root) with refresh if a newer checkpoint parent is found.
 4) Autodetect newest World*.pt under candidate roots.
 5) Fallback to ./data/agent_memory.

Logs / Runs directory derivation:
 If explicit env overrides (LLA_LOGS_DIR / LLA_RUNS_DIR) are set — use them.
 Else if paths.yaml supplies logs_dir / runs_dir — use those.
 Else derive as <memory_root>/logs and <memory_root>/runs, with smart_subdir_collapse
 to avoid nested logs/logs when memory_root itself points at .../logs or .../runs.

LLA_MEMORY_ROOT therefore cleanly re-roots artifact emission without touching code.

Cache: resolve_memory_root is cached; call reset_paths_cache() for tests after env tweaks.
"""

import os
import sys
from pathlib import Path
from functools import lru_cache
import glob
import yaml


def _repo_root() -> Path:
    # Assume this file resides under <repo>/living_latent/system/paths.py
    # __file__/.. (system) /.. (living_latent) /.. (repo)
    return Path(__file__).resolve().parents[2]


def _load_paths_cfg() -> dict:
    cfg_path = _repo_root() / 'living_latent' / 'cfg' / 'paths.yaml'
    try:
        data = yaml.safe_load(cfg_path.read_text(encoding='utf-8')) or {}
    except Exception:
        data = {}
    return data.get('paths', {})


def _env_override() -> dict:
    return {
        'LLA_MEMORY_ROOT': os.environ.get('LLA_MEMORY_ROOT'),
        'LLA_DATA_ROOT': os.environ.get('LLA_DATA_ROOT'),
        'LLA_LOGS_DIR': os.environ.get('LLA_LOGS_DIR'),
        'LLA_RUNS_DIR': os.environ.get('LLA_RUNS_DIR'),
    }


def _stamp_path(cfg: dict) -> Path:
    return _repo_root() / str(cfg.get('cache_stamp', '.lla_memory_root'))


def _find_world_checkpoints(search_roots: list[Path], world_glob: str, max_depth: int) -> list[Path]:
    results: list[Path] = []
    for root in search_roots:
        root = root.resolve()
        # search within depth by constructing patterns
        patterns = [str(root / (('*/' * d) + world_glob)) for d in range(max_depth + 1)]
        for pat in patterns:
            for p in glob.glob(pat, recursive=True):
                path = Path(p)
                if path.is_file():
                    results.append(path)
    results = sorted(results, key=lambda p: p.stat().st_mtime, reverse=True)
    return results


def find_world_checkpoints(data_roots: list[str] | list[Path]) -> list[Path]:
    cfg = _load_paths_cfg()
    world_glob = cfg.get('world_glob', '**/World*.pt')
    max_depth = int(cfg.get('search_max_depth', 5))
    roots = [Path(r) for r in data_roots]
    return _find_world_checkpoints(roots, world_glob, max_depth)


@lru_cache(maxsize=1)
def resolve_memory_root() -> Path:
    cfg = _load_paths_cfg()
    env = _env_override()
    repo = _repo_root()
    stamp = _stamp_path(cfg)

    # 1) ENV overrides
    if env.get('LLA_MEMORY_ROOT'):
        mem = Path(env['LLA_MEMORY_ROOT']).expanduser().resolve()
        mem.mkdir(parents=True, exist_ok=True)
        _write_stamp(stamp, mem)
        return mem

    # 2) paths.yaml
    if cfg.get('memory_root'):
        mem = (repo / cfg['memory_root']).expanduser().resolve() if not Path(cfg['memory_root']).is_absolute() else Path(cfg['memory_root']).expanduser().resolve()
        mem.mkdir(parents=True, exist_ok=True)
        _write_stamp(stamp, mem)
        return mem

    # 3) stamp file (with refresh if newer checkpoint is found)
    if stamp.exists():
        try:
            p = Path(stamp.read_text(encoding='utf-8').strip())
            if p:
                p.mkdir(parents=True, exist_ok=True)
                # Try refresh from autodetect
                data_root = env.get('LLA_DATA_ROOT') or cfg.get('data_root')
                roots = []
                if data_root:
                    roots.append((repo / data_root) if not Path(data_root).is_absolute() else Path(data_root))
                roots += [repo, repo / 'logs', repo / 'runs', repo / 'living_latent', repo / 'state']
                candidates = _find_world_checkpoints(roots, cfg.get('world_glob', '**/World*.pt'), int(cfg.get('search_max_depth', 5)))
                if candidates:
                    latest_parent = candidates[0].parent
                    if latest_parent != p:
                        latest_parent.mkdir(parents=True, exist_ok=True)
                        _write_stamp(stamp, latest_parent)
                        return latest_parent
                return p
        except Exception:
            pass

    # 4) auto-detect by latest World*.pt
    data_root = env.get('LLA_DATA_ROOT') or cfg.get('data_root')
    roots = []
    if data_root:
        roots.append((repo / data_root) if not Path(data_root).is_absolute() else Path(data_root))
    # add repo and common folders to search space
    roots += [repo, repo / 'logs', repo / 'runs', repo / 'living_latent', repo / 'state']

    candidates = _find_world_checkpoints(roots, cfg.get('world_glob', '**/World*.pt'), int(cfg.get('search_max_depth', 5)))
    if candidates:
        mem = candidates[0].parent
        mem.mkdir(parents=True, exist_ok=True)
        _write_stamp(stamp, mem)
        return mem

    # 5) fallback
    mem = (repo / 'data' / 'agent_memory').resolve()
    mem.mkdir(parents=True, exist_ok=True)
    _write_stamp(stamp, mem)
    return mem


def _write_stamp(stamp: Path, mem: Path) -> None:
    try:
        stamp.write_text(str(mem), encoding='utf-8')
    except Exception:
        pass


def reset_paths_cache() -> None:
    """Reset cached resolution (used by tests / runtime reconfiguration)."""
    try:
        resolve_memory_root.cache_clear()  # type: ignore[attr-defined]
    except Exception:
        pass


def get_checkpoints_dir() -> Path:
    return resolve_memory_root()


def get_logs_dir() -> Path:
    env = _env_override()
    if env.get('LLA_LOGS_DIR'):
        p = Path(env['LLA_LOGS_DIR']).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    cfg = _load_paths_cfg()
    if cfg.get('logs_dir'):
        p = Path(cfg['logs_dir']) if Path(cfg['logs_dir']).is_absolute() else (_repo_root() / cfg['logs_dir'])
    else:
        mem = resolve_memory_root()
        if bool(cfg.get('smart_subdir_collapse', True)) and mem.name in {'logs', 'runs'}:
            base = mem.parent
            p = base / 'logs'
        else:
            p = mem / 'logs'
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_runs_dir() -> Path:
    env = _env_override()
    if env.get('LLA_RUNS_DIR'):
        p = Path(env['LLA_RUNS_DIR']).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    cfg = _load_paths_cfg()
    if cfg.get('runs_dir'):
        p = Path(cfg['runs_dir']) if Path(cfg['runs_dir']).is_absolute() else (_repo_root() / cfg['runs_dir'])
    else:
        mem = resolve_memory_root()
        if bool(cfg.get('smart_subdir_collapse', True)) and mem.name in {'logs', 'runs'}:
            base = mem.parent
            p = base / 'runs'
        else:
            p = mem / 'runs'
    p.mkdir(parents=True, exist_ok=True)
    return p
