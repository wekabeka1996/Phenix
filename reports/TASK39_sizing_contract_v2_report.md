# TASK39-I — Sizing Contract v2 + Fixed Qty/Notional (Remove Legacy 10% Fallback)

## Summary (Before/After)

**Before**
- При відсутньому `risk_contract_v1` sizing міг непомітно падати в legacy fallback `equity * 0.1` (10%).
- Не було SSOT-режиму “візьми рівно 1 SOL” / “візьми рівно $30”.
- Частина логіки sizing залежала від того, що стратегія принесе `position_size_usd`/hint-и.

**After**
- Legacy fallback `equity * 0.1` **видалено**: відсутній sizing-контракт → **fail-closed** з причиною `NRR-SIZING-CONTRACT-MISSING`.
- Додано 3 явні режими sizing (SSOT):
  - `percent_equity`
  - `fixed_notional_usd`
  - `fixed_qty` (per-symbol мапа)
- `DecisionMaking` сам рахує `qty` для strategy-gateway (не вимагає `position_size_usd` від стратегії).
- Округлення `qty` по `step_size` виконується детерміновано (Decimal + ROUND_DOWN).

---

## Config (SSOT)

Додано секцію `decision_making.position_sizing.sizing`:

- `config/aurora/domains.yaml`
- `config/aurora/trading.yaml`

Приклад:

```yaml
sizing:
  mode: fixed_qty
  fixed_qty:
    SOLUSDT: 1.0
```

---

## Changed / Added Files

**Config / Models**
- `apps/reference/config_models.py` — додано `SizingV2Config` (валидація mode/параметрів).
- `config/aurora/domains.yaml` — SSOT для `decision_making.position_sizing.sizing`.
- `config/aurora/trading.yaml` — mirror конфіг для трейдинг-пайплайну.

**DecisionMaking**
- `apps/reference/domains/decision_making/decision_making.py` — `_calculate_position_size()` підтримує `fixed_qty/fixed_notional_usd/percent_equity`, без legacy 10% fallback; strategy-gateway сам рахує `qty`.

**Tests**
- `tests/domains/decision_making/test_task39_sizing_contract_v2.py`
- `tests/integration/test_task39_sizing_gateway_fixed_qty.py`

---

## Test Outputs (required)

Command:
`pytest -q tests/domains/decision_making/test_task39_sizing_contract_v2.py tests/integration/test_task39_sizing_gateway_fixed_qty.py`

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.1, pluggy-1.6.0
rootdir: /home/wekabeka/Музыка/Phenix
configfile: pytest.ini
collected 6 items

tests/domains/decision_making/test_task39_sizing_contract_v2.py .....    [ 83%]
tests/integration/test_task39_sizing_gateway_fixed_qty.py .              [100%]

============================== 6 passed in 0.14s ===============================
```

