#!/usr/bin/env python3
"""
Config Validation Tool

Validates Aurora configuration files for basic structure and required fields.
Usage: python tools/validate_configs.py
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple
import yaml
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*args, **kwargs):
        return False

# Load environment variables from .env file (best-effort)
load_dotenv()


def load_yaml_file(file_path: Path) -> Dict[str, Any]:
    """Load YAML file and return as dict."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"❌ Error loading {file_path}: {e}")
        return {}


def validate_trading_config(config_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate trading config structure."""
    errors = []

    # Check required top-level sections
    required_sections = ['trading']
    for section in required_sections:
        if section not in config_data:
            errors.append(f"Missing required section: {section}")

    if 'trading' in config_data:
        trading = config_data['trading']

        # Check mode setting
        if 'mode' not in trading:
            errors.append(
                "Missing trading.mode (should be 'testnet' or 'production')")
        elif trading['mode'] not in ['testnet', 'production']:
            errors.append(
                f"Invalid trading.mode: {trading['mode']} (should be 'testnet' or 'production')")

        # Check decision settings
        if 'decision' not in trading:
            errors.append("Missing trading.decision section")
        else:
            decision = trading['decision']
            if 'testnet' not in decision:
                errors.append("Missing trading.decision.testnet settings")
            if 'production' not in decision:
                errors.append("Missing trading.decision.production settings")

        # Check risk settings
        if 'risk' not in trading:
            errors.append("Missing trading.risk section")

        # Check domain configuration
        if 'domain_configuration' not in trading:
            errors.append("Missing trading.domain_configuration")

    return len(errors) == 0, errors


def validate_system_config(config_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate system config structure."""
    errors = []

    # Check config_version
    if 'config_version' not in config_data:
        errors.append("Missing config_version")

    # Check trading_mode
    if 'trading_mode' not in config_data:
        errors.append("Missing trading_mode")
    elif config_data['trading_mode'] not in ['live', 'testnet', 'hybrid_live_data_testnet_exec']:
        errors.append(f"Invalid trading_mode: {config_data['trading_mode']}")

    # Check required sections
    required_sections = ['sequential_tests', 'risk_core', 'kelly']
    for section in required_sections:
        if section not in config_data:
            errors.append(f"Missing required section: {section}")

    return len(errors) == 0, errors


def validate_regime_config(config_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate regime config structure."""
    errors = []

    # Check config_version
    if 'config_version' not in config_data:
        errors.append("Missing config_version")

    # Check hmm section (replaces regimes)
    if 'hmm' not in config_data:
        errors.append("Missing hmm section")

    # Check features section
    if 'features' not in config_data:
        errors.append("Missing features section")

    return len(errors) == 0, errors


def main():
    """Main validation function."""
    print("🔍 Aurora Config Validation Tool")
    print("=" * 50)

    # Define config files and their validators
    config_validations = [
        {
            'config_file': Path('config/aurora/trading.yaml'),
            'validator': validate_trading_config,
            'name': 'Trading Config'
        },
        {
            'config_file': Path('config/aurora/system.yaml'),
            'validator': validate_system_config,
            'name': 'System Config'
        },
        {
            'config_file': Path('config/aurora/regime.yaml'),
            'validator': validate_regime_config,
            'name': 'Regime Config'
        }
    ]

    all_valid = True
    total_errors = []

    for validation in config_validations:
        config_file = validation['config_file']
        validator = validation['validator']
        name = validation['name']

        print(f"\n📋 Validating {name}...")
        print(f"   File: {config_file}")

        # Check if file exists
        if not config_file.exists():
            error = f"❌ Config file not found: {config_file}"
            print(error)
            all_valid = False
            total_errors.append(error)
            continue

        # Load file
        config_data = load_yaml_file(config_file)
        if not config_data:
            all_valid = False
            continue

        # Validate
        is_valid, errors = validator(config_data)

        if is_valid:
            print(f"   ✅ {name} structure is valid")
        else:
            print(f"   ❌ {name} has validation errors:")
            for error in errors:
                print(f"      {error}")
            all_valid = False
            total_errors.extend(errors)

    # Additional checks
    print("\n🔧 Additional checks...")
    # Check for required environment variables
    required_env_vars = ['BINANCE_TESTNET_API_KEY',
                         'BINANCE_TESTNET_API_SECRET']
    missing_env = []
    for var in required_env_vars:
        if not os.getenv(var):
            missing_env.append(var)

    if missing_env:
        print(
            f"   ⚠️  Missing environment variables: {', '.join(missing_env)}")
        print("      Set them in .env file for full functionality")
    else:
        print("   ✅ Required environment variables are set")

    # Summary
    print("\n" + "=" * 50)
    if all_valid:
        print("🎉 All configurations are valid!")
        print("🚀 System ready for deployment")
        return 0
    else:
        print("❌ Configuration validation failed!")
        print(f"Total errors: {len(total_errors)}")
        print("\n💡 Fix the errors above and run validation again")
        return 1


if __name__ == "__main__":
    sys.exit(main())
