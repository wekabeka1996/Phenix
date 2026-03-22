# AURORA ENTRY PRICE FORMULA FORENSIC AUDIT

Дата: 2026-03-22
Статус: Final forensic conclusion

## 1. Executive Verdict
- Поточна runtime-формула entry price для LIMIT/GTX на Aurora підтверджена кодом і логами.
- Підтверджений maker reject кейс Binance -5022, нормалізований у NRR-018 (MAKER_ONLY_REJECT).
- Дефект у формулі формування entry price в DecisionMaking не виявлено.
- Локальний ризик виявлено на етапі execution-округлення ціни для SELL: однакова floor-логіка для BUY/SELL погіршує maker-safety для SELL.

## 2. Runtime Formula (доведено)
Нехай:
- anchor = features.price
- offset = ATR × regime_multiplier

Тоді:
- BUY: entry_price = anchor - offset
- SELL: entry_price = anchor + offset

Далі в open FSM для LIMIT:
- submit_price = floor(entry_price / tick) × tick

## 3. Confirmed Evidence Chain (BTC reject case)
RID: aurora_BTCUSDT_1774131001501

1) ORDER_INTENT зафіксований із ціною 70254.01057142857.
2) GUARD_ADJUST округлив ціну до 70254.0 (tick=0.1).
3) Відправлено LIMIT SELL 0.104 @ 70254.0 з tif=GTX.
4) Біржа повернула -5022 (maker/post-only reject).
5) Подію нормалізовано у ORDER_REJECTED з NRR-018 / MAKER_ONLY_REJECT.

## 4. Side-Safety та Maker-Safety
- Strategy-level side logic коректна:
  - BUY відсувається вниз від anchor (менш агресивно)
  - SELL відсувається вгору від anchor (менш агресивно)
- Execution-level rounding має асиметричний ризик:
  - floor для BUY підсилює maker-safe поведінку
  - floor для SELL зсуває ціну вниз і робить її агресивнішою

Висновок: ризик maker reject локалізований переважно в open FSM rounding, а не у формулі entry price.

## 5. Regime/Bar Awareness
- Regime-aware entry logic активна (ATR × regime multipliers, включно з DEFAULT).
- Bar-aware механіка присутня в TTL/pending-entry policy (valid_for_ms), не в базовій формулі обчислення entry.

## 6. Root Cause Ranking
1. Side-agnostic floor rounding у open guards для SELL.
2. Мікроструктурний рух стакану між intent і submit.
3. Відсутність pre-submit maker-buffer check відносно актуального best bid/ask.

## 7. Design Decision (minimal change)
Рекомендовано мінімальний локальний редизайн у execution_position/fsm_open:
- BUY: floor до tick
- SELL: ceil до tick

Обґрунтування:
- не змінює бізнес-формулу DecisionMaking;
- зберігає LIMIT/GTX політику;
- адресує підтверджений runtime-механізм reject.

## 8. Scope Boundaries
- Без broad refactor.
- Без відключення GTX.
- Без припущень про невидимі runtime дані (best bid/ask snapshot відсутній у наведеному ланцюгу).

## 9. Final Statement
Формула entry price в Aurora є валідною та підтвердженою. Основний вектор покращення для зниження NRR-018 — side-aware rounding в open execution guard для SELL при збереженні maker-only semantics.
