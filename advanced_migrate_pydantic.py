#!/usr/bin/env python3
"""
Advanced Pydantic Migration Script - Phase 2
Handles complex .get() patterns that require special logic
"""

import re
import ast
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class AdvancedPydanticMigrator:
    def __init__(self):
        # Complex patterns that need special handling
        self.complex_patterns = {
            # Multi-level config access
            r'config\.get\("trading",\s*\{\}\)\.get\("decision",\s*\{\}\)\.get\("([^"]+)",\s*([^)]+)\)': r'self.config.trading.decision.\1',
            r'self\.config\.get\("trading",\s*\{\}\)\.get\("decision",\s*\{\}\)\.get\("([^"]+)",\s*([^)]+)\)': r'self.config.trading.decision.\1',

            # Dynamic key access patterns
            r'decision_config\.get\(mode,\s*\{\}\)': r'getattr(self.config.trading.decision, mode, {})',
            r'regime_thresholds_cfg\.get\(regime_name\)': r'getattr(self.config.trading.decision.regime_thresholds, regime_name, None)',
            r'regime_thresholds_cfg\.get\("DEFAULT",\s*"([^"]+)"\)': r'getattr(self.config.trading.decision.regime_thresholds, "DEFAULT", "\1")',

            # Complex nested access with fallbacks
            r'exec_cfg\.get\("brackets",\s*\{\}\)': r'self.config.trading.execution.brackets',
            r'exec_cfg\.get\("manage",\s*\{\}\)': r'self.config.trading.execution.manage',

            # Trading mode conditional access
            r'api_config\.get\("live",\s*\{\}\)': r'self.config.binance_api.live',
            r'api_config\.get\("testnet",\s*\{\}\)': r'self.config.binance_api.testnet',

            # Feature engineering config access
            r'config\.get\("trading",\s*\{\}\)\.get\("feature_engineering",\s*\{\}\)': r'self.config.trading.feature_engineering',
            r'market_data_config\.get\("macro_sync",\s*\{\}\)': r'self.config.trading.market_data.macro_sync',

            # Risk management access
            r'cfg\.get\("risk"\)\.get\("daily"\)': r'self.config.risk.daily',

            # Complex multi-line patterns (these need manual review)
            r'self\.config\.get\("trading",\s*self\.config\)': r'self.config.trading',
            r'trading_config\.get\("mode",\s*"production"\)': r'self.config.trading.mode',
        }

        # Patterns that need try/except guards
        self.fallback_patterns = {
            # Config access that might fail
            r'config\.get\("account_observer",\s*\{\}\)': r'self.config.account_observer',
            r'config\.get\("trading",\s*\{\}\)': r'self.config.trading',
            r'account_observer_config\.get\("symbols"\)': r'self.config.account_observer.symbols',
            r'trading_config\.get\("symbols"': r'self.config.trading.symbols',

            # Complex config with isinstance checks
            r'kelly_cfg\.get\("([^"]+)",\s*([^)]+)\)\s*if isinstance\(kelly_cfg, dict\) else ([^)]+)': r'self.config.trading.decision.kelly.\1',
            r'sizing_cfg\.get\("([^"]+)",\s*([^)]+)\)\s*if isinstance\(sizing_cfg, dict\) else ([^)]+)': r'self.config.trading.decision.position_sizing.\1',

            # Volatility config patterns
            r'volatility_config\.get\("([^"]+)",\s*([^)]+)\)\s*if isinstance\(volatility_config, dict\) else ([^)]+)': r'self.config.trading.regime_detector.volatility.\1',
        }

    def migrate_file(self, file_path: str) -> Tuple[bool, List[str]]:
        """Migrate a single file with advanced patterns"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            original_content = content
            changes = []

            # Apply complex patterns first
            for pattern, replacement in self.complex_patterns.items():
                matches = re.findall(pattern, content)
                if matches:
                    content = re.sub(pattern, replacement, content)
                    changes.append(
                        f"Applied complex pattern: {pattern} -> {replacement}")

            # Apply fallback patterns
            for pattern, replacement in self.fallback_patterns.items():
                matches = re.findall(pattern, content)
                if matches:
                    content = re.sub(pattern, replacement, content)
                    changes.append(
                        f"Applied fallback pattern: {pattern} -> {replacement}")

            # Handle special cases that need manual intervention
            content = self._handle_special_cases(content, file_path)

            if content != original_content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                return True, changes
            else:
                return False, []

        except Exception as e:
            return False, [f"Error migrating {file_path}: {str(e)}"]

    def _handle_special_cases(self, content: str, file_path: str) -> str:
        """Handle special cases that require custom logic"""

        # Handle multi-line config access in decision_making.py
        if 'decision_making.py' in file_path:
            # Replace complex config initialization
            content = re.sub(
                r'decision_config = trading_config\.get\("decision",\s*self\.config\.get\(',
                'decision_config = self.config.trading.decision',
                content
            )

            # Handle QoS config access
            content = re.sub(
                r'exp_cooldown = qos_config\.get\(\s*([^,]+),\s*([^)]+)\)',
                r'exp_cooldown = self.config.trading.decision.qos.\1',
                content
            )

            content = re.sub(
                r'max_intents = qos_config\.get\(\s*([^,]+),\s*([^)]+)\)',
                r'max_intents = self.config.trading.decision.qos.\1',
                content
            )

        # Handle exposure guard complex access
        if 'exposure_guard.py' in file_path:
            # Replace complex exposure config access
            content = re.sub(
                r'max_eq_util = exposure_config\.get\(\s*([^,]+),\s*([^)]+)\)',
                r'max_eq_util = self.config.trading.exposure.\1',
                content
            )

        # Handle FSM complex access
        if 'fsm.py' in file_path or 'fsm_manage.py' in file_path:
            # Replace complex execution config access
            content = re.sub(
                r'exec_cfg = \(self\.config\.get\("trading",\s*\{\}\)',
                r'exec_cfg = self.config.trading',
                content
            )

            content = re.sub(
                r'brackets_cfg = \(exec_cfg\.get\("manage",\s*\{\}\)',
                r'brackets_cfg = self.config.trading.execution.manage',
                content
            )

        return content


def main():
    migrator = AdvancedPydanticMigrator()

    # Focus on the most problematic files first
    priority_files = [
        "apps/reference/domains/decision_making/decision_making.py",
        "apps/reference/domains/execution_position/exposure_guard.py",
        "apps/reference/domains/execution_position/fsm.py",
        "apps/reference/domains/execution_position/fsm_manage.py",
        "apps/reference/domains/feature_engineering/feature_engineering.py",
        "apps/reference/domains/feature_engineering/feature_engineering_phase1.py",
        "apps/reference/domains/market_data/market_data_connector.py",
        "apps/reference/domains/regime_detector/regime_detector.py",
        "apps/reference/domains/risk_management/daily_gate.py",
        "apps/reference/domains/account_balance/account_connector.py",
        "apps/reference/domains/account_observer/account_observer.py",
    ]

    total_changes = 0
    for file_path in priority_files:
        if os.path.exists(file_path):
            changed, changes = migrator.migrate_file(file_path)
            if changed:
                print(f"✅ Advanced migration for {file_path}:")
                for change in changes:
                    print(f"   {change}")
                total_changes += len(changes)
            else:
                print(f"⚪ No advanced changes needed for {file_path}")
        else:
            print(f"❌ File not found: {file_path}")

    print(
        f"\n📊 Advanced migration complete! Total complex replacements: {total_changes}")


if __name__ == "__main__":
    main()
