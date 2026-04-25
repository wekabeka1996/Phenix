import os
import re

# Мапа рефакторингу: Модель -> Новий шлях
updates = {
    'DecisionMakingDomainConfig': 'apps/reference/config/domains/decision_making.py',
    'ExecutionPositionDomainConfig': 'apps/reference/config/domains/execution_position.py',
    'FeatureEngineeringDomainConfig': 'apps/reference/config/domains/feature_engineering.py',
    'ShadowTelemetryDomainConfig': 'apps/reference/config/domains/shadow_telemetry.py',
    'RiskManagementDomainConfig': 'apps/reference/config/domains/risk_management.py',
    'PositionTrackingDomainConfig': 'apps/reference/config/domains/position_tracking.py',
    'ObjectiveEngineDomainConfig': 'apps/reference/config/domains/objective_engine.py',
    'TAFeaturesDomainConfig': 'apps/reference/config/domains/ta_features.py',
    'DomainsConfig': 'apps/reference/config/domains/_aggregator.py',
    'SystemMarketDataConfig': 'apps/reference/config/system/market_data.py',
    'OpsConfig': 'apps/reference/config/system/ops.py',
    'SystemMetaConfig': 'apps/reference/config/system/observability.py',
    'TrailingDefaultsConfig': 'apps/reference/config/strategies/common.py',
    'TCAPrefsConfig': 'apps/reference/config/domains/decision_making.py',
    'RiskBudgetsConfig': 'apps/reference/config/domains/decision_making.py',
    'TradingConfig': 'apps/reference/config/domains/_aggregator.py'
}

docs_dir = 'config/docs'
files_to_process = ['domains_passport.md', 'trading_passport.md']
files_created = 0

print("🚀 Починаю створення альтернативних паспортів (_v2)...")

for filename in files_to_process:
    filepath = os.path.join(docs_dir, filename)
    if not os.path.exists(filepath):
        print(f"⚠️ Файл не знайдено: {filepath}")
        continue
        
    new_filepath = os.path.join(docs_dir, filename.replace('.md', '_v2.md'))
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Хірургічна Regex заміна рядків: apps/reference/config_models.py:XXXX (model: ModelName)
    for model_name, new_path in updates.items():
        # Патерн 1: (model: ModelName)
        pattern = r'apps/reference/config_models\.py:\d+\s+\(model:\s*' + model_name + r'\)'
        replacement = f'{new_path} (model: {model_name})'
        content = re.sub(pattern, replacement, content)
        
        # Патерн 2: (ModelName.field)
        pattern2 = r'apps/reference/config_models\.py:\d+\s+\(' + model_name + r'\.'
        replacement2 = f'{new_path} ({model_name}.'
        content = re.sub(pattern2, replacement2, content)

    # Зберігаємо у НОВИЙ файл
    with open(new_filepath, 'w', encoding='utf-8') as f:
        f.write(content)
        
    print(f'✅ Створено новий файл: {new_filepath}')
    files_created += 1

print(f'\nГотово! Створено файлів: {files_created}. Ви можете порівняти їх з оригіналами.')
