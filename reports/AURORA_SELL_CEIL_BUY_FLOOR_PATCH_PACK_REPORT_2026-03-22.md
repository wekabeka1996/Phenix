# AURORA_SELL_CEIL_BUY_FLOOR_PATCH_PACK — REPORT

## Executive Verdict

Пакет виконано в межах запитаного scope.

Поточний execution-side rounding для LIMIT entry змінено локально і без зміни strategy math:
- BUY тепер округлюється вниз до тіку.
- SELL тепер округлюється вгору до тіку.
- LIMIT/GTX policy збережено.
- Додано pre-submit observability перед фактичним submit на адаптер.

Bounded validation пройдено:
- 19 tests passed
- 1 test skipped

Пост-patch live або replay доказу з реальною біржовою книгою у цьому пакеті немає. Отже verdict пакета: code-level fix plus bounded test validation, але не production-runtime proof.

## Current Rounding Contract

### FACTS

- До патча rounding LIMIT price у відкритті позиції був side-agnostic floor-like quantization в execution path.
- Активний path залишився тим самим: decision payload проходить через OpenFlowFSM і далі в OpenExecutor LIMIT submit path.
- BUY rounding behavior already matched passive-maker expectation: floor to tick.
- SELL rounding behavior був asymmetrically wrong для maker-passive intent у reject-кейсі, бо SELL теж йшов вниз до тіку.

### PROVEN PRE-PATCH FAILURE ANCHOR

- У форензічному кейсі `rid=aurora_BTCUSDT_1774131001501` strategy сформувала SELL intent price `70254.01057142857`.
- Execution path округлив submit price до `70254.0`.
- Submit відбувся як LIMIT + GTX.
- Venue відповів reject `-5022`, далі це було нормалізовано як `MAKER_ONLY_REJECT` / `NRR-018`.

### INFERENCE

- Для SELL LIMIT GTX side-agnostic rounding down збільшував ризик попадання в maker-only reject window відносно пасивного SELL placement.

## Patch Implemented

### File 1

`apps/reference/domains/execution_position/fsm_open.py`

Внесені зміни:
- додано side-aware helper `_round_limit_price_to_tick(price, tick_size, side)`
- BUY використовує `ROUND_FLOOR`
- SELL використовує `ROUND_CEILING`
- guard log `GUARD_ADJUST` тепер включає `side` і `mode`
- у DEC:OPEN payload додані поля:
	- `price_before_rounding`
	- `price_after_rounding`
	- `tick_size`
	- `rounding_mode`

Результат:
- rounding contract став явним і доказовим на межі OpenFlowFSM -> DEC:OPEN.

### File 2

`apps/reference/domains/execution_position/open_executor.py`

Внесені зміни:
- додано `_collect_limit_submit_trace(...)`
- перед LIMIT submit формується structured trace `LIMIT_SUBMIT_TRACE`
- trace пишеться в `order_logger` до реального `place_limit_entry(...)`
- лог до submit тепер включає:
	- `symbol`
	- `side`
	- `tif`
	- `price_before_rounding`
	- `price_after_rounding`
	- `tick_size`
	- `rounding_mode`
	- `best_bid`
	- `best_ask`
	- `spread`
	- `distance_to_touch`
	- `rid`

Результат:
- наступний maker-only reject або success тепер має pre-submit evidence layer, якого не вистачало в первинному forensic case.

### Scope Guard

Свідомо НЕ змінювалося:
- strategy entry formula
- intent builder math
- LIMIT/GTX policy
- fallback policy
- maker-only reject normalization

## Observability Added

### FACTS

Нове pre-submit observability фіксує дві речі, яких раніше бракувало одночасно:
- exact before-rounding intended LIMIT price
- exact after-rounding submitted LIMIT price

Додатково, якщо adapter підтримує `get_book_ticker(symbol)`, trace містить:
- `best_bid`
- `best_ask`
- `spread`
- `distance_to_touch`

### FAIL-CLOSED BEHAVIOR

- Якщо adapter відсутній або не має `get_book_ticker`, trace не ламає submit path.
- У такому випадку `book_context=UNAVAILABLE` і submit trace все одно зберігає rounding evidence.

### INFERENCE

- Це не усуває maker-only reject саме по собі, але усуває попередню доказову сліпу зону між intent price і venue reject.

## Validation Evidence

### Static Validation

Editor diagnostics для змінених файлів були clean:
- `apps/reference/domains/execution_position/fsm_open.py`
- `apps/reference/domains/execution_position/open_executor.py`
- `tests/domains/execution_position/test_open_flow_fsm_leverage_and_guards_v1.py`
- `tests/domains/execution_position/test_open_executor_submit_trace.py`

### Bounded Test Run

Command used:

```powershell
Set-Location 'c:/Users/user/Music/Phenix'
C:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/execution_position/test_open_flow_fsm_leverage_and_guards_v1.py tests/domains/execution_position/test_open_executor_submit_trace.py tests/integration/test_ep01_4_maker_guard.py -q
```

Observed result:

```text
19 passed, 1 skipped in 0.78s
```

### What The Tests Proved

1. BUY LIMIT rounding stays floor-to-tick.
2. SELL LIMIT rounding is now ceil-to-tick.
3. DEC:OPEN now carries explicit rounding trace fields.
4. LIMIT submit trace captures book context when `get_book_ticker(...)` is available.
5. LIMIT submit trace fails closed to `book_context=UNAVAILABLE` when book API is unavailable.
6. Existing maker-guard integration coverage stayed green in this bounded run.

## FACTS

- Patch is localized to execution-layer files only.
- Strategy formula was not changed.
- SELL ceil / BUY floor logic is implemented in `fsm_open.py` before DEC:OPEN emission.
- Pre-submit structured trace is implemented in `open_executor.py` before adapter submit.
- Bounded validation passed: 19 passed, 1 skipped.

## INFERENCES

- The patch reduces a proven SELL-side execution rounding asymmetry that was compatible with the earlier maker-only reject case.
- The added observability materially improves future forensic certainty for LIMIT/GTX rejects.
- Because maker-only rejects depend on live book state at submit time, unit/integration tests alone cannot prove full production elimination of `NRR-018`.

## ASSUMPTIONS

- Passive SELL placement should round away from immediate touch, not toward the previous lower tick.
- Existing adapter `get_book_ticker(symbol)` returns best bid/ask values representative enough for pre-submit trace use.
- Existing bounded tests cover the intended contract boundary sufficiently for this narrow patch package.

## UNKNOWNS

- Whether all future SELL GTX rejects are eliminated in live trading.
- Whether there are additional reject modes independent of rounding, such as micro-latency or book movement between trace collection and submit.
- Whether some symbols with unusual tick/lot specifications need extra venue-specific handling beyond this patch.

## Risks

### Residual Runtime Risk

- Even with SELL ceil, a fast-moving book can still turn a passive-looking LIMIT GTX order into a venue reject by submit time.

### Residual Evidence Risk

- `LIMIT_SUBMIT_TRACE` observes book state before submit, not exchange-internal book state at exact matching decision time.

### Contract Risk

- Якщо інші execution paths submit-ять LIMIT orders поза цим path, вони не отримують цей exact rounding/trace improvement автоматично.

## Next Action

Один наступний пакет, якщо потрібен stronger proof:

`POST_PATCH_RUNTIME_CAPTURE_FOR_SELL_GTX`

Ціль:
- зібрати bounded live або replay evidence для реального SELL LIMIT GTX path
- підтвердити, що новий submit trace показує `before`, `after`, `best_bid`, `distance_to_touch`
- перевірити, чи частота `NRR-018` на SELL зменшилась після патча

## Minimal Safe Verdict

Поточний пакет є mergeable для запитаного scope: локальний execution-side SELL ceil / BUY floor patch впроваджено, pre-submit observability додано, bounded validation пройдено, strategy math і LIMIT/GTX policy не змінені. Production-level elimination of maker-only rejects поки що не доведена і потребує окремого runtime evidence package.