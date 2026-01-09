# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

# SPEC: Define Pydantic Config model mapping 1:1 to cfg/master.yaml with defaults above.
# Provide load_config(path)->Config, env override via LLA_* env vars, and to_dict().
# Raise on unknown fields; log all resolved values on startup.
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional

import yaml
from pydantic import BaseModel, Field
try:  # Pydantic v2
    from pydantic import ConfigDict
    _HAS_PYDANTIC_V2 = True
except ImportError:  # fallback for v1
    ConfigDict = None  # type: ignore
    _HAS_PYDANTIC_V2 = False

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)


# --- Nested Models to match YAML structure ---

class ViabilityConfig(BaseModel):
    # Aligned to R0 freeze + production cadence (smoke run used tighter values in master.yaml)
    alpha: float = 0.1
    window: int = 256          # freeze baseline (smoke) retained for sensitivity
    min_count: int = 30         # faster conformal adaptation
    retrain_every_s: int = 300  # production cadence (smoke had 30)
    tau_floor: float = 0.005

class EFEConfig(BaseModel):
    surprisal_weight: float = 0.02   # freeze working value
    disagreement_weight: float = 0.5
    ensemble_size: int = 3

class EmpowermentConfig(BaseModel):
    mode: str = "ba_bound"
    fallback_threshold: float = 0.6
    proxy_min_valid: float = 0.7

class SlerpPenalties(BaseModel):
    acf: float = 1.0
    spectrum: float = 1.0
    energy: float = 2.0

class BridgeConfig(BaseModel):
    select_by: str = "complexity_score"
    slerp_penalties: SlerpPenalties = Field(default_factory=SlerpPenalties)
    min_interval_s: int = 60    # ensure ≥3 bridges in short runs
    required_valid_min: int = 3
    # Backward compatibility: earlier we had flat booleans
    force_at_end: Any = True  # will be normalized to ForceAtEndConfig in load_config
    force_window_s: int = 20  # legacy field (deprecated) kept for compatibility
    max_forced_attempts: int = 2  # legacy field (deprecated)
    improvement_eps: float = 0.0

class ActionGovernorConfig(BaseModel):
    """Action Governor configuration for PI-controller action ratio targeting"""
    enabled: bool = False
    target_pct: float = 22.0
    tolerance_pct: float = 4.0
    ewma_alpha: float = 0.30
    pi: Dict[str, Any] = Field(default_factory=lambda: {
        'kp': 0.40,
        'ki': 0.10,
        'anti_windup': True,
        'integrator_clip': [-0.25, 0.25]
    })
    duty_max: float = 0.35
    quotas: Dict[str, Any] = Field(default_factory=lambda: {
        'window_s': 600,
        'dominance_threshold': 0.70,
        'usage_degradation': {
            'start_after': 3,
            'factor': 0.85
        }
    })
    safety: Dict[str, Any] = Field(default_factory=lambda: {
        'rate_limit_per_min': 10,
        'spacing_s': 6
    })
    logging: Dict[str, bool] = Field(default_factory=lambda: {
        'emit_blackbox': True,
        'emit_acceptance': True
    })
    # BandCap v1.6 features
    bandcap_s: float = 20.0
    min_noops_after_action: int = 9

class ActionSafetyConfig(BaseModel):
    """TASK 10: Action safety controls configuration"""
    allowlist: list[str] = Field(default_factory=lambda: ['no_op', 'cooloff_sleep', 'renice_processes', 'de_risk_high_temp'])
    rate_limits: Dict[str, int] = Field(default_factory=lambda: {
        'de_risk_high_temp': 3,  # Max 3 GPU power changes per minute
        'renice_processes': 6,   # Max 6 process changes per minute  
        'cooloff_sleep': 10      # Max 10 sleep actions per minute
        # no_op has no rate limit (unlimited)
    })
    panic_file: str = 'C:/ProgramData/LLA/state/PANIC_STOP'
    rate_window_s: int = 60  # Rate limiting window in seconds

class EffectsConfig(BaseModel):
    """TASK 11: Effects tracking and ledger management configuration"""
    enabled: bool = True
    ledger_path: str = "effects_ledger.jsonl"
    snapshot_timeout_s: float = 30.0
    impact_window_s: float = 60.0
    min_impact_threshold: float = 0.1
    rollback_enabled: bool = False

class WarmupConfig(BaseModel):
    """TASK 12: Warmup policy gradual hardening configuration"""
    enabled: bool = True
    initial_stage: str = "smoke"  # smoke, staging, production
    progression_file: str = "warmup_progression.json"
    min_runtime_s: float = 300.0
    min_decisions: int = 10
    min_success_rate: float = 0.8
    max_safety_violations: int = 2
    stability_window_s: float = 180.0
    auto_progression_enabled: bool = True
    max_stage_duration_s: float = 1800.0
    rollback_on_failure: bool = True

class ActionThresholdsConfig(BaseModel):
    """TASK 13: Configurable action thresholds per environment"""
    # Minimum action ratio thresholds (prevent regression to 100% no_op)
    min_action_ratio: float = Field(default=0.2, ge=0.0, le=1.0)
    
    # Individual action frequency limits (per hour)
    max_cooling_actions_per_hour: int = Field(default=12, ge=0)  # de_risk_high_temp, cooloff_sleep
    max_optimization_actions_per_hour: int = Field(default=20, ge=0)  # renice_processes
    
    # Action effectiveness thresholds
    min_action_effectiveness: float = Field(default=0.3, ge=0.0, le=1.0)
    max_rollback_rate: float = Field(default=0.3, ge=0.0, le=1.0)
    
    # Environment-specific multipliers
    environment_type: str = Field(default="production")  # smoke, staging, production
    risk_tolerance_multiplier: float = Field(default=1.0, ge=0.1, le=5.0)
    
    # Safety override settings
    emergency_action_override: bool = True  # Allow override in critical situations
    grace_period_minutes: int = Field(default=30, ge=0)  # Grace period for new deployments
    
    # Validation settings
    strict_validation: bool = True  # Enforce strict threshold validation
    auto_adjustment_enabled: bool = False  # Auto-adjust thresholds based on performance

class SafetyConfig(BaseModel):
    two_signals: bool = True
    mi_drop_penalty: float = 0.2
    kill_temp_c: float = 85.0
    cpu_load: float = 0.90   # production threshold (smoke lowered to 0.40)
    action_controls: ActionSafetyConfig = Field(default_factory=ActionSafetyConfig)  # TASK 10
    effects: EffectsConfig = Field(default_factory=EffectsConfig)  # TASK 11
    warmup: WarmupConfig = Field(default_factory=WarmupConfig)  # TASK 12

class KpiConfig(BaseModel):
    homeostasis_target: float = 0.85
    recovery_s: int = 120
    report_every_s: int = 5   # high-frequency KPI visibility (smoke was 10)

class IOConfig(BaseModel):
    nvml: bool = True
    mock: bool = False      # real mode by default; smoke set via flag/override
    log_dir: str = "logs"
    jsonl: bool = True
    # Directory for external text triggers (e.g., TEXT_TRIGGER file). Use a cross-platform path.
    triggers_dir: str = "C:/ProgramData/LLA/state"
    rotate_when: str = "midnight"  # TimedRotatingFileHandler 'when' parameter
    rotate_interval: int = 1        # interval for rotation
    rotate_backup_count: int = 7    # keep one week of daily logs


class ForceAtEndConfig(BaseModel):
    enabled: bool = True
    window_s: int = 20
    only_last_window: bool = False
    max_attempts_per_window: int = 2


class R1TextTriggerConfig(BaseModel):
    """Configuration for optional automatic emission of a TEXT_TRIGGER file.

    When enabled the orchestrator will, after offset_s seconds from start, create
    a trigger file (filename) inside cfg.io.triggers_dir containing the JSON
    payload string. This supports automated ΔSurprisal acceptance without manual
    intervention. The file is only emitted once per run.
    """
    enabled: bool = False
    offset_s: int = 120
    filename: str = "TEXT_TRIGGER"
    payload: str = '{"type":"auto","note":"r1.text_trigger"}'


class R1Config(BaseModel):
    """Container for forward-compatible R1 features (kept separate from R0)."""
    text_trigger: R1TextTriggerConfig = Field(default_factory=R1TextTriggerConfig)


# ---- R2 (skeleton) configuration models (flexible; keep defaults minimal) ----

class R2OnlineAcceptance(BaseModel):
    require_r2_online_ok: bool = False
    min_stability: float = 0.60
    max_churn_per_hour: float = 4.0

class R2OnlineConfig(BaseModel):
    enabled: bool = False
    interval_s: int = 60
    cooldown_s: int = 180
    min_dwell_s: int = 120
    max_switches_per_hour: int = 6
    acceptance: R2OnlineAcceptance = Field(default_factory=R2OnlineAcceptance)

class R2PreloopConfig(BaseModel):
    enabled: bool = True
    max_seconds: int = 120
    max_ticks: int = 0   # 0 => unlimited within time budget
    readiness_bridges: int = 5
    viability_min_samples: int = 30  # warmup gating threshold (default ties to viability.min_count)
    bridges_min_ready: int = 1       # minimum valid bridges before lifting warmup

class R2MainLoopConfig(BaseModel):
    min_seconds: int = 0  # guarantee (0 => no guarantee)

class R2AttractorsConfig(BaseModel):
    top_k_source: int = 100
    min_cluster_size: int = 5
    method: str = "kmeans"
    k: int = 3
    features: list[str] = Field(default_factory=lambda: ['dJ','dEFE','dEmp','dHomeo'])

class R2RouterConfig(BaseModel):
    novelty_weight: float = 0.2
    tau_guard: float = 0.05
    min_score: float = 0.0

class R2LearnConfig(BaseModel):
    buffer_max: int = 1000
    batch_size: int = 32
    lr: float = 1e-3
    epochs: int = 3
    loss: str = 'mse'

class R2StabilityConfig(BaseModel):
    window_s: int = 1800
    min_stability: float = 0.65
    min_dwell_gain: float = 0.0
    max_churn_per_hour: float = 4.0

class RunnerConfig(BaseModel):
    """Runtime control configuration"""
    min_runtime_s: int = 300
    max_runtime_s: int = 0  # 0 = no upper limit
    require_min_decisions: int = 30
    on_acceptance_fail: dict = Field(default_factory=lambda: {'continue_until_min_runtime': True})

class R2SelectorConfig(BaseModel):
    mu_distance: float = 0.75
    min_score: float = 0.10

class R2CouplingConfig(BaseModel):
    use_attractor_coupling: bool = True
    mu_dist: float = 0.75
    min_compat: float = 0.10
    top_k_per_attractor: int = 2

class R2BootstrapConfig(BaseModel):
    """Temporary bootstrap phase for early bridge generation.

    When enabled (mode=r2) the first `bridges_target` valid bridges bypass the
    attractor selector (if selector_bypass True) and/or use relaxed selector
    parameters (`temp_selector_overrides`). After target reached or
    `revert_after_s` elapsed since run start, normal selector thresholds are
    restored automatically.
    """
    enabled: bool = False
    bridges_target: int = 5
    selector_bypass: bool = True
    revert_after_s: int = 900  # safety: auto‑revert after 15 minutes
    temp_selector_overrides: dict[str, float] | None = None  # e.g. {min_score:-1.0, mu_distance:0.0}

class R2Config(BaseModel):
    online: R2OnlineConfig = Field(default_factory=R2OnlineConfig)
    attractors: R2AttractorsConfig = Field(default_factory=R2AttractorsConfig)
    router: R2RouterConfig = Field(default_factory=R2RouterConfig)
    learn: R2LearnConfig = Field(default_factory=R2LearnConfig)
    stability: R2StabilityConfig = Field(default_factory=R2StabilityConfig)
    selector: R2SelectorConfig = Field(default_factory=R2SelectorConfig)
    coupling: R2CouplingConfig = Field(default_factory=R2CouplingConfig)
    bootstrap: R2BootstrapConfig = Field(default_factory=R2BootstrapConfig)
    preloop: R2PreloopConfig | None = None   # if config uses r2.online.preloop we keep backwards mapping
    main_loop: R2MainLoopConfig | None = None

    def validate_no_duplicate_acceptance(self):
        # Guard against r2.online.acceptance.acceptance nesting bug
        try:
            acc = self.online.acceptance
            # If underlying raw dict had duplicate level it'll be caught prior; extra check is light
        except Exception:
            pass



# --- Root Configuration Model ---

class Config(BaseModel):
    # Pydantic v2 style config
    if _HAS_PYDANTIC_V2:
        model_config = ConfigDict(extra='forbid')  # type: ignore
    viability: ViabilityConfig = Field(default_factory=ViabilityConfig)
    efe: EFEConfig = Field(default_factory=EFEConfig)
    empowerment: EmpowermentConfig = Field(default_factory=EmpowermentConfig)
    bridge: BridgeConfig = Field(default_factory=BridgeConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    kpi: KpiConfig = Field(default_factory=KpiConfig)
    runner: RunnerConfig = Field(default_factory=RunnerConfig)
    io: IOConfig = Field(default_factory=IOConfig)
    r1: R1Config = Field(default_factory=R1Config)
    r2: R2Config = Field(default_factory=R2Config)
    
    # TASK 10-13: Action management subsystem configurations
    action_governor: ActionGovernorConfig = Field(default_factory=ActionGovernorConfig)
    action_safety: ActionSafetyConfig = Field(default_factory=ActionSafetyConfig)
    effects: EffectsConfig = Field(default_factory=EffectsConfig)
    warmup: WarmupConfig = Field(default_factory=WarmupConfig)
    action_thresholds: ActionThresholdsConfig = Field(default_factory=ActionThresholdsConfig)

    def to_dict(self) -> Dict[str, Any]:
        """Return config as primitive dict using Pydantic v2+ API when available.

        Uses model_dump (v2) with fallback to dict (v1) to avoid deprecation warnings.
        """
        if hasattr(self, 'model_dump'):
            return self.model_dump()  # type: ignore[attr-defined]
        return self.dict()

def _override_with_env(cfg_dict: Dict[str, Any], prefix: str = "LLA") -> None:
    """Recursively overrides config dictionary with environment variables."""
    for key, value in cfg_dict.items():
        if isinstance(value, dict):
            _override_with_env(value, prefix=f"{prefix}_{key.upper()}")
        else:
            env_var = f"{prefix}_{key.upper()}"
            if env_var in os.environ:
                env_val = os.environ[env_var]
                try:
                    # Attempt to cast to the original type
                    original_type = type(value)
                    cfg_dict[key] = original_type(env_val)
                    log.info(f"Overrode '{env_var}' with value '{env_val}'")
                except (ValueError, TypeError):
                    log.warning(f"Could not cast env var '{env_var}' to type {type(value)}")


def load_config(path: Path) -> Config:
    """Loads configuration from a YAML file and overrides with environment variables."""
    if not path.exists():
        log.warning(f"Config file not found at {path}. Using default values.")
        cfg_dict = {}
    else:
        # Ensure UTF-8 decoding (Windows cp1252 could break on comments / non-ASCII)
        with open(path, 'r', encoding='utf-8') as f:
            cfg_dict = yaml.safe_load(f)
    
    # Create a default config dict to ensure all keys exist
    default_config = Config().model_dump() if hasattr(Config, 'model_dump') else Config().dict()
    # Deep update default config with loaded values
    def deep_update(d, u):
        """Recursively merge u into d (mutating d) handling None placeholders.

        If a key in u has value None but d has a dict, we keep d's dict (YAML
        structural error safeguard). If d expects a dict (by default_config)
        but u provided a non-dict, we overwrite only if types match; otherwise
        we log and ignore the bad value to avoid validation failure.
        """
        for k, v in u.items():
            if isinstance(v, dict):
                base = d.get(k, {}) if isinstance(d.get(k, {}), dict) else {}
                d[k] = deep_update(base, v)
            else:
                if isinstance(d.get(k), dict) and v is None:
                    # Skip None overriding an expected dict
                    continue
                d[k] = v
        return d
        
    final_cfg_dict = deep_update(default_config, cfg_dict)

    _override_with_env(final_cfg_dict)

    # Normalize legacy bridge.force_at_end format (bool or missing) into structured config
    bridge_section = final_cfg_dict.get("bridge", {})
    fae_val = bridge_section.get("force_at_end", True)
    if isinstance(fae_val, dict):
        # Ensure defaults for missing keys
        _fae_model = ForceAtEndConfig(**fae_val)
        fae_norm = _fae_model.model_dump() if hasattr(_fae_model, 'model_dump') else _fae_model.dict()
    else:
        # Legacy bool -> construct dict using legacy auxiliaries if present
        _fae_model = ForceAtEndConfig(
            enabled=bool(fae_val),
            window_s=int(bridge_section.get("force_window_s", 20) or 20),
            max_attempts_per_window=int(bridge_section.get("max_forced_attempts", 2) or 2),
            only_last_window=False,
        )
        fae_norm = _fae_model.model_dump() if hasattr(_fae_model, 'model_dump') else _fae_model.dict()
    bridge_section["force_at_end"] = fae_norm
    final_cfg_dict["bridge"] = bridge_section

    # Schema guard for duplicate acceptance nesting under r2.online
    try:
        dup = (((final_cfg_dict.get('r2') or {}).get('online') or {}).get('acceptance') or {})
        if isinstance(dup, dict) and 'acceptance' in dup:
            raise ValueError("Invalid config: duplicate 'acceptance' level under r2.online.acceptance")
    except Exception as e:
        raise

    # Backward-compatible relocation: if r2.online.preloop exists move into r2.preloop (normalized) when top-level preloop missing
    try:
        r2_block = final_cfg_dict.get('r2') or {}
        online_block = r2_block.get('online') or {}
        # Treat explicit None (from defaults) as absent for promotion purposes
        preloop_current = r2_block.get('preloop', None)
        if 'preloop' in online_block and (preloop_current is None or not isinstance(preloop_current, dict)):
            r2_block['preloop'] = online_block.get('preloop')
        # main_loop already top-level if provided; (future normalization placeholder)
        final_cfg_dict['r2'] = r2_block
    except Exception:
        pass

    # Pydantic v2 vs v1 compatible instantiation
    if _HAS_PYDANTIC_V2:
        config = Config.model_validate(final_cfg_dict)  # type: ignore[attr-defined]
    else:  # v1
        from pydantic import BaseModel as _BM  # type: ignore
        config = Config.parse_obj(final_cfg_dict)  # type: ignore
    log.info("Configuration loaded successfully.")
    log.debug(f"Final config keys: {list(final_cfg_dict.keys())}")
    return config

# Example usage (can be placed in a script)
if __name__ == '__main__':
    # This assumes the script is run from the project root 'living_latent'
    config_path = Path("cfg/master.yaml")
    cfg = load_config(config_path)
    print("\n--- Loaded Config ---")
    print(f"Viability Alpha: {cfg.viability.alpha}")
    print(f"Log Directory: {cfg.io.log_dir}")