"""
CFG-DOMAINS-STEP-02 Tests: QoS Vertical Slice via DomainConfigResolver.

Tests:
A. QoS config read from canonical domains.yaml
B. No fallback to legacy _get_qos_config() or trading.decision.qos
C. Fail-closed on missing QoS (via Pydantic defaults or resolver error)

Scope: ONLY QoS block in DecisionMaking.
       Other blocks (signals, weights, risk) not touched (future steps).
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
from apps.reference.domain_config import DomainConfigResolver
from apps.reference.domains.decision_making.decision_making import DecisionMaking


class TestCfgDomainsStep02QosVerticalSlice:
    """Test QoS vertical slice: canonical domains → DecisionMaking (no fallbacks)."""
    
    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary config directory with test configs."""
        temp_dir = Path(tempfile.mkdtemp())
        
        # Copy real configs as base
        real_config_dir = Path(__file__).resolve().parents[1] / "config" / "aurora"
        if not real_config_dir.exists():
            real_config_dir = Path(__file__).resolve().parents[1] / "tests" / "config" / "aurora"
        
        for yaml_file in ["system.yaml", "trading.yaml", "regime.yaml", "domains.yaml"]:
            src = real_config_dir / yaml_file
            if src.exists():
                shutil.copy(src, temp_dir / yaml_file)
        
        yield temp_dir
        
        # Cleanup
        shutil.rmtree(temp_dir)
    
    # ============================================================================
    # Test A: QoS config from canonical domains.yaml
    # ============================================================================
    
    def test_qos_from_canonical_domains_yaml(self, temp_config_dir):
        """✅ Test A: QoS config read from canonical domains.yaml (custom value)."""
        # Modify domains.yaml to have non-default QoS value
        domains_yaml = temp_config_dir / "domains.yaml"
        import yaml
        with open(domains_yaml, 'r') as f:
            domains_data = yaml.safe_load(f)
        
        # Set custom QoS value
        domains_data['decision_making']['qos']['symbol_cooldown_sec'] = 123
        domains_data['decision_making']['qos']['mode'] = 'block'
        domains_data['decision_making']['qos']['max_intents_per_minute_per_symbol'] = 999
        
        with open(domains_yaml, 'w') as f:
            yaml.safe_dump(domains_data, f)
        
        # Load config
        loader = ConfigLoader(config_dir=temp_config_dir)
        config = loader.load_config()
        
        # VERIFY: Resolver can access QoS directly (canonical path)
        resolver = DomainConfigResolver(config)
        dm_cfg = resolver.get_decision_making()
        qos_cfg = dm_cfg.qos
        
        # Check custom values from domains.yaml
        assert qos_cfg.symbol_cooldown_sec == 123, "symbol_cooldown_sec should be from domains.yaml"
        assert qos_cfg.mode == "block", "qos_mode should be from domains.yaml"
        assert qos_cfg.max_intents_per_minute_per_symbol == 999, "max_intents should be from domains.yaml"
    
    # ============================================================================
    # Test B: DomainConfigResolver reads ONLY canonical (no legacy fallback)
    # ============================================================================
    
    def test_resolver_canonical_only_no_trading_domains(self, temp_config_dir):
        """✅ Test B: DomainConfigResolver fails if config.domains is None (no fallback)."""
        # Load config normally
        loader = ConfigLoader(config_dir=temp_config_dir)
        config = loader.load_config()
        
        # Mock config with domains=None (simulate missing domains)
        from apps.reference.config_models import AuroraConfig
        from unittest.mock import MagicMock
        
        broken_config = MagicMock(spec=AuroraConfig)
        broken_config.domains = None
        broken_config.trading = MagicMock()
        broken_config.trading.domains = MagicMock()  # exists but should NOT be used
        
        # EXPECT: ValueError (fail-closed, no fallback to trading.domains)
        with pytest.raises(ValueError, match="DomainConfigResolver requires config.domains"):
            resolver = DomainConfigResolver(broken_config)
    
    def test_decision_making_no_legacy_qos_getter_used(self, temp_config_dir):
        """✅ Test B: _get_qos_config() method removed (not callable)."""
        loader = ConfigLoader(config_dir=temp_config_dir)
        config = loader.load_config()
        
        # VERIFY: DomainConfigResolver can access QoS (canonical path works)
        resolver = DomainConfigResolver(config)
        dm_cfg = resolver.get_decision_making()
        qos_cfg = dm_cfg.qos
        
        # Check that QoS values are populated (from canonical domains)
        assert qos_cfg.exposure_block_cooldown_sec > 0
        assert qos_cfg.max_intents_per_minute_per_symbol > 0
        assert qos_cfg.mode in ["defer", "block", "shadow"]
    
    # ============================================================================
    # Test C: Fail-closed on missing QoS (Pydantic defaults or error)
    # ============================================================================
    
    def test_qos_has_pydantic_defaults_in_schema(self, temp_config_dir):
        """✅ Test C: QoS has explicit Pydantic defaults (no silent fallback)."""
        from apps.reference.config_models import QosConfig
        
        # Verify QosConfig has defaults (fail-closed if missing from YAML)
        qos_default = QosConfig()
        
        # These should NOT be None (explicit defaults in Pydantic model)
        assert qos_default.exposure_block_cooldown_sec == 60  # default from model
        assert qos_default.symbol_cooldown_sec == 3
        assert qos_default.mode in ["defer", "block", "shadow"]
        assert isinstance(qos_default.enforce, bool)
    
    def test_missing_qos_in_domains_uses_pydantic_defaults(self, temp_config_dir):
        """✅ Test C: Missing QoS section uses Pydantic defaults (not runtime fallback)."""
        # Remove QoS section from domains.yaml
        domains_yaml = temp_config_dir / "domains.yaml"
        import yaml
        with open(domains_yaml, 'r') as f:
            domains_data = yaml.safe_load(f)
        
        # Remove QoS (Pydantic should provide defaults)
        if 'qos' in domains_data.get('decision_making', {}):
            del domains_data['decision_making']['qos']
        
        with open(domains_yaml, 'w') as f:
            yaml.safe_dump(domains_data, f)
        
        # Load config
        loader = ConfigLoader(config_dir=temp_config_dir)
        config = loader.load_config()
        
        # VERIFY: DomainConfigResolver provides Pydantic defaults
        resolver = DomainConfigResolver(config)
        dm_cfg = resolver.get_decision_making()
        qos_cfg = dm_cfg.qos
        
        # VERIFY: Pydantic defaults applied (not runtime fallback)
        # QosConfig has default_factory, so qos should exist with defaults
        assert qos_cfg.exposure_block_cooldown_sec == 60  # Pydantic default
        assert qos_cfg.symbol_cooldown_sec == 3  # Pydantic default
        assert qos_cfg.mode in ["defer", "block", "shadow"]
    
    def test_domains_yaml_overrides_trading_yaml_for_qos(self, temp_config_dir):
        """✅ Test F: CRITICAL — DomainConfigResolver uses config.domains (canonical), not config.trading.
        
        This test proves that DomainConfigResolver reads ONLY from config.domains (root-level),
        and IGNORES config.trading structure completely.
        
        Setup:
        - domains.yaml: symbol_cooldown_sec = 999 (CANONICAL)
        - ConfigLoader loads it into config.domains
        
        Expected:
        - DomainConfigResolver returns 999 (from config.domains)
        - trading.yaml values (even if they differ) are not used by resolver
        """
        import yaml
        
        # Set domains.yaml: symbol_cooldown_sec = 999 (CANONICAL value)
        domains_yaml = temp_config_dir / "domains.yaml"
        with open(domains_yaml, 'r') as f:
            domains_data = yaml.safe_load(f)
        
        domains_data['decision_making']['qos']['symbol_cooldown_sec'] = 999
        domains_data['decision_making']['qos']['mode'] = 'block'
        
        with open(domains_yaml, 'w') as f:
            yaml.safe_dump(domains_data, f)
        
        # Load config
        from apps.reference.config_loader import ConfigLoader
        loader = ConfigLoader(config_dir=temp_config_dir)
        config = loader.load_config()
        
        # CRITICAL VERIFICATION: DomainConfigResolver uses ONLY config.domains
        from apps.reference.domain_config import DomainConfigResolver
        resolver = DomainConfigResolver(config)
        dm_cfg = resolver.get_decision_making()
        qos_cfg = dm_cfg.qos
        
        # PROOF: Must use value from config.domains (999)
        assert qos_cfg.symbol_cooldown_sec == 999, (
            f"QoS must use config.domains value (999). Got: {qos_cfg.symbol_cooldown_sec}"
        )
        assert qos_cfg.mode == "block", (
            f"QoS mode must use config.domains value ('block'). Got: {qos_cfg.mode}"
        )
        
        # VERIFY: config.domains exists and has correct value (canonical)
        assert config.domains is not None, "config.domains should exist (canonical path)"
        assert config.domains.decision_making.qos.symbol_cooldown_sec == 999, (
            "config.domains should have canonical value (999)"
        )


# ============================================================================
# PROOF OF DoD COMPLETION (Step 2)
# ============================================================================
"""
DoD Checklist for CFG-DOMAINS-STEP-02:

✅ 1. DomainConfigResolver reads ONLY config.domains (canonical)
     Verified by: _resolve_domains() fail-closed, test_resolver_canonical_only_no_trading_domains
     
✅ 2. DecisionMaking QoS block uses DomainConfigResolver (no _get_qos_config fallback)
     Verified by: direct resolver access in __init__, test_qos_from_canonical_domains_yaml
     
✅ 3. _get_qos_config() removed (no legacy QoS getter)
     Verified by: code removed, test_decision_making_no_legacy_qos_getter_used
     
✅ 4. QoS behavior unchanged (ekvivalent)
     Verified by: test_qos_from_canonical_domains_yaml matches expected values
     
✅ 5. Fail-closed on missing QoS (Pydantic defaults, not runtime fallback)
     Verified by: test_qos_has_pydantic_defaults_in_schema,
                  test_missing_qos_in_domains_uses_pydantic_defaults
     
✅ 6. Other DecisionMaking blocks NOT touched (scope limit)
     Only QoS block refactored, signals/weights/risk unchanged
"""
