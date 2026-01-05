# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

# WRITE PRODUCTION-READY PYTHON 3.11.
# Follow this SPEC EXACTLY. type hints, pydantic for IO, no global state, dependency injection via constructors.
# Logging: structured JSON to logs/*.jsonl. Handle exceptions gracefully and continue.
# Every public function must have a docstring with Args/Returns/Raises.

import logging
import time
import json
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from pydantic import BaseModel
from dataclasses import dataclass

from .telemetry import Observation

log = logging.getLogger(__name__)

class EffectsConfig(BaseModel):
    """Configuration for effects tracking and ledger management."""
    enabled: bool = True
    ledger_path: str = "logs/effects_ledger.jsonl"
    snapshot_timeout_s: float = 30.0
    impact_window_s: float = 60.0
    min_impact_threshold: float = 0.1
    rollback_enabled: bool = False

class SystemSnapshot(BaseModel):
    """Snapshot of system state at a point in time."""
    timestamp: float
    gpu_temp_c: float
    gpu_util_pct: float
    gpu_mem_used_gb: float
    cpu_load_pct: float
    io_wait_pct: float
    fan_pct: float
    throttling: bool
    
    @classmethod
    def from_observation(cls, obs: Observation) -> 'SystemSnapshot':
        """Create snapshot from telemetry observation."""
        return cls(
            timestamp=obs.ts,
            gpu_temp_c=obs.gpu_temp_c,
            gpu_util_pct=obs.gpu_util_pct,
            gpu_mem_used_gb=obs.gpu_mem_used_gb,
            cpu_load_pct=obs.cpu_load_pct,
            io_wait_pct=obs.io_wait_pct,
            fan_pct=obs.fan_pct,
            throttling=obs.throttling
        )

class ActionImpactAssessment(BaseModel):
    """Assessment of an action's impact on system state."""
    action_name: str
    execution_timestamp: float
    before_snapshot: SystemSnapshot
    after_snapshot: Optional[SystemSnapshot] = None
    
    # Impact metrics
    temp_delta_c: Optional[float] = None
    util_delta_pct: Optional[float] = None
    load_delta_pct: Optional[float] = None
    fan_delta_pct: Optional[float] = None
    throttling_changed: Optional[bool] = None
    
    # Assessment results
    effectiveness_score: Optional[float] = None  # 0.0 to 1.0
    negative_side_effects: Optional[bool] = None
    rollback_recommended: Optional[bool] = None
    impact_magnitude: Optional[str] = None  # "low", "medium", "high"
    
    def calculate_impact(self) -> None:
        """Calculate impact metrics from before/after snapshots."""
        if self.after_snapshot is None:
            return
            
        self.temp_delta_c = self.after_snapshot.gpu_temp_c - self.before_snapshot.gpu_temp_c
        self.util_delta_pct = self.after_snapshot.gpu_util_pct - self.before_snapshot.gpu_util_pct
        self.load_delta_pct = self.after_snapshot.cpu_load_pct - self.before_snapshot.cpu_load_pct
        self.fan_delta_pct = self.after_snapshot.fan_pct - self.before_snapshot.fan_pct
        self.throttling_changed = (self.after_snapshot.throttling != self.before_snapshot.throttling)
        
        # Assess effectiveness based on action type
        if self.action_name in ['de_risk_high_temp', 'cooloff_sleep']:
            # For cooling actions, lower temp = more effective
            if self.temp_delta_c is not None and self.temp_delta_c < 0:
                self.effectiveness_score = min(1.0, abs(self.temp_delta_c) / 10.0)  # Scale by 10°C max expected
            else:
                self.effectiveness_score = 0.0
        elif self.action_name == 'renice_processes':
            # For load reduction, lower CPU load = more effective  
            if self.load_delta_pct is not None and self.load_delta_pct < 0:
                self.effectiveness_score = min(1.0, abs(self.load_delta_pct) / 50.0)  # Scale by 50% max expected
            else:
                self.effectiveness_score = 0.0
        else:
            # For no_op or unknown actions
            self.effectiveness_score = 0.0
            
        # Detect negative side effects
        self.negative_side_effects = (
            (self.temp_delta_c is not None and self.temp_delta_c > 5.0) or  # Unexpected temp increase
            (self.throttling_changed and self.after_snapshot.throttling)     # Started throttling
        )
        
        # Determine impact magnitude
        max_delta = max(
            abs(self.temp_delta_c or 0),
            abs(self.util_delta_pct or 0) / 10,  # Scale util to similar range as temp
            abs(self.load_delta_pct or 0) / 10   # Scale load to similar range as temp
        )
        
        if max_delta < 2.0:
            self.impact_magnitude = "low"
        elif max_delta < 5.0:
            self.impact_magnitude = "medium"
        else:
            self.impact_magnitude = "high"
            
        # Recommend rollback for ineffective actions with negative side effects
        self.rollback_recommended = (
            self.effectiveness_score is not None and 
            self.effectiveness_score < 0.2 and 
            self.negative_side_effects is True
        )

class EffectsLedger:
    """
    Tracks action effects with before/after snapshots and impact assessment.
    Provides learning data and rollback decision support.
    """
    
    def __init__(self, config: EffectsConfig):
        """
        Initialize the effects ledger.
        
        Args:
            config: Effects tracking configuration
        """
        self.config = config
        self.ledger_path = Path(config.ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Active tracking for pending assessments
        self.pending_assessments: Dict[str, ActionImpactAssessment] = {}
        
        log.info(f"EffectsLedger initialized: enabled={config.enabled}, "
                f"ledger_path={config.ledger_path}, impact_window={config.impact_window_s}s")
    
    def record_action_start(self, action_name: str, before_obs: Observation) -> str:
        """
        Record the start of an action with before snapshot.
        
        Args:
            action_name: Name of the action being executed
            before_obs: System observation before action execution
            
        Returns:
            Assessment ID for tracking this action
        """
        if not self.config.enabled:
            return ""
            
        assessment_id = f"{action_name}_{int(time.time() * 1000)}"
        
        before_snapshot = SystemSnapshot.from_observation(before_obs)
        assessment = ActionImpactAssessment(
            action_name=action_name,
            execution_timestamp=time.time(),
            before_snapshot=before_snapshot
        )
        
        self.pending_assessments[assessment_id] = assessment
        
        log.info(f"Action tracking started: {assessment_id} - {action_name}")
        return assessment_id
    
    def record_action_complete(self, assessment_id: str, after_obs: Observation) -> Optional[ActionImpactAssessment]:
        """
        Record the completion of an action with after snapshot and impact assessment.
        
        Args:
            assessment_id: ID returned from record_action_start
            after_obs: System observation after action execution
            
        Returns:
            Completed assessment with impact analysis, or None if not found
        """
        if not self.config.enabled or assessment_id not in self.pending_assessments:
            return None
            
        assessment = self.pending_assessments.pop(assessment_id)
        assessment.after_snapshot = SystemSnapshot.from_observation(after_obs)
        assessment.calculate_impact()
        
        # Write to ledger
        self._write_to_ledger(assessment)
        
        log.info(f"Action tracking completed: {assessment_id} - "
                f"effectiveness={assessment.effectiveness_score:.2f}, "
                f"magnitude={assessment.impact_magnitude}, "
                f"rollback_rec={assessment.rollback_recommended}")
        
        return assessment
    
    def cleanup_stale_assessments(self) -> None:
        """Clean up assessments that never got completion snapshots."""
        current_time = time.time()
        stale_ids = []
        
        for assessment_id, assessment in self.pending_assessments.items():
            if current_time - assessment.execution_timestamp > self.config.snapshot_timeout_s:
                stale_ids.append(assessment_id)
                log.warning(f"Cleaning up stale assessment: {assessment_id}")
        
        for stale_id in stale_ids:
            del self.pending_assessments[stale_id]
    
    def get_action_history(self, action_name: str, limit: int = 10) -> List[ActionImpactAssessment]:
        """
        Get recent history for a specific action type.
        
        Args:
            action_name: Name of action to get history for
            limit: Maximum number of records to return
            
        Returns:
            List of recent assessments for this action type
        """
        if not self.config.enabled or not self.ledger_path.exists():
            return []
            
        history = []
        try:
            with open(self.ledger_path, 'r') as f:
                lines = f.readlines()
                
            # Read from end of file backwards for most recent entries
            for line in reversed(lines[-limit*3:]):  # Read more lines to filter
                try:
                    data = json.loads(line.strip())
                    if data.get('action_name') == action_name:
                        assessment = ActionImpactAssessment.model_validate(data)
                        history.append(assessment)
                        if len(history) >= limit:
                            break
                except (json.JSONDecodeError, ValueError) as e:
                    log.warning(f"Failed to parse ledger line: {e}")
                    continue
                    
        except FileNotFoundError:
            log.info(f"Ledger file not found: {self.ledger_path}")
        except Exception as e:
            log.error(f"Error reading action history: {e}")
            
        return list(reversed(history))  # Return in chronological order
    
    def get_effectiveness_stats(self, action_name: str, window_hours: int = 24) -> Dict[str, Any]:
        """
        Get effectiveness statistics for an action over a time window.
        
        Args:
            action_name: Name of action to analyze
            window_hours: Time window in hours to analyze
            
        Returns:
            Dictionary with effectiveness statistics
        """
        cutoff_time = time.time() - (window_hours * 3600)
        history = self.get_action_history(action_name, limit=100)
        
        # Filter to time window
        recent_history = [
            a for a in history 
            if a.execution_timestamp >= cutoff_time and a.effectiveness_score is not None
        ]
        
        if not recent_history:
            return {
                'action_name': action_name,
                'window_hours': window_hours,
                'sample_size': 0,
                'avg_effectiveness': 0.0,
                'success_rate': 0.0,
                'rollback_rate': 0.0
            }
        
        effectiveness_scores = [a.effectiveness_score for a in recent_history if a.effectiveness_score is not None]
        successful_actions = [a for a in recent_history if (a.effectiveness_score or 0) >= 0.5]
        rollback_recommended = [a for a in recent_history if a.rollback_recommended]
        
        return {
            'action_name': action_name,
            'window_hours': window_hours,
            'sample_size': len(recent_history),
            'avg_effectiveness': sum(effectiveness_scores) / len(effectiveness_scores) if effectiveness_scores else 0.0,
            'success_rate': len(successful_actions) / len(recent_history),
            'rollback_rate': len(rollback_recommended) / len(recent_history),
            'recent_assessments': len(recent_history)
        }
    
    def _write_to_ledger(self, assessment: ActionImpactAssessment) -> None:
        """Write assessment to the effects ledger file."""
        try:
            with open(self.ledger_path, 'a') as f:
                f.write(assessment.model_dump_json() + '\n')
        except Exception as e:
            log.error(f"Failed to write to effects ledger: {e}")