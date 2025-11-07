#!/usr/bin/env python3
"""
Automated Pydantic Migration Script
Replaces .get() calls with Pydantic-first access patterns
"""

import re
import ast
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class PydanticMigrator:
    def __init__(self):
        # Patterns for different config access types
        self.patterns = {
            # self.config.get("trading", {}).get("decision", {}).get("kelly_cap")
            r'self\.config\.get\("trading",\s*\{\}\)\.get\("decision",\s*\{\}\)\.get\("([^"]+)",\s*([^)]+)\)': r'self.config.trading.decision.\1',
            # self.config.get("trading", {}).get("decision", {})
            r'self\.config\.get\("trading",\s*\{\}\)\.get\("decision",\s*\{\}\)': r'self.config.trading.decision',
            # trading_config.get("decision", {})
            r'trading_config\.get\("decision",\s*\{\}\)': r'self.config.trading.decision',
            # decision_config.get("kelly_cap", default)
            r'decision_config\.get\("([^"]+)",\s*([^)]+)\)': r'self.config.trading.decision.\1',
            # sizing_config.get("min_position_size_usd", default)
            r'sizing_config\.get\("([^"]+)",\s*([^)]+)\)': r'self.config.trading.decision.position_sizing.\1',
            # qos_config.get("symbol_cooldown_sec", default)
            r'qos_config\.get\("([^"]+)",\s*([^)]+)\)': r'self.config.trading.decision.qos.\1',
            # features_config.get("ttl_sec", default)
            r'features_config\.get\("([^"]+)",\s*([^)]+)\)': r'self.config.trading.decision.features.\1',
            # bar_gate_cfg.get("enable", default)
            r'bar_gate_cfg\.get\("([^"]+)",\s*([^)]+)\)': r'self.config.trading.decision.bar_gating.\1',
            # behavior_cfg.get("enable", default)
            r'behavior_cfg\.get\("([^"]+)",\s*([^)]+)\)': r'self.config.trading.decision.behavior_fsm.\1',
            # signals_cfg.get("normalize", default)
            r'signals_cfg\.get\("([^"]+)",\s*([^)]+)\)': r'self.config.trading.decision.signals.\1',
            # exposure_config.get("max_eq_util", default)
            r'exposure_config\.get\("([^"]+)",\s*([^)]+)\)': r'self.config.trading.exposure.\1',
            # side_config.get("long", default)
            r'side_config\.get\("([^"]+)",\s*([^)]+)\)': r'self.config.trading.exposure.side_limits.\1',
            # leverage_config.get("__default__", default)
            r'leverage_config\.get\("__default__",\s*([^)]+)\)': r'self.config.trading.exposure.leverage.__default__',
            # leverage_config.get(symbol, default)
            r'leverage_config\.get\((\w+),\s*([^)]+)\)': r'self.config.trading.exposure.leverage.get(\1, \2)',
            # api_config.get("live", {})
            r'api_config\.get\("live",\s*\{\}\)': r'self.config.binance_api.live',
            # api_config.get("testnet", {})
            r'api_config\.get\("testnet",\s*\{\}\)': r'self.config.binance_api.testnet',
            # env_config.get("api_key")
            r'env_config\.get\("api_key"\)': r'self.config.binance_api.live.api_key if self.config.trading_mode == "live" else self.config.binance_api.testnet.api_key',
            # env_config.get("api_secret")
            r'env_config\.get\("api_secret"\)': r'self.config.binance_api.live.api_secret if self.config.trading_mode == "live" else self.config.binance_api.testnet.api_secret',
            # env_config.get("rest_url")
            r'env_config\.get\("rest_url"\)': r'self.config.binance_api.live.rest_url if self.config.trading_mode == "live" else self.config.binance_api.testnet.rest_url',
            # config.get("trading_mode", "testnet")
            r'config\.get\("trading_mode",\s*"([^"]+)"\)': r'self.config.trading_mode',
            # config.get("binance_api", {})
            r'config\.get\("binance_api",\s*\{\}\)': r'self.config.binance_api',
            # account_observer_config.get("poll_interval", default)
            r'account_observer_config\.get\("([^"]+)",\s*([^)]+)\)': r'self.config.account_observer.\1',
            # trading_config.get("symbols", default)
            r'trading_config\.get\("symbols",\s*([^)]+)\)': r'self.config.trading.symbols',
            # market_data_config.get("macro_sync", {})
            r'market_data_config\.get\("macro_sync",\s*\{\}\)': r'self.config.trading.market_data.macro_sync',
            # macro_sync_config.get("anchors", [])
            r'macro_sync_config\.get\("anchors",\s*\[\]\)': r'self.config.trading.market_data.macro_sync.anchors',
            # macro_sync_config.get("enabled", True)
            r'macro_sync_config\.get\("enabled",\s*([^)]+)\)': r'self.config.trading.market_data.macro_sync.enabled',
            # macro_sync_config.get("window", 60)
            r'macro_sync_config\.get\("window",\s*([^)]+)\)': r'self.config.trading.market_data.macro_sync.window',
            # fe_config.get("ema", {})
            r'fe_config\.get\("ema",\s*\{\}\)': r'self.config.trading.feature_engineering.ema',
            # fe_config.get("volume", {})
            r'fe_config\.get\("volume",\s*\{\}\)': r'self.config.trading.feature_engineering.volume',
            # fe_config.get("volatility", {})
            r'fe_config\.get\("volatility",\s*\{\}\)': r'self.config.trading.feature_engineering.volatility',
            # fe_config.get("liquidity", {})
            r'fe_config\.get\("liquidity",\s*\{\}\)': r'self.config.trading.feature_engineering.liquidity',
            # ema_config.get("period_short", 3)
            r'ema_config\.get\("period_short",\s*([^)]+)\)': r'self.config.trading.feature_engineering.ema.period_short',
            # volume_config.get("window_sec", 60)
            r'volume_config\.get\("window_sec",\s*([^)]+)\)': r'self.config.trading.feature_engineering.volume.window_sec',
            # volatility_config.get("sma_length", 10)
            r'volatility_config\.get\("sma_length",\s*([^)]+)\)': r'self.config.trading.feature_engineering.volatility.sma_length',
            # liquidity_config.get("depth_half", "100")
            r'liquidity_config\.get\("depth_half",\s*"([^"]+)"\)': r'self.config.trading.feature_engineering.liquidity.depth_half',
            # models_cfg.get("sma_trend", {})
            r'models_cfg\.get\("sma_trend",\s*\{\}\)': r'self.config.trading.regime_detector.models.sma_trend',
            # model_config.get("short_period", 10)
            r'model_config\.get\("short_period",\s*([^)]+)\)': r'self.config.trading.regime_detector.models.sma_trend.short_period',
            # vol_cfg.get("atr_period", 14)
            r'vol_cfg\.get\("atr_period",\s*([^)]+)\)': r'self.config.trading.regime_detector.models.volatility.atr_period',
            # risk_config.get("max_daily_drawdown_pct")
            r'risk_config\.get\("max_daily_drawdown_pct"\)': r'self.config.risk.max_daily_drawdown_pct',
            # rcfg.get("max_realized_loss_usd", 250)
            r'rcfg\.get\("max_realized_loss_usd",\s*([^)]+)\)': r'self.config.risk.daily.max_realized_loss_usd',
            # rcfg.get("reset_time_utc", "00:00")
            r'rcfg\.get\("reset_time_utc",\s*"([^"]+)"\)': r'self.config.risk.daily.reset_time_utc',
            # brackets_cfg.get("sl", {})
            r'brackets_cfg\.get\("sl",\s*\{\}\)': r'self.config.trading.execution.brackets.sl',
            # brackets_cfg.get("tp", {})
            r'brackets_cfg\.get\("tp",\s*\{\}\)': r'self.config.trading.execution.brackets.tp',
            # sl_cfg.get("fixed_bps", 50)
            r'sl_cfg\.get\("fixed_bps",\s*([^)]+)\)': r'self.config.trading.execution.brackets.sl.fixed_bps',
            # tp_cfg.get("fixed_bps", 100)
            r'tp_cfg\.get\("fixed_bps",\s*([^)]+)\)': r'self.config.trading.execution.brackets.tp.fixed_bps',
            # exec_cfg.get("brackets", {})
            r'exec_cfg\.get\("brackets",\s*\{\}\)': r'self.config.trading.execution.brackets',
            # exec_config.get("cooldown_ms", 1000)
            r'exec_config\.get\("cooldown_ms",\s*([^)]+)\)': r'self.config.trading.execution.cooldown_ms',
            # exec_config.get("guard_enabled", True)
            r'exec_config\.get\("guard_enabled",\s*([^)]+)\)': r'self.config.trading.execution.guard_enabled',
            # manage_cfg.get("orphan_monitor", {})
            r'manage_cfg\.get\("orphan_monitor",\s*\{\}\)': r'self.config.trading.execution.manage.orphan_monitor',
            # orphan_cfg.get("enabled", True)
            r'orphan_cfg\.get\("enabled",\s*([^)]+)\)': r'self.config.trading.execution.manage.orphan_monitor.enabled',
            # orphan_cfg.get("run_on_startup", True)
            r'orphan_cfg\.get\("run_on_startup",\s*([^)]+)\)': r'self.config.trading.execution.manage.orphan_monitor.run_on_startup',
            # orphan_cfg.get("periodic_interval_sec", 300)
            r'orphan_cfg\.get\("periodic_interval_sec",\s*([^)]+)\)': r'self.config.trading.execution.manage.orphan_monitor.periodic_interval_sec',
            # orphan_cfg.get("min_order_age_sec", 0)
            r'orphan_cfg\.get\("min_order_age_sec",\s*([^)]+)\)': r'self.config.trading.execution.manage.orphan_monitor.min_order_age_sec',
            # orphan_cfg.get("batch_cancel_limit", 50)
            r'orphan_cfg\.get\("batch_cancel_limit",\s*([^)]+)\)': r'self.config.trading.execution.manage.orphan_monitor.batch_cancel_limit',
            # orphan_cfg.get("rate_limit_per_min", 120)
            r'orphan_cfg\.get\("rate_limit_per_min",\s*([^)]+)\)': r'self.config.trading.execution.manage.orphan_monitor.rate_limit_per_min',
            # watchdog_config.get("ack_ttl_ms", 8000)
            r'watchdog_config\.get\("ack_ttl_ms",\s*([^)]+)\)': r'self.config.trading.execution.manage.watchdog.ack_ttl_ms',
            # watchdog_config.get("fill_ttl_ms", 30000)
            r'watchdog_config\.get\("fill_ttl_ms",\s*([^)]+)\)': r'self.config.trading.execution.manage.watchdog.fill_ttl_ms',
            # brackets_config.get("enable", False)
            r'brackets_config\.get\("enable",\s*([^)]+)\)': r'self.config.trading.execution.brackets.enable',
            # emergency_cfg.get("enable", False)
            r'emergency_cfg\.get\("enable",\s*([^)]+)\)': r'self.config.trading.execution.manage.emergency.enable',
            # emergency_cfg.get("emergency_sl_bps", 200)
            r'emergency_cfg\.get\("emergency_sl_bps",\s*([^)]+)\)': r'self.config.trading.execution.manage.emergency.emergency_sl_bps',
            # trailing_config.get("cooldown_sec", 30)
            r'trailing_config\.get\("cooldown_sec",\s*([^)]+)\)': r'self.config.trading.execution.manage.trailing.cooldown_sec',
            # trailing_config.get("step_bps", 10)
            r'trailing_config\.get\("step_bps",\s*([^)]+)\)': r'self.config.trading.execution.manage.trailing.step_bps',
            # config.get("interval_sec", 300)
            r'config\.get\("interval_sec",\s*([^)]+)\)': r'self.config.ops.snapshots.interval_sec',
            # config.get("snapshot_dir", "ops/snapshots")
            r'config\.get\("snapshot_dir",\s*"([^"]+)"\)': r'self.config.ops.snapshots.snapshot_dir',
            # config.get("domains", ["position_tracking"])
            r'config\.get\("domains",\s*\[([^\]]+)\]\)': r'self.config.ops.snapshots.domains',
        }

    def migrate_file(self, file_path: str) -> Tuple[bool, List[str]]:
        """Migrate a single file by replacing .get() calls with Pydantic access"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            original_content = content
            changes = []

            # Apply all patterns
            for pattern, replacement in self.patterns.items():
                matches = re.findall(pattern, content)
                if matches:
                    content = re.sub(pattern, replacement, content)
                    changes.extend(
                        [f"Replaced {len(matches)} occurrences of pattern: {pattern} -> {replacement}"])

            # Special handling for complex cases that need try/except blocks
            content = self._add_fallback_guards(content, file_path)

            if content != original_content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                return True, changes
            else:
                return False, []

        except Exception as e:
            return False, [f"Error migrating {file_path}: {str(e)}"]

    def _add_fallback_guards(self, content: str, file_path: str) -> str:
        """Add try/except fallback guards for complex config access"""
        # This is a simplified version - in practice, we'd need more sophisticated AST analysis
        # For now, we'll focus on the pattern replacements above
        return content


def main():
    migrator = PydanticMigrator()

    # Files to migrate based on the test output
    files_to_migrate = [
        "apps/reference/domains/decision_making/decision_making.py",
        "apps/reference/domains/execution_position/exposure_guard.py",
        "apps/reference/domains/execution_position/fsm.py",
        "apps/reference/domains/execution_position/fsm_manage.py",
        "apps/reference/domains/feature_engineering/feature_engineering.py",
        "apps/reference/domains/feature_engineering/feature_engineering_phase1.py",
        "apps/reference/domains/market_data/market_data_connector.py",
        "apps/reference/domains/position_tracking/position_tracking.py",
        "apps/reference/domains/regime_detector/regime_detector.py",
        "apps/reference/domains/risk_management/daily_gate.py",
        "apps/reference/domains/risk_management/risk_management.py",
        "apps/reference/domains/snapshot_scheduler/snapshot_scheduler.py",
        "apps/reference/domains/account_balance/account_connector.py",
        "apps/reference/domains/account_observer/account_observer.py",
    ]

    total_changes = 0
    for file_path in files_to_migrate:
        if os.path.exists(file_path):
            changed, changes = migrator.migrate_file(file_path)
            if changed:
                print(f"✅ Migrated {file_path}:")
                for change in changes:
                    print(f"   {change}")
                total_changes += len(changes)
            else:
                print(f"⚪ No changes needed for {file_path}")
        else:
            print(f"❌ File not found: {file_path}")

    print(
        f"\n📊 Migration complete! Total pattern replacements: {total_changes}")


if __name__ == "__main__":
    main()
