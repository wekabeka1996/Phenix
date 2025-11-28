# Hybrid Mode Fix — Quick Summary

**Problem**: AuroraCore не запускався у гібридному режимі з помилкою:
```
HYBRID_INCOHERENT: Hybrid mode pre-flight check failed.
Reasons: Market data trading_mode is 'testnet', expected 'live'.
```

**Root Cause**:
1. `config/modes.yaml` мав дублікат `full_testnet` (синтаксична помилка)
2. Відсутній `default_profile` → loader завжди вибирав `testnet`
3. Loader не підтримував `default_profile` в modes.yaml

**Solution**:

### 1. Fixed `config/modes.yaml`
- Видалено дублікат `full_testnet`
- Додано `default_profile: shadow_live`

### 2. Updated `apps/reference/config_loader.py`
Метод `_default_trading_mode_from_v2()` тепер читає `default_profile`:

```python
# Check for explicit default_profile
default_profile_name = modes.get("default_profile") if isinstance(modes, dict) else None
if default_profile_name and default_profile_name in profiles:
    default_profile = profiles[default_profile_name]
    if isinstance(default_profile, dict):
        return default_profile.get("trading_mode", "testnet")
```

**Result**:

### Before
```
Trading mode: testnet
Domain modes:
  market_data: testnet         ❌
  feature_engineering: testnet ❌
  decision_making: testnet     ❌
  execution_position: testnet
  risk_management: testnet
```

### After
```
Trading mode: hybrid_live_data_testnet_exec ✅
Domain modes:
  market_data: live               ✅ (реальні дані ринку)
  feature_engineering: live       ✅ (реальні метрики)
  decision_making: live           ✅ (реальний аналіз)
  execution_position: testnet     ✅ (ордери на testnet)
  risk_management: testnet        ✅ (портфель з testnet)
  audit_trail: live               ✅
```

### AuroraCore Startup
```
✅ Hybrid mode pre-flight check passed.
✅ HYBRID: OK (live data, testnet exec)
✅ AccountConnector is configured for TESTNET execution environment
```

**Гібридний режим активний**:
- Всі метрики, дані ринку, аналіз — з **live** біржі
- Виставлення ордерів, управління портфелем — на **testnet**

**Files Modified**:
- `config/modes.yaml` (+2 lines: видалено дублікат, додано default_profile)
- `apps/reference/config_loader.py` (+7 lines: підтримка default_profile)
- `apps/reference/config/modes.yaml` (synced from config/)
