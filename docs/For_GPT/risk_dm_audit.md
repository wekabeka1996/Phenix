# Risk / DecisionMaking Audit

## Цель и границы

Фиксируем текущую цепочку: `RiskManagement` → `DecisionMaking` → `AuroraBridge / ExecutionManagement` → `ExecPosFSM`, чтобы понять:

1. Какие конфиги/правила реально влияют на `CMD:OPEN`.
2. Какие gate-ы отсекают сигналы.
3. Где возможны противоречия `DM` ↔ `Risk` ↔ `ExecPos`.
4. Какие части Risk/DM критичны для стабильности системы.

Основано на коде в `apps/reference/domains/risk_management/risk_management.py`, `apps/reference/domains/decision_making/decision_making.py`, `apps/reference/main.py`, `apps/reference/domains/execution_position/fsm.py`, `apps/reference/domains/execution_position/exposure_guard.py`.

## 1. RiskManagement: активные конфиги и правила

- **Конфиги**: `trading.risk` (или fallback `system.risk`).
  * `max_daily_drawdown_pct`, `trading_allowed_thresholds.max_risk_score`, `soft_limits` (использует `soft_clip` как дополнение).
  * `trading.risk.trading_allowed_thresholds.max_risk_score` определяет порог для `risk_score`.
  * `trading.risk.soft_limits` исполняются через `ExposureGuard.soft_clip_engine`.
- **Применяемые правила**:
  * `risk_score` — комбинация нормализованных `delta_price_pct`, `obi`, `tfi`, `absorption_inverse` (см. `_calculate_risk_parameters`).
  * `is_trading_allowed = risk_score <= max_risk_score`.
  * Daily drawdown проверяется по `portfolio_state`.
  * При `risk_score > max` логируется `WhyCode.RISK_SCORE_HIGH` и `is_trading_allowed` ложное.
  * При отключении/ошибке `RiskManagement` не блокирует (fail-open), но `is_trading_allowed` будет False.

## 2. DecisionMaking → gates для CMD:OPEN

### 2.1 Сбор данных
- `DecisionMaking` слушает события: `EVT:FEATURES_CALCULATED`, `EVT:RISK_ASSESSMENT_COMPLETED`, `EVT:PORTFOLIO_STATE_UPDATED`, `EVT:REGIME_DETECTED`, `EVT:EXPOSURE_SUMMARY_UPDATED`.
- Для каждого символа требуется и фичи, и `risk_params`. `risk_params` могут быть переписаны из кеша (если оценка была в последние 30 сек), чтобы избежать гонки.
- Дополнительно включён `bar gating` (`_bar_gating_enabled`, `_bar_ms`) чтобы не делать решения в одном баре дважды.

### 2.2 Конфиги DM, влияющие на вход/решение
- `trading.decision` (включая `signals`, `signal_threshold`, `position_sizing`, `kelly`, `risk_budgets`).
- `trading.decision.qos` (symbol cooldown, exposure_block_cooldown, rate limits) и `trading.mode`.
- `trading.instruments` используется для параметров qty/price/side/defaults.
- `domain_configuration.decision_making` задаёт источник данных, но не влияет на логику gate-ов.

### 2.3 Проверки перед proposal
- `Risk gate`: если `risk_params["is_trading_allowed"]` False → отклонение (NRR "RISK_DISALLOWED" или "NRR-011" для exposure). Срабатывает `_handle_exposure_block`.
- `Exposure cache precheck`: получает `EVT:EXPOSURE_SUMMARY_UPDATED` от ExecPos (см. `ExecPosFSM._on_portfolio_state_updated`, `ExecutionPosition` emits) и кеширует его. Перед `TRADE_INTENT_PROPOSED` считается `projected_exposure = current + notional`. Если больше `max_exposure_usd`, отклоняется (NRR-011).
- `Qty > 0`: `_calculate_position_size` может вернуть 0 (либо не пройти guard), в этом случае решетка прекращается.
- `QoS state`: `_qos_allow` проверяет cooldown, rate limit, exposure cooldown; если блокирует, intent откладывается (а не отвергается).

### 2.4 Формирование `TRADE_INTENT_PROPOSED`
- Если все проверки прошли, `decision_context` содержит features/risk/portfolio/regime; `_calculate_position_size` выдает qty/why.
- `self._propose_trade_intent` вызывает `_propose_trade_intent`, где:
  * формируется payload `{"instrument": symbol, "side": side, "order": {"qty": qty_str, "price": price_ref_str, ...}}`.
  * генерируется `Message(op="EVT", verb="TRADE_INTENT_PROPOSED", ... )`.
  * Логируется `INTENT_PROPOSED`, `dlog`, `OrderLogger`.
  * Если config `decision.reward_alpha` etc (noted) - included.
  * `ExecutionManagement` или `AuroraBridge` принимает этот intent.

## 3. Проверки на противоречия

### 3.1 DM даёт сигнал, Risk блокирует
- Если приходит `EVT:RISK_ASSESSMENT_COMPLETED` c `is_trading_allowed=False`, DecisionMaking отклоняет сигнал. Блокировка фиксируются в `_record_blocked_intent` (AlertManager check каждые ≥10с). Нет `TRADE_INTENT_PROPOSED`.
- Никогда не достигает `ExecutionManagement`, значит противоречия нет (Risk первичен). CM logs (NormalizedRejectReasons).

### 3.2 Risk пропускает, но ExecPos отказывает
- DecisionMaking может пропустить `TRADE_INTENT_PROPOSED`, но ExecPos (`AuroraBridge` + `ExecPosFSM`) может отклонить:
 1. `AuroraBridge` может отложить intent (`QoS`/`portfolio freshness`/`INTENT_DEFERRED`), но не отклоняет.
 2. `ExecPosFSM._check_exposure_fail_closed` вызывает `ExposureGuard.can_open` с `notional_usd = qty * price_ref`. Если guard отказывает (стейл портфель, превышены лимиты, `exposure_guard` state stale), `CMD:OPEN` возвращается `ERR:OPEN` (fail-closed). Это *основной контрпример*: Risk сигнал пропущен (допустимый), но exposure guard блокирует.
 3. `OpenFlowFSM` guard (`min_qty`, `min_notional`, cooldown, idempotency) тоже может отклонить CMD:OPEN. Эти guard’ы проверяют `trading.execution.manage`/`trading.instruments` `min_qty`.
 4. `ExposureGuard` при отказе вызывает `reserve`, и `ExecPos` публикует `ERR:OPEN` с `why=exposure_fail_closed_<reason>`. Также может блокировать `shadow` check or `stale notional`.
- `DecisionMaking` также проверяет `_precheck_exposure_cache`, но если данные устарели (>30 сек), то fail-open, тогда `ExecPos` exposure guard может блокировать позже (разрывая синхронизацию).

### 3.3 Сложные случаи с ExposureGuard
- ExposureGuard хранит `reservations`, `postfill_reservations`, `pending_exposure`. `ExecPosFSM._handle_fill_event` перемещает резервацию из `reservations` → `postfill`.
- Есть `postfill_hold_ttl` (config `trading.exposure.pending_reservation_ttl_sec`) — пока позиция “не подтверждена”, новые `CMD:OPEN` могут быть отложены из-за забронированного капитала.
- `DecisionMaking` также ведёт `_exposure_cache`, обновляемый после каждого `EVT:EXPOSURE_SUMMARY_UPDATED` (ExecPos emits on portfolio, fill, cancel). Если cache stale, DM пропускает проверку (fail-open), но ExecPos guard может продолжать блокировки до восстановления `EXPOSURE_SUMMARY_UPDATED`.
- **Противоречие**: `DecisionMaking` может пропустить exposure cache check (если stale), запустить `TRADE_INTENT_PROPOSED`, но при `CMD:OPEN` ExposureGuard обнаруживает, что уже есть активный `reservation`/`positions` и блокирует. Это ожидаемое поведение (синхронизируется через summary events) и не считается багом.

## 4. Критичные элементы для стабильности SYSTEM CORE

1. **RiskManagement risk_score gate** — фиксирует, что никого нельзя пускать в `DecisionMaking`, если `risk_score` выше порога. Слом на этом уровне приводит к массовым отклонениям. `max_risk_score` (тестнет 0.9?) — самая чувствительная настройка.
2. **DecisionMaking QoS + exposure cache** — предотвращают судьбоносные “rate floods” / “over-exposure”. Эти механизмы создают `INTENT_DEFERRED/ DROPPED`, синхронизация с metrics важна для мониторинга.
3. **ExposureGuard** (и `ExecPosFSM._check_exposure_fail_closed`) — после того, как CMD:OPEN пройден, именно guard отвечает за резервы. Если guard ошибается (например, stale portfolio_state) — то `CMD:OPEN` отклоняется, но это безопаснее, чем залезть за лимиты.
4. **AuroraBridge freshness gate** — без свежего `EVT:PORTFOLIO_STATE_UPDATED` риски увеличиваются; `position_tracking.positions_stale_ttl_sec` и deferred logic поддерживают последовательность.
5. **DecisionMaking alerting** (`_check_and_emit_risk_gate_alert`) — если доля заблокированных интентов >20% (testnet) или >50% (production), `AlertManager.check_risk_gate` вызывается и сигнализирует о возможном кризисе.

## Заключение

Документ фиксирует, как конфиги `trading.risk.*`, `trading.decision.*`, `trading.execution.*` и `trading.exposure.*` реализуют последовательность gating: Risk → Decision → Execution. Возможные “противоречия” (например, exposure guard блокирует после деблокировки Risk) зафиксированы и описаны. Изменений в логике не предпринимается — это снимок текущего состояния системы.
