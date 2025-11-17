#!/usr/bin/env python3
"""Tests for dual-mode execution manage and brackets config resolvers with config v2 support."""

import pytest
from decimal import Decimal
from unittest.mock import patch
from pathlib import Path

import yaml

from apps.reference.config_loader import AuroraConfig
from apps.reference.config_models import ConfigV2
from apps.reference.domains.execution_position.manage_config import (
    resolve_execution_manage_config,
    ExecutionManageConfig,
    _get_v2_execution_manage_cfg,
    clear_manage_config_cache,
)
from apps.reference.domains.execution_position.brackets_config import (
    resolve_brackets_config,
    ResolvedBrackets,
    _get_v2_execution_brackets_cfg,
)


class TestExecutionManageV2:
    """Test dual-mode execution manage config resolution."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_manage_config_cache()

    def test_legacy_only_behavior(self):
        """Test that legacy config works without v2."""
        mock_config = {
            "trading": {
                "execution": {
                    "manage": {
                        "auto": True,
                        "orphan_monitor": {
                            "enabled": True,
                            "periodic_interval_sec": 300,
                        },
                        "quick_profit": {
                            "enabled": True,
                            "target_usd": "3.0",
                        },
                        "brackets": {
                            "enable": True,
                            "oco_emulation": False,
                        },
                    },
                }
            }
        }

        cfg = AuroraConfig(trading=mock_config["trading"])
        manage_cfg = resolve_execution_manage_config(cfg)

        assert isinstance(manage_cfg, ExecutionManageConfig)
        assert manage_cfg.source == "legacy"
        assert manage_cfg.auto is True
        assert manage_cfg.orphan_monitor.enabled is True
        assert manage_cfg.quick_profit.target_usd == Decimal("3.0")
        assert manage_cfg.brackets.enable is True

    def test_v2_config_priority(self):
        """Test that v2 config takes priority over legacy."""
        mock_config = {
            "trading": {
                "execution": {
                    "manage": {
                        "auto": False,  # legacy value
                        "quick_profit": {
                            "target_usd": "1.0",  # legacy value
                        },
                    },
                }
            }
        }

        v2_data = {
            "domains": {
                "execution": {
                    "manage": {
                        "auto": True,  # v2 value
                        "quick_profit": {
                            "target_usd": "5.0",  # v2 value
                        },
                        "orphan_monitor": {
                            "enabled": True,
                        },
                        "brackets": {
                            "enable": True,
                            "sl": {"fixed_bps": "35"},
                            "tp": {"fixed_bps": "70"},
                        },
                        "guardian": {
                            "unified": False,
                            "emit_tidy_event": False,
                            "poll_interval_ms": 1500,
                            "cleanup_ttl_ms": 9000,
                            "symbol_cooldown_ms": 7000,
                        },
                        "watchdog": {
                            "ack_ttl_ms": 123,
                            "fill_ttl_ms": 999,
                            "check_interval_ms": 222,
                        },
                    },
                    "brackets": {
                        "sl": {"fixed_bps": "30"},  # v2
                        "tp": {"fixed_bps": "60"},  # v2
                        "offset_bps": 15,
                    }
                }
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(**v2_data))
        manage_cfg = resolve_execution_manage_config(cfg)

        assert manage_cfg.source == "config_v2"
        assert manage_cfg.auto is True  # v2 priority
        assert manage_cfg.quick_profit.target_usd == Decimal(
            "5.0")  # v2 priority
        assert manage_cfg.guardian.poll_interval_ms == 1500
        assert manage_cfg.guardian.cleanup_ttl_ms == 9000
        assert manage_cfg.guardian.symbol_cooldown_ms == 7000
        assert manage_cfg.watchdog.ack_ttl_ms == 123
        assert manage_cfg.watchdog.fill_ttl_ms == 999
        assert manage_cfg.watchdog.source == "config_v2"

    def test_v2_fallback_on_error(self):
        """Test fallback to legacy when v2 config is invalid."""
        mock_config = {
            "trading": {
                "execution": {
                    "manage": {
                        "auto": True,
                        "quick_profit": {
                            "target_usd": "2.0",
                        },
                    },
                }
            }
        }

        v2_data = {
            "domains": {
                "execution": {
                    "manage": {
                        "quick_profit": {
                            "target_usd": "invalid",  # invalid value to trigger error
                        },
                    }
                }
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(**v2_data))
        manage_cfg = resolve_execution_manage_config(cfg)

        assert manage_cfg.source == "legacy"  # fallback
        assert manage_cfg.auto is True  # legacy value


class TestBracketsConfigV2:
    """Test dual-mode brackets config resolution."""

    def test_legacy_only_behavior(self):
        """Test that legacy config works without v2."""
        mock_config = {
            "trading": {
                "execution": {
                    "manage": {
                        "brackets": {
                            "sl": {"fixed_bps": "25"},
                            "tp": {"fixed_bps": "50"},
                            "offset_bps": 10,
                        },
                    },
                }
            }
        }

        cfg = AuroraConfig(trading=mock_config["trading"])
        brackets_cfg = resolve_brackets_config(cfg)

        assert isinstance(brackets_cfg, ResolvedBrackets)
        assert brackets_cfg.source == "legacy"
        assert brackets_cfg.sl_bps == Decimal("25")
        assert brackets_cfg.tp_bps == Decimal("50")
        assert brackets_cfg.offset_bps == 10

    def test_v2_config_priority(self):
        """Test that v2 config takes priority over legacy."""
        mock_config = {
            "trading": {
                "execution": {
                    "manage": {
                        "brackets": {
                            "sl": {"fixed_bps": "20"},  # legacy
                            "tp": {"fixed_bps": "40"},  # legacy
                        },
                    },
                }
            }
        }

        v2_data = {
            "domains": {
                "execution": {
                    "brackets": {
                        "sl": {"fixed_bps": "30"},  # v2
                        "tp": {"fixed_bps": "60"},  # v2
                        "offset_bps": 15,
                    }
                }
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(**v2_data))
        brackets_cfg = resolve_brackets_config(cfg)

        assert brackets_cfg.source == "config_v2"
        assert brackets_cfg.sl_bps == Decimal("30")  # v2 priority
        assert brackets_cfg.tp_bps == Decimal("60")  # v2 priority
        assert brackets_cfg.offset_bps == 15

    def test_v2_fallback_on_error(self):
        """Test fallback to legacy when v2 config is invalid."""
        mock_config = {
            "trading": {
                "execution": {
                    "manage": {
                        "brackets": {
                            "sl": {"fixed_bps": "25"},
                            "tp": {"fixed_bps": "50"},
                        },
                    },
                }
            }
        }

        v2_data = {
            "domains": {
                "execution": {
                    "brackets": {
                        # invalid to trigger error
                        "sl": {"fixed_bps": "invalid"},
                    },
                    "manage": {
                        "brackets": {
                            "sl": {"fixed_bps": "70"},
                            "tp": {"fixed_bps": "140"},
                        }
                    },
                }
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(**v2_data))
        brackets_cfg = resolve_brackets_config(cfg)

        assert brackets_cfg.source == "legacy"  # fallback
        assert brackets_cfg.sl_bps == Decimal("25")  # legacy value

    def test_repository_execution_yaml_brackets_source(self):
        """Ensure the canonical config/domains/execution.yaml drives resolver output."""
        execution_yaml = Path(__file__).resolve(
        ).parents[3] / "config" / "domains" / "execution.yaml"
        if not execution_yaml.exists():
            execution_yaml = Path(__file__).resolve(
            ).parents[2] / "config" / "domains" / "execution.yaml"
        execution_cfg = yaml.safe_load(
            execution_yaml.read_text(encoding="utf-8"))

        cfg = AuroraConfig(config_v2=ConfigV2(
            domains={"execution": execution_cfg}))
        brackets_cfg = resolve_brackets_config(cfg)

        assert brackets_cfg.source == "config_v2"
        assert brackets_cfg.sl_bps == Decimal(
            str(execution_cfg["brackets"]["sl"]["fixed_bps"]))
        assert brackets_cfg.tp_bps == Decimal(
            str(execution_cfg["brackets"]["tp"]["fixed_bps"]))
        assert brackets_cfg.offset_bps == execution_cfg["brackets"].get(
            "offset_bps", 0)
