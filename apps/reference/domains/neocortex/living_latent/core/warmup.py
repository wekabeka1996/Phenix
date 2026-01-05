# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

# WRITE PRODUCTION-READY PYTHON 3.11.
# Follow this SPEC EXACTLY. type hints, pydantic for IO, no global state, dependency injection via constructors.
# Logging: structured JSON to logs/*.jsonl. Handle exceptions gracefully and continue.
# Every public function must have a docstring with Args/Returns/Raises.

"""
TASK 12: Warmup Policy Gradual Hardening

Implements progressive parameter adjustment from smoke → staging → production
with automatic progression gates based on system stability metrics.
"""

import logging
import time
import json
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from pydantic import BaseModel
from enum import Enum
from dataclasses import dataclass

log = logging.getLogger(__name__)

class WarmupStage(str, Enum):
    """Stages of progressive hardening."""
    SMOKE = "smoke"           # Initial relaxed parameters
    STAGING = "staging"       # Intermediate hardening
    PRODUCTION = "production" # Final strict parameters

class WarmupConfig(BaseModel):
    """Configuration for warmup policy gradual hardening."""
    enabled: bool = True
    initial_stage: WarmupStage = WarmupStage.SMOKE
    progression_file: str = "logs/warmup_progression.json"
    
    # Stage progression criteria
    min_runtime_s: float = 300.0        # Minimum time in stage before progression
    min_decisions: int = 10             # Minimum decisions before progression
    min_success_rate: float = 0.8       # Minimum action success rate
    max_safety_violations: int = 2      # Maximum safety violations allowed
    stability_window_s: float = 180.0   # Window for stability assessment
    
    # Auto-progression settings
    auto_progression_enabled: bool = True
    max_stage_duration_s: float = 1800.0  # Max time before forced progression (30 min)
    rollback_on_failure: bool = True       # Rollback to previous stage on failure

class StageParameters(BaseModel):
    """Parameters for a specific warmup stage."""
    stage: WarmupStage
    
    # Action policy parameters
    min_action_ratio: float
    max_action_frequency: float  # actions per minute
    
    # Safety parameters  
    safety_multiplier: float     # multiplier for safety thresholds
    rate_limit_multiplier: float # multiplier for rate limits
    
    # EFE/Empowerment thresholds
    efe_action_threshold: float
    empowerment_threshold: float
    
    # Description for logging
    description: str

class ProgressionGate(BaseModel):
    """Gate criteria for progressing to next stage."""
    from_stage: WarmupStage
    to_stage: WarmupStage
    
    # Stability metrics required
    min_runtime_s: float
    min_decisions: int
    min_success_rate: float
    max_violations: int
    
    # Optional effectiveness criteria
    min_avg_effectiveness: Optional[float] = None
    max_rollback_rate: Optional[float] = None

class WarmupState(BaseModel):
    """Current state of warmup progression."""
    current_stage: WarmupStage
    stage_start_time: float
    total_decisions: int = 0
    successful_decisions: int = 0
    safety_violations: int = 0
    last_updated: float
    
    # Progression tracking
    progression_history: List[Dict[str, Any]] = []
    auto_progression_disabled: bool = False
    
    # Stage statistics
    stage_stats: Dict[str, Any] = {}

class WarmupPolicy:
    """
    Manages gradual hardening of action parameters from smoke → staging → production.
    Provides automatic progression gates and rollback capabilities.
    """
    
    def __init__(self, config: WarmupConfig):
        """
        Initialize warmup policy manager.
        
        Args:
            config: Warmup configuration
        """
        self.config = config
        self.state_file = Path(config.progression_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Define stage parameters
        self.stage_parameters = {
            WarmupStage.SMOKE: StageParameters(
                stage=WarmupStage.SMOKE,
                min_action_ratio=0.1,        # Very relaxed - allow mostly no_op
                max_action_frequency=30.0,   # High frequency for testing
                safety_multiplier=0.8,       # Relaxed safety thresholds
                rate_limit_multiplier=3.0,   # 3x higher rate limits
                efe_action_threshold=80.0,   # Lower threshold = more actions
                empowerment_threshold=0.5,   # Lower threshold = more exploration
                description="Initial smoke testing with relaxed parameters"
            ),
            WarmupStage.STAGING: StageParameters(
                stage=WarmupStage.STAGING,
                min_action_ratio=0.3,        # Moderate action requirement
                max_action_frequency=15.0,   # Moderate frequency
                safety_multiplier=0.9,       # Slightly relaxed safety
                rate_limit_multiplier=1.5,   # 1.5x higher rate limits
                efe_action_threshold=100.0,  # Moderate threshold
                empowerment_threshold=0.6,   # Moderate exploration
                description="Staging with moderate parameter hardening"
            ),
            WarmupStage.PRODUCTION: StageParameters(
                stage=WarmupStage.PRODUCTION,
                min_action_ratio=0.5,        # Strict action requirement
                max_action_frequency=8.0,    # Conservative frequency
                safety_multiplier=1.0,       # Full safety thresholds
                rate_limit_multiplier=1.0,   # Standard rate limits
                efe_action_threshold=120.0,  # High threshold = fewer actions
                empowerment_threshold=0.7,   # Higher exploration threshold
                description="Production with strict safety parameters"
            )
        }
        
        # Define progression gates
        self.progression_gates = [
            ProgressionGate(
                from_stage=WarmupStage.SMOKE,
                to_stage=WarmupStage.STAGING,
                min_runtime_s=300.0,     # 5 minutes minimum
                min_decisions=10,        # At least 10 decisions
                min_success_rate=0.7,    # 70% success rate
                max_violations=3,        # Max 3 safety violations
                min_avg_effectiveness=0.3  # 30% average effectiveness
            ),
            ProgressionGate(
                from_stage=WarmupStage.STAGING,
                to_stage=WarmupStage.PRODUCTION,
                min_runtime_s=600.0,     # 10 minutes minimum
                min_decisions=20,        # At least 20 decisions
                min_success_rate=0.8,    # 80% success rate
                max_violations=1,        # Max 1 safety violation
                min_avg_effectiveness=0.5, # 50% average effectiveness
                max_rollback_rate=0.2    # Max 20% rollback rate
            )
        ]
        
        # Load or initialize state
        self.state = self._load_state()
        
        log.info(f"WarmupPolicy initialized: enabled={config.enabled}, "
                f"current_stage={self.state.current_stage}, "
                f"auto_progression={config.auto_progression_enabled}")
    
    def get_current_parameters(self) -> StageParameters:
        """
        Get parameters for current warmup stage.
        
        Returns:
            Current stage parameters
        """
        return self.stage_parameters[self.state.current_stage]
    
    def record_decision(self, action_name: str, success: bool, safety_violation: bool = False) -> None:
        """
        Record a decision outcome for progression tracking.
        
        Args:
            action_name: Name of the action taken
            success: Whether the action was successful
            safety_violation: Whether a safety violation occurred
        """
        if not self.config.enabled:
            return
            
        self.state.total_decisions += 1
        if success:
            self.state.successful_decisions += 1
        if safety_violation:
            self.state.safety_violations += 1
            
        self.state.last_updated = time.time()
        
        # Update stage statistics
        stage_key = self.state.current_stage.value
        if stage_key not in self.state.stage_stats:
            self.state.stage_stats[stage_key] = {
                'decisions': 0,
                'successes': 0,
                'violations': 0,
                'actions': {}
            }
        
        stage_stats = self.state.stage_stats[stage_key]
        stage_stats['decisions'] += 1
        if success:
            stage_stats['successes'] += 1
        if safety_violation:
            stage_stats['violations'] += 1
            
        # Track action frequency
        if action_name not in stage_stats['actions']:
            stage_stats['actions'][action_name] = 0
        stage_stats['actions'][action_name] += 1
        
        self._save_state()
        
        log.debug(f"Decision recorded: {action_name}, success={success}, "
                 f"violation={safety_violation}, stage={self.state.current_stage}")
    
    def check_progression_eligibility(self, effectiveness_stats: Optional[Dict[str, float]] = None) -> Tuple[bool, str]:
        """
        Check if current stage is eligible for progression to next stage.
        
        Args:
            effectiveness_stats: Optional effectiveness statistics from effects ledger
            
        Returns:
            Tuple of (eligible, reason)
        """
        if not self.config.enabled or not self.config.auto_progression_enabled:
            return False, "Auto-progression disabled"
            
        if self.state.auto_progression_disabled:
            return False, "Auto-progression manually disabled"
            
        if self.state.current_stage == WarmupStage.PRODUCTION:
            return False, "Already at production stage"
            
        # Find applicable gate
        gate = None
        for g in self.progression_gates:
            if g.from_stage == self.state.current_stage:
                gate = g
                break
                
        if not gate:
            return False, f"No progression gate defined for {self.state.current_stage}"
        
        current_time = time.time()
        stage_runtime = current_time - self.state.stage_start_time
        
        # Check basic criteria
        if stage_runtime < gate.min_runtime_s:
            return False, f"Insufficient runtime: {stage_runtime:.0f}s < {gate.min_runtime_s:.0f}s required"
            
        if self.state.total_decisions < gate.min_decisions:
            return False, f"Insufficient decisions: {self.state.total_decisions} < {gate.min_decisions} required"
            
        # Check success rate
        if self.state.total_decisions > 0:
            success_rate = self.state.successful_decisions / self.state.total_decisions
            if success_rate < gate.min_success_rate:
                return False, f"Low success rate: {success_rate:.2f} < {gate.min_success_rate:.2f} required"
        
        # Check safety violations
        if self.state.safety_violations > gate.max_violations:
            return False, f"Too many violations: {self.state.safety_violations} > {gate.max_violations} allowed"
        
        # Check optional effectiveness criteria
        if gate.min_avg_effectiveness is not None and effectiveness_stats:
            avg_eff = effectiveness_stats.get('avg_effectiveness', 0.0)
            if avg_eff < gate.min_avg_effectiveness:
                return False, f"Low effectiveness: {avg_eff:.2f} < {gate.min_avg_effectiveness:.2f} required"
                
        if gate.max_rollback_rate is not None and effectiveness_stats:
            rollback_rate = effectiveness_stats.get('rollback_rate', 1.0)
            if rollback_rate > gate.max_rollback_rate:
                return False, f"High rollback rate: {rollback_rate:.2f} > {gate.max_rollback_rate:.2f} allowed"
        
        # Check forced progression timeout
        if stage_runtime > self.config.max_stage_duration_s:
            return True, f"Forced progression: runtime {stage_runtime:.0f}s > {self.config.max_stage_duration_s:.0f}s limit"
        
        return True, "All progression criteria met"
    
    def progress_to_next_stage(self, reason: str = "Manual progression") -> bool:
        """
        Progress to the next warmup stage.
        
        Args:
            reason: Reason for progression
            
        Returns:
            True if progression successful, False otherwise
        """
        if self.state.current_stage == WarmupStage.PRODUCTION:
            log.warning("Already at production stage, cannot progress further")
            return False
            
        # Determine next stage
        if self.state.current_stage == WarmupStage.SMOKE:
            next_stage = WarmupStage.STAGING
        else:  # STAGING
            next_stage = WarmupStage.PRODUCTION
            
        # Record progression event
        progression_event = {
            'timestamp': time.time(),
            'from_stage': self.state.current_stage.value,
            'to_stage': next_stage.value,
            'reason': reason,
            'stage_runtime_s': time.time() - self.state.stage_start_time,
            'decisions_made': self.state.total_decisions,
            'success_rate': self.state.successful_decisions / max(1, self.state.total_decisions),
            'safety_violations': self.state.safety_violations
        }
        
        # Update state
        previous_stage = self.state.current_stage
        self.state.current_stage = next_stage
        self.state.stage_start_time = time.time()
        self.state.total_decisions = 0
        self.state.successful_decisions = 0
        self.state.safety_violations = 0
        self.state.progression_history.append(progression_event)
        
        self._save_state()
        
        log.info(f"Warmup progression: {previous_stage.value} → {next_stage.value} - {reason}")
        return True
    
    def rollback_to_previous_stage(self, reason: str = "Safety rollback") -> bool:
        """
        Rollback to previous warmup stage.
        
        Args:
            reason: Reason for rollback
            
        Returns:
            True if rollback successful, False otherwise
        """
        if not self.config.rollback_on_failure:
            log.warning("Rollback disabled in configuration")
            return False
            
        if self.state.current_stage == WarmupStage.SMOKE:
            log.warning("Already at smoke stage, cannot rollback further")
            return False
            
        # Determine previous stage
        if self.state.current_stage == WarmupStage.PRODUCTION:
            previous_stage = WarmupStage.STAGING
        else:  # STAGING
            previous_stage = WarmupStage.SMOKE
        
        # Record rollback event
        rollback_event = {
            'timestamp': time.time(),
            'from_stage': self.state.current_stage.value,
            'to_stage': previous_stage.value,
            'reason': reason,
            'type': 'rollback',
            'stage_runtime_s': time.time() - self.state.stage_start_time,
            'decisions_made': self.state.total_decisions,
            'safety_violations': self.state.safety_violations
        }
        
        # Update state
        current_stage = self.state.current_stage
        self.state.current_stage = previous_stage
        self.state.stage_start_time = time.time()
        self.state.total_decisions = 0
        self.state.successful_decisions = 0
        self.state.safety_violations = 0
        self.state.progression_history.append(rollback_event)
        
        # Disable auto-progression after rollback
        self.state.auto_progression_disabled = True
        
        self._save_state()
        
        log.warning(f"Warmup rollback: {current_stage.value} → {previous_stage.value} - {reason}")
        return True
    
    def get_progression_status(self) -> Dict[str, Any]:
        """
        Get current progression status and statistics.
        
        Returns:
            Dictionary with progression status information
        """
        current_time = time.time()
        stage_runtime = current_time - self.state.stage_start_time
        
        status = {
            'enabled': self.config.enabled,
            'current_stage': self.state.current_stage.value,
            'stage_runtime_s': stage_runtime,
            'stage_runtime_human': f"{stage_runtime/60:.1f} minutes",
            'total_decisions': self.state.total_decisions,
            'successful_decisions': self.state.successful_decisions,
            'safety_violations': self.state.safety_violations,
            'success_rate': self.state.successful_decisions / max(1, self.state.total_decisions),
            'auto_progression_enabled': self.config.auto_progression_enabled and not self.state.auto_progression_disabled,
            'progressions_made': len([h for h in self.state.progression_history if h.get('type') != 'rollback']),
            'rollbacks_made': len([h for h in self.state.progression_history if h.get('type') == 'rollback']),
            'current_parameters': self.get_current_parameters().dict(),
            'progression_history': self.state.progression_history[-5:]  # Last 5 events
        }
        
        return status
    
    def _load_state(self) -> WarmupState:
        """Load warmup state from file or create new."""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    state = WarmupState.model_validate(data)
                    log.info(f"Loaded warmup state: stage={state.current_stage}, "
                            f"decisions={state.total_decisions}")
                    return state
        except Exception as e:
            log.warning(f"Failed to load warmup state: {e}")
            
        # Create new state
        state = WarmupState(
            current_stage=self.config.initial_stage,
            stage_start_time=time.time(),
            last_updated=time.time()
        )
        
        log.info(f"Created new warmup state: stage={state.current_stage}")
        return state
    
    def _save_state(self) -> None:
        """Save current warmup state to file."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state.model_dump(), f, indent=2)
        except Exception as e:
            log.error(f"Failed to save warmup state: {e}")