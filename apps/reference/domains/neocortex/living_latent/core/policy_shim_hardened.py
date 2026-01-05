# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

"""
Policy Shim V2 - Hardened Production Implementation
=================================================

Pydantic-safe hardening через environment variables та trigger files.
Includes homeostasis gating, self-calibration, structured logging, emergency controls.

SPEC R0-13-POLICY_SHIM_V2: Conservative Action Policy Shim
- Streak-based no_op replacement (configurable threshold)
- Cooldown-based rate limiting
- Homeostasis-aware hysteresis
- Emergency controls via trigger files
- Structured event logging
"""

import os
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any
from ..utils.policy_shim_log import log_shim


class PolicyShimHardened:
    """Production-hardened Policy Shim с configurable parameters"""
    
    def __init__(self):
        # Environment-based configuration (Pydantic-safe)
        self.noop_streak_limit = int(os.getenv("LLA_SHIM_NOOP_STREAK_LIMIT", "2"))
        self.cooldown_s = int(os.getenv("LLA_SHIM_COOLDOWN_S", "20"))
        
        # Homeostasis hysteresis thresholds
        hyst_values = os.getenv("LLA_SHIM_HYST", "65,80").split(",")
        self.hyst_low = int(hyst_values[0])
        self.hyst_high = int(hyst_values[1])
        
        # Trigger directory для emergency controls
        self.trigger_dir = Path(os.getenv("LLA_TRIGGERS_DIR", "C:/ProgramData/LLA/state"))
        self.trigger_dir.mkdir(parents=True, exist_ok=True)
        
        # Emergency control files
        self.force_prefer_file = self.trigger_dir / "SHIM_FORCE_PREFER"
        self.disable_file = self.trigger_dir / "SHIM_DISABLE"
        
        # State tracking
        self._last_replacement_ts = 0.0
        self._dynamic_streak_limit = self.noop_streak_limit
        
        # ⏰ SPACING OPTIMIZATION для рівномірного розподілу cooloff_sleep
        # Default: 60s window / 10 actions = 6s spacing for optimal utilization
        self.rate_window_s = float(os.getenv("LLA_SHIM_RATE_WINDOW_S", "60"))
        self.rate_limit = int(os.getenv("LLA_SHIM_RATE_LIMIT", "10"))
        self.spacing_s = self.rate_window_s / self.rate_limit if self.rate_limit > 0 else 0.0
        self._next_cooloff_at = 0.0
        
        # 🚀 SOFT ANTI-NO_ALT DEFER MECHANISM
        # Prevents excessive NO_ALT fallbacks by deferring when tick_force_cooloff available
        self.cooloff_sleep_duration_s = float(os.getenv("LLA_SHIM_COOLOFF_S", "1.0"))
        self._next_tick_force_cooloff = False
        self._defer_eta_check_s = 2.0  # Check if can defer for 2s
        
        print(f"🎯 PolicyShimHardened initialized:")
        print(f"   NOOP_STREAK_LIMIT: {self.noop_streak_limit}")
        print(f"   COOLDOWN_S: {self.cooldown_s}")
        print(f"   HYSTERESIS: {self.hyst_low}-{self.hyst_high}%")
        print(f"   SPACING: {self.spacing_s:.1f}s ({self.rate_limit}/min)")
        print(f"   COOLOFF_SLEEP_DURATION: {self.cooloff_sleep_duration_s}s")
        print(f"   DEFER_ETA_CHECK: {self._defer_eta_check_s}s")
        print(f"   TRIGGER_DIR: {self.trigger_dir}")
    
    def can_defer_for_tick_force_cooloff(self) -> bool:
        """
        Check if we can defer NO_ALT for upcoming tick_force_cooloff
        
        Soft anti-NO_ALT mechanism: if spacing indicates cooloff_sleep will be 
        available within defer_eta_check_s, defer the NO_ALT decision.
        
        Returns:
            True if should defer (wait for tick_force_cooloff)
        """
        now = time.time()
        eta_to_next_cooloff = self._next_cooloff_at - now
        
        # If cooloff is available within defer window, suggest deferring
        if 0 < eta_to_next_cooloff <= self._defer_eta_check_s:
            log_shim("soft_defer_no_alt",
                    eta_to_next_cooloff=eta_to_next_cooloff,
                    defer_window_s=self._defer_eta_check_s,
                    reason="tick_force_cooloff_available_soon")
            return True
        
        return False
    
    def set_next_tick_force_cooloff(self) -> None:
        """Mark that next tick should force cooloff_sleep if possible"""
        self._next_tick_force_cooloff = True
        log_shim("next_tick_force_cooloff_set",
                reason="defer_mechanism_activated")
    
    def should_tick_force_cooloff(self) -> bool:
        """
        Check if this tick should force cooloff_sleep
        
        Returns:
            True if tick should force cooloff (and clears the flag)
        """
        if self._next_tick_force_cooloff:
            self._next_tick_force_cooloff = False
            
            # Verify we still meet spacing/cooldown requirements
            if self.is_spacing_ok() and self.is_cooldown_ok():
                log_shim("tick_force_cooloff_executed",
                        reason="defer_mechanism_triggered")
                self.mark_replacement()
                self.schedule_next_cooloff()
                return True
            else:
                log_shim("tick_force_cooloff_blocked",
                        spacing_ok=self.is_spacing_ok(),
                        cooldown_ok=self.is_cooldown_ok(),
                        reason="safety_constraints")
        
        return False
    
    def is_disabled(self) -> bool:
        """Check if Policy Shim is disabled via trigger file"""
        return self.disable_file.exists()
    
    def get_prefer_actions_ticks(self) -> int:
        """Get prefer_actions ticks (8 if forced, 0 otherwise)"""
        return 8 if self.force_prefer_file.exists() else 0
    
    def is_cooldown_ok(self) -> bool:
        """Check if cooldown period has passed"""
        return (time.time() - self._last_replacement_ts) >= self.cooldown_s
    
    def is_spacing_ok(self) -> bool:
        """Check if optimal spacing period has passed for rate utilization"""
        now = time.time()
        spacing_ready = now >= self._next_cooloff_at
        if spacing_ready:
            log_shim("spacing_check", 
                    next_at=self._next_cooloff_at,
                    now=now,
                    spacing_s=self.spacing_s,
                    result="ready")
        return spacing_ready
    
    def schedule_next_cooloff(self) -> None:
        """Schedule next cooloff attempt for optimal spacing"""
        now = time.time()
        self._next_cooloff_at = now + self.spacing_s
        log_shim("spacing_scheduled",
                next_at=self._next_cooloff_at,
                spacing_s=self.spacing_s)
    
    def mark_replacement(self) -> None:
        """Mark that a replacement occurred (for cooldown tracking)"""
        self._last_replacement_ts = time.time()
    
    def update_dynamic_streak_limit(self, homeostasis_pct: Optional[float]) -> int:
        """Update streak limit based on homeostasis (hysteresis)"""
        if homeostasis_pct is None:
            return self.noop_streak_limit
        
        # Homeostasis hysteresis gating
        if homeostasis_pct < self.hyst_low:
            # Low homeostasis -> increase conservatism (higher streak limit)
            self._dynamic_streak_limit = max(self.noop_streak_limit, 3)
            log_shim("homeostasis_gating", 
                    homeostasis_pct=homeostasis_pct, 
                    streak_limit=self._dynamic_streak_limit,
                    reason="low_homeostasis_conservative")
        elif homeostasis_pct >= self.hyst_high:
            # High homeostasis -> restore normal operation
            self._dynamic_streak_limit = self.noop_streak_limit
            log_shim("homeostasis_gating",
                    homeostasis_pct=homeostasis_pct,
                    streak_limit=self._dynamic_streak_limit,
                    reason="high_homeostasis_normal")
        
        return self._dynamic_streak_limit
    
    def should_replace_no_op(self, 
                           streak: int, 
                           bridge_count: int,
                           homeostasis_pct: Optional[float] = None) -> bool:
        """
        Determine if no_op should be replaced with cooloff_sleep
        
        Args:
            streak: Current no_op streak count
            bridge_count: Number of ready bridges
            homeostasis_pct: Current homeostasis percentage (for hysteresis)
        
        Returns:
            True if replacement should occur
        """
        # Check emergency disable
        if self.is_disabled():
            log_shim("shim_disabled", reason="emergency_disable_file")
            return False
        
        # Update dynamic streak limit based on homeostasis
        current_streak_limit = self.update_dynamic_streak_limit(homeostasis_pct)
        
        # Check cooldown (safety) and spacing (efficiency)
        if not self.is_cooldown_ok():
            remaining_cooldown = self.cooldown_s - (time.time() - self._last_replacement_ts)
            log_shim("cooldown_blocked", 
                    remaining_s=remaining_cooldown,
                    streak=streak,
                    bridges=bridge_count)
            return False
        
        # ⏰ SPACING OPTIMIZATION: Check if we should wait for optimal timing
        if not self.is_spacing_ok():
            log_shim("spacing_blocked",
                    next_cooloff_at=self._next_cooloff_at,
                    streak=streak,
                    bridges=bridge_count,
                    reason="optimal_rate_utilization")
            return False
        
        # Core Policy Shim logic: replace if streak >= limit
        should_replace = streak >= current_streak_limit
        
        if should_replace:
            log_shim("replace_no_op",
                    streak=streak,
                    bridges=bridge_count,
                    streak_limit=current_streak_limit,
                    homeostasis_pct=homeostasis_pct)
            self.mark_replacement()
            self.schedule_next_cooloff()  # Schedule next attempt for optimal spacing
        
        return should_replace
    
    def should_proactive_cooloff(self, current_action: str = "no_op") -> bool:
        """
        Check if we should proactively execute cooloff_sleep for optimal rate utilization
        
        Args:
            current_action: The currently planned action
            
        Returns:
            True if proactive cooloff_sleep should be executed
        """
        # Only consider proactive cooloff for no_op actions
        if current_action != "no_op":
            return False
        
        # Check emergency disable
        if self.is_disabled():
            return False
        
        # Check if spacing timing is optimal AND we have safety clearance
        if self.is_spacing_ok() and self.is_cooldown_ok():
            log_shim("proactive_cooloff",
                    current_action=current_action,
                    reason="optimal_timing_available")
            self.mark_replacement()
            self.schedule_next_cooloff()
            return True
        
        return False
    
    def handle_blocked_action_fallback(self, 
                                     primary_action: str, 
                                     fallback_action: str = "cooloff_sleep") -> bool:
        """
        Handle fallback when primary action is blocked
        
        Args:
            primary_action: The originally selected action that was blocked
            fallback_action: The fallback action to use
        
        Returns:
            True if fallback should be applied
        """
        # Check emergency disable
        if self.is_disabled():
            log_shim("fallback_disabled", 
                    primary=primary_action,
                    reason="emergency_disable_file")
            return False
        
        # Check cooldown for fallback
        if not self.is_cooldown_ok():
            remaining_cooldown = self.cooldown_s - (time.time() - self._last_replacement_ts)
            log_shim("fallback_cooldown_blocked",
                    primary=primary_action,
                    fallback=fallback_action,
                    remaining_s=remaining_cooldown)
            return False
        
        # Apply fallback
        log_shim("fallback_blocked_action",
                primary=primary_action,
                fallback=fallback_action)
        self.mark_replacement()
        
        return True
    
    def handle_conservative_pattern(self, ready_bridges: int, threshold: int = 3) -> int:
        """
        Handle conservative pattern detection
        
        Args:
            ready_bridges: Number of ready bridges
            threshold: Threshold for conservative pattern detection
        
        Returns:
            Number of prefer_actions ticks to apply
        """
        # Check for forced prefer actions via trigger file
        forced_ticks = self.get_prefer_actions_ticks()
        if forced_ticks > 0:
            log_shim("prefer_actions_forced",
                    ticks=forced_ticks,
                    ready_bridges=ready_bridges,
                    reason="trigger_file")
            return forced_ticks
        
        # Normal conservative pattern detection
        if ready_bridges >= threshold:
            prefer_ticks = 8
            log_shim("conservative_pattern_detected",
                    ready_bridges=ready_bridges,
                    threshold=threshold,
                    prefer_ticks=prefer_ticks)
            return prefer_ticks
        
        return 0
    
    def get_current_config(self) -> Dict[str, Any]:
        """Get current Policy Shim configuration for debugging"""
        now = time.time()
        return {
            "noop_streak_limit": self.noop_streak_limit,
            "dynamic_streak_limit": self._dynamic_streak_limit,
            "cooldown_s": self.cooldown_s,
            "cooloff_sleep_duration_s": self.cooloff_sleep_duration_s,
            "hysteresis": f"{self.hyst_low}-{self.hyst_high}%",
            "spacing_s": self.spacing_s,
            "rate_limit": f"{self.rate_limit}/min",
            "defer_eta_check_s": self._defer_eta_check_s,
            "disabled": self.is_disabled(),
            "forced_prefer": self.force_prefer_file.exists(),
            "cooldown_remaining": max(0, self.cooldown_s - (time.time() - self._last_replacement_ts)),
            "next_cooloff_eta": max(0, self._next_cooloff_at - now),
            "next_tick_force_cooloff": self._next_tick_force_cooloff,
            "trigger_dir": str(self.trigger_dir)
        }
    
    def emergency_stop(self) -> None:
        """Create emergency disable file"""
        self.disable_file.touch()
        log_shim("emergency_stop", reason="manual_disable")
        print(f"🛑 Policy Shim EMERGENCY STOP activated: {self.disable_file}")
    
    def emergency_resume(self) -> None:
        """Remove emergency disable file"""
        if self.disable_file.exists():
            self.disable_file.unlink()
            log_shim("emergency_resume", reason="manual_enable")
            print(f"✅ Policy Shim resumed: {self.disable_file} removed")
    
    def force_prefer_actions(self, duration_minutes: int = 5) -> None:
        """Temporarily force prefer actions"""
        self.force_prefer_file.touch()
        log_shim("force_prefer_activated", 
                duration_minutes=duration_minutes,
                reason="manual_activation")
        print(f"🎯 Policy Shim: Forced prefer_actions for {duration_minutes} minutes")
        print(f"   Remove file to stop: {self.force_prefer_file}")


# Global instance for easy access
policy_shim_hardened = PolicyShimHardened()


# Convenience functions for integration
def should_replace_no_op(streak: int, bridge_count: int, homeostasis_pct: Optional[float] = None) -> bool:
    """Convenience function for no_op replacement decision"""
    return policy_shim_hardened.should_replace_no_op(streak, bridge_count, homeostasis_pct)

def handle_blocked_action_fallback(primary_action: str, fallback_action: str = "cooloff_sleep") -> bool:
    """Convenience function for blocked action fallback"""
    return policy_shim_hardened.handle_blocked_action_fallback(primary_action, fallback_action)

def handle_conservative_pattern(ready_bridges: int, threshold: int = 3) -> int:
    """Convenience function for conservative pattern handling"""
    return policy_shim_hardened.handle_conservative_pattern(ready_bridges, threshold)

def get_shim_config() -> Dict[str, Any]:
    """Get current Policy Shim configuration"""
    return policy_shim_hardened.get_current_config()

def can_defer_for_tick_force_cooloff() -> bool:
    """Check if can defer NO_ALT for upcoming cooloff_sleep"""
    return policy_shim_hardened.can_defer_for_tick_force_cooloff()

def set_next_tick_force_cooloff() -> None:
    """Set next tick to force cooloff_sleep"""
    return policy_shim_hardened.set_next_tick_force_cooloff()

def should_tick_force_cooloff() -> bool:
    """Check if this tick should force cooloff_sleep"""
    return policy_shim_hardened.should_tick_force_cooloff()