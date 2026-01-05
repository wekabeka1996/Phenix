# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

"""R1-4 Bridge Executor with Guard-based Rollback.

Provides `BridgeExecutor.apply` that:
 1. Emits bridge_exec_start
 2. Takes snapshot anchor (if snapshot interface provided)
 3. Executes bridge via provided callable
 4. Monitors guard window; triggers rollback if thresholds violated
 5. Emits bridge_exec_rollback OR returns PlanResult with status committed

Snapshot interface (optional): must expose take_anchor(name)->anchor_id and rollback(anchor_id).
Metrics context: bridge.ctx.metrics must expose get_homeostasis() & get_delta_efe_baseline().
"""
from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Optional, Callable, Any, Dict

@dataclass
class PlanResult:
    bridge_id: str
    started_ts: float
    anchor_id: Optional[str]
    status: str  # 'committed' | 'rollback'
    reason: Optional[str] = None


class BridgeExecutor:
    def __init__(self, cfg: dict, blackbox_emit: Callable[[dict], None], snapshot: Any | None, is_dry_run: bool = False):
        """R1 BridgeExecutor with optional dry-run early skip.

        Args:
            cfg: full runtime config dict.
            blackbox_emit: callable to append event to blackbox log.
            snapshot: snapshot manager (can be None).
            is_dry_run: whether current run is dry-run / mock (disables real commits if configured).
        """
        self.cfg = cfg
        self.emit = blackbox_emit
        self.snapshot = snapshot
        self.is_dry_run = bool(is_dry_run)
        self.guard = ((cfg.get('r1') or {}).get('rollback_guard') or {
            'guard_window_s': 30,
            'min_homeostasis': 0.95,
            'min_delta_efe': 0.0,
        })

    def apply(self, bridge: Any, act_apply_callable: Callable[[Any], None]) -> PlanResult:
        b_id = getattr(bridge, 'id', str(getattr(bridge, 'uid', 'unknown')))
        started = time.time()
        anchor_id = None
        # Early dry-run skip commit (deterministic based on config flag)
        exec_cfg = ((self.cfg.get('r1') or {}).get('executor') or {})
        if self.is_dry_run and not bool(exec_cfg.get('dry_run_commits', True)):
            self.emit({
                'ts': started,
                'event': 'executor_dry_run_skip_commit',
                'bridge_id': b_id,
                'reason': 'dry_run_commits_disabled'
            })
            return PlanResult(b_id, started, anchor_id, 'skipped', 'dry_run_no_commit')
        if self.snapshot is not None:
            try:
                anchor_id = self.snapshot.take_anchor(f"bridge:{b_id}:{int(started)}")
            except Exception:
                anchor_id = None
        # Emit start event
        self.emit({
            'ts': started,
            'event': 'bridge_exec_start',
            'bridge_id': b_id,
            'score': getattr(bridge, 'score', None),
            'adjusted_score': getattr(bridge, 'adjusted_score', None),
        })
        # Execute
        try:
            act_apply_callable(bridge)
        except Exception as e:  # immediate rollback on execution failure
            if anchor_id and self.snapshot is not None:
                try:
                    self.snapshot.rollback(anchor_id)
                except Exception:
                    pass
            self.emit({
                'ts': time.time(),
                'event': 'bridge_exec_rollback',
                'bridge_id': b_id,
                'reason': 'execution_error',
                'error': str(e),
            })
            return PlanResult(b_id, started, anchor_id, 'rollback', 'execution_error')

        # Guard window monitoring
        guard_until = started + float(self.guard.get('guard_window_s', 30))
        min_homeo = float(self.guard.get('min_homeostasis', 0.95))
        min_dEfe = float(self.guard.get('min_delta_efe', 0.0))
        worst_homeo = 1.0
        min_delta_efe_seen = 1e9

        metrics = getattr(getattr(bridge, 'ctx', None), 'metrics', None)
        get_homeo = getattr(metrics, 'get_homeostasis', None)
        get_dEfe = getattr(metrics, 'get_delta_efe_baseline', None)
        while time.time() < guard_until and callable(get_homeo) and callable(get_dEfe):
            try:
                cur_homeo = float(get_homeo())
                delta_efe = float(get_dEfe())
            except Exception:
                break
            worst_homeo = min(worst_homeo, cur_homeo)
            min_delta_efe_seen = min(min_delta_efe_seen, delta_efe)
            if cur_homeo < min_homeo or delta_efe < min_dEfe:
                if anchor_id and self.snapshot is not None:
                    try:
                        self.snapshot.rollback(anchor_id)
                    except Exception:
                        pass
                self.emit({
                    'ts': time.time(),
                    'event': 'bridge_exec_rollback',
                    'bridge_id': b_id,
                    'reason': 'guard_threshold',
                    'guard_metrics': {
                        'worst_homeostasis': worst_homeo,
                        'min_delta_efe': min_delta_efe_seen,
                    }
                })
                return PlanResult(b_id, started, anchor_id, 'rollback', 'guard_threshold')
            time.sleep(0.2)
        return PlanResult(b_id, started, anchor_id, 'committed')

__all__ = ["BridgeExecutor", "PlanResult"]
