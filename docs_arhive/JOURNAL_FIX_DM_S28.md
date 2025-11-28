# JOURNAL_FIX_DM_S28

Журнал фіксує всі зміни, пов’язані з виправленням equity=0 (S28) у домені decision_making та уніфікацією джерела equity для sizing.

## TASK DM-S28 — Initial context

- Проблема: DecisionMaking іноді бачить equity=0 при живому портфелі (equity_free_usdt > 0, є відкриті позиції).
- Наслідок: sizing дає quantity=0 → всі TRADE_INTENT відхиляються.
- Ціль: ввести чіткий контракт `PortfolioSnapshot` і єдине джерело equity для всіх розрахунків у decision_making.

## DM-S28.1 — Equity usage inventory

| File | Function / class | Source of equity | Usage | Notes |
|------|------------------|------------------|-------|-------|
| decision_making.py | `on_portfolio` | `event.pld.equity_free_usdt` cached into `_cached_equity_free_usdt` | cache to avoid zero overwrite | Source is raw portfolio dict/obj, silent zero fallback |
| decision_making.py | `_check_and_trigger_decision_for_symbol` | gate on `latest_portfolio` presence | blocks decisions if portfolio missing | No typing, depends on raw dict |
| decision_making.py | `_make_decision_for_symbol` | context["portfolio"] → equity via `_cached_equity_free_usdt` | gating + logging | Equity=0 bug when portfolio lacks equity key |
| decision_making.py | `_calculate_position_size` | `_cached_equity_free_usdt` or `portfolio.get("equity_free_usdt")` or `"equity"` | sizing USD → qty | fallback to "0" causes zero-qty intents |

## DM-S28.2 — PortfolioSnapshot contract
- Додано `PortfolioSnapshot` (Pydantic, Decimal) у `apps/reference/domains/decision_making/contracts.py` з полями `equity_total/free/locked_usdt`, `positions_value_usdt`, `timestamp`, `source`; не приймає від’ємні значення.
- Тест: `tests/domains/decision_making/test_decision_making_equity_flow.py::test_portfolio_snapshot_contract_accepts_decimal_and_blocks_negative`.

## DM-S28.3 — Equity source normalization
- Додано `PortfolioProvider` (`apps/reference/domains/decision_making/portfolio_provider.py`): нормалізує raw портфоліо у `PortfolioSnapshot`, тримає `_last_nonzero` (не перезаписує equity>0 нулями), `get_snapshot(prefer_nonzero=True)`.
- DecisionMaking:
  - При `on_portfolio` інжектує snapshot через provider, логує equity_free/total, positions_count з raw payload.
  - Decision context тепер включає `portfolio_snapshot` (typed) + `portfolio` dump для сумісності.
  - Гейт `latest_portfolio` замінено на `portfolio_provider.has_snapshot`.
  - `_make_decision_for_symbol` та `_calculate_position_size` беруть equity з `portfolio_snapshot.equity_free_usdt`; equity<=0 → reason `equity_non_positive`.

## DM-S28.4 — Sizing guardrails
- `_calculate_position_size` тепер відмовляє при equity_free<=0 з явним reason, перед рандерингом USD→qty.
- Повна відмова від кешів `_cached_equity_*`; SSOT = PortfolioSnapshot.

## DM-S28.5 — Tests
- Новий файл `tests/domains/decision_making/test_decision_making_equity_flow.py`:
  - контракт PortfolioSnapshot,
  - sizing з equity>0 дає qty>0,
  - sizing з equity=0 → reject reason contains equity,
  - provider `prefer_nonzero` тримає останній позитивний snapshot.

## DM-S28.6 — Test snapshot after fix
- `pytest tests/domains/decision_making -q` → 4 passed.
- `pytest tests/domains/execution_position -q` → 0 failed, 573 passed, 11 skipped, 2 xfailed (A/B replay).
