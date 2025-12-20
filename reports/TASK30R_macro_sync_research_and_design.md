# TASK30-R — Macro Sync Research & Repair Design (E2E Mapping + Proposed Implementation)

## 1) Executive Summary (≤15 рядків)

- **Поточний стан:** `macro_sync` у проді часто тримається близько **0.5 (neutral)**, тобто **corr≈0** або **NOT_READY→neutral**, що робить метрику слабкоінформативною для decision.
- **Ключова причина:** реалізація рахує **Pearson corr по індексах** (останній `N` елементів) **без time-alignment**, при цьому дані приходять **асинхронно** (окремий потік anchor updates, різні time sources, різна частота/джиттер) → класичний **Epps effect / async shrinkage**.
- **Де саме “async”:** symbol returns рахуються по `ts` з market tick (eventTime), а anchor series оновлюється окремими EVT:ANCHOR_UPDATED (arrivalTime / wallclock) і correlation не враховує timestamp взагалі.
- **Рекомендований фікс:** **Option A (recommended)** — **time-grid resampling** (Δ=1s або Δ=configurable) → **aligned returns** → Pearson по спільних bins; явна деградація `neutral + why` при пропусках/σ≈0/out-of-order.
- **Ризики:** зміна дистрибуції `macro_sync` (вийде з “0.5-plateau”), потреба калібрувати downstream weights/thresholds; треба чіткі тести на стабільність та latency.

---

## Required search commands (raw outputs)

### 1) `grep -RIn "macro_sync" apps/reference | head -n 200`

```text
apps/reference/domains/market_data/market_data_connector.py:90:        # Anchors: Load from macro_sync config. Fail if None/missing.
apps/reference/domains/market_data/market_data_connector.py:91:        if not trading.market_data or not trading.market_data.macro_sync:
apps/reference/domains/market_data/market_data_connector.py:93:                "trading.market_data.macro_sync must be configured. "
apps/reference/domains/market_data/market_data_connector.py:94:                "Please add 'market_data.macro_sync.anchors' to your config.")
apps/reference/domains/market_data/market_data_connector.py:95:        self.anchors: list[str] = trading.market_data.macro_sync.anchors
apps/reference/domains/market_data/worker.py:158:        macro_sync = _dget(market_data_cfg, "macro_sync", {})
apps/reference/domains/market_data/worker.py:159:        self._anchors = _dget(macro_sync, "anchors", [])
apps/reference/domains/market_data/docs/DEPLOYMENT.md:184:        macro_sync:
apps/reference/domains/market_data/docs/DEPLOYMENT.md:248:    macro_sync:
apps/reference/domains/market_data/docs/CHANGELOG.md:158:    macro_sync:
apps/reference/domains/market_data/docs/CHANGELOG.md:163:1. Update configuration files to include `macro_sync` section
apps/reference/domains/market_data/docs/README.md:42:    macro_sync:
apps/reference/domains/market_data/docs/README.md:176:    macro_sync:
apps/reference/domains/market_data/docs/EVENTS.md:247:    if symbol in self.config.macro_sync.anchors:
apps/reference/domains/market_data/docs/TESTING.md:292:        macro_sync=MacroSyncConfig(anchors=['BTCUSDT']),
apps/reference/domains/market_data/docs/API_DEPENDENCIES.md:256:    macro_sync: MacroSyncConfig = MacroSyncConfig()
apps/reference/domains/market_data/websocket_aggregator.py:28:            anchors: List of anchor symbols for macro_sync (e.g., ['BTCUSDT', 'ETHUSDT'])
apps/reference/domains/feature_engineering/domain_dict.json:20:      "description": "Computed features including OBI, TFI, delta_price, liquidity_kappa, and Phase 1 metrics (ema_bias, volume_spike, volatility_state, depth_imbalance, macro_sync)",
apps/reference/domains/feature_engineering/domain_dict.json:26:    "phase1": ["ema_bias", "volume_spike", "volatility_state", "depth_imbalance", "macro_sync"]
apps/reference/domains/feature_engineering/__init__.py:9:- Phase 1: ema_bias, volume_spike, volatility_state, depth_imbalance, macro_sync
apps/reference/domains/feature_engineering/types.py:75:    # Returns for macro_sync
apps/reference/domains/feature_engineering/types.py:80:    macro_sync_ready: bool = False
apps/reference/domains/feature_engineering/types.py:81:    macro_sync_not_ready_reason: Optional[str] = None
apps/reference/domains/feature_engineering/types.py:248:    def macro_sync_enabled(self) -> bool:
apps/reference/domains/feature_engineering/types.py:249:        return self._cfg.macro_sync.enabled
apps/reference/domains/feature_engineering/types.py:252:    def macro_sync_time_diff_threshold_ms(self) -> int:
apps/reference/domains/feature_engineering/types.py:253:        return int(self._cfg.macro_sync.time_diff_threshold_ms)
apps/reference/domains/feature_engineering/types.py:256:    def macro_sync_ttl_ms(self) -> int:
apps/reference/domains/feature_engineering/types.py:257:        return int(self._cfg.macro_sync.ttl_ms)
apps/reference/domains/feature_engineering/types.py:260:    def macro_sync_anchors(self) -> list:
apps/reference/domains/feature_engineering/types.py:261:        return self._cfg.macro_sync.anchors
apps/reference/domains/feature_engineering/types.py:264:    def macro_sync_align_mode(self) -> str:
apps/reference/domains/feature_engineering/types.py:265:        return str(self._cfg.macro_sync.align_mode)
apps/reference/domains/feature_engineering/types.py:268:    def macro_sync_anchor_update_from_ticks(self) -> bool:
apps/reference/domains/feature_engineering/types.py:269:        return bool(self._cfg.macro_sync.anchor_update_from_ticks)
apps/reference/domains/feature_engineering/types.py:272:    def macro_sync_window(self) -> int:
apps/reference/domains/feature_engineering/types.py:273:        return self._cfg.macro_sync.window
apps/reference/domains/feature_engineering/types.py:276:    def macro_sync_min_buffer(self) -> int:
apps/reference/domains/feature_engineering/types.py:277:        return self._cfg.macro_sync.min_buffer_size
apps/reference/domains/feature_engineering/docs/README.md:84:    "macro_sync": "0.71"
apps/reference/domains/feature_engineering/docs/README.md:107:    macro_sync:
apps/reference/domains/feature_engineering/docs/EVENTS.md:26:│     - Compute macro_sync (correlation with BTC/ETH)          │
apps/reference/domains/feature_engineering/docs/EVENTS.md:109:    "macro_sync": "0.71"
apps/reference/domains/feature_engineering/docs/EVENTS.md:128:| `macro_sync` | [0, 1] | Corr with BTC/ETH | Higher = aligned with market |
apps/reference/domains/feature_engineering/docs/FTR_FEATURES_FUTURES_V2_DESIGN.md:111:| `macro_sync` | macro | […4402 chars truncated…acro_sync_not_ready_reason:
apps/reference/domains/feature_engineering/feature_engineering.py:536:                    reasons.append(f"macro_sync:{hot.macro_sync_not_ready_reason}")
apps/reference/domains/feature_engineering/feature_engineering.py:537:                    inc_data_quality_drop(domain="feature_engineering", reason="macro_sync_not_ready")
apps/reference/domains/feature_engineering/contracts.py:25:        - Phase 1: ema_bias, volume_spike, volatility_state, depth_imbalance, macro_sync
apps/reference/domains/feature_engineering/contracts.py:80:    macro_sync: Decimal = Field(
apps/reference/domains/feature_engineering/contracts.py:131:        "ema_bias", "volume_spike", "volatility_state", "depth_imbalance", "macro_sync"
apps/reference/domains/feature_engineering/contracts.py:228:    "macro_sync": {
apps/reference/domains/feature_engineering/calculation_engine.py:365:    def update_macro_sync_buffer(
apps/reference/domains/feature_engineering/calculation_engine.py:371:        """Update return for macro_sync correlation."""
apps/reference/domains/feature_engineering/calculation_engine.py:379:            and 0 < time_diff_ms <= self.cfg.macro_sync_time_diff_threshold_ms
apps/reference/domains/feature_engineering/calculation_engine.py:386:    def compute_macro_sync(
apps/reference/domains/feature_engineering/calculation_engine.py:394:        """Compute macro_sync = correlation with anchor returns, normalized to [0,1]."""
apps/reference/domains/feature_engineering/calculation_engine.py:395:        state.macro_sync_ready = False
apps/reference/domains/feature_engineering/calculation_engine.py:396:        state.macro_sync_not_ready_reason = None
apps/reference/domains/feature_engineering/calculation_engine.py:398:        if not self.cfg.macro_sync_enabled or not self.cfg.macro_sync_anchors:
apps/reference/domains/feature_engineering/calculation_engine.py:399:            state.macro_sync_ready = True
apps/reference/domains/feature_engineering/calculation_engine.py:403:        if len(sym_returns) < self.cfg.macro_sync_min_buffer:
apps/reference/domains/feature_engineering/calculation_engine.py:404:            state.macro_sync_not_ready_reason = "insufficient_symbol_samples"
apps/reference/domains/feature_engineering/calculation_engine.py:407:        align_mode = self.cfg.macro_sync_align_mode
apps/reference/domains/feature_engineering/calculation_engine.py:408:        ttl_ms = int(self.cfg.macro_sync_ttl_ms)
apps/reference/domains/feature_engineering/calculation_engine.py:412:        for anchor in self.cfg.macro_sync_anchors:
apps/reference/domains/feature_engineering/calculation_engine.py:433:            if len(anchor_returns) < self.cfg.macro_sync_min_buffer:
apps/reference/domains/feature_engineering/calculation_engine.py:440:                n = min(len(sym_returns), self.cfg.macro_sync_window)
apps/reference/domains/feature_engineering/calculation_engine.py:444:                n = min(len(sym_returns), len(anchor_returns), self.cfg.macro_sync_window)
apps/reference/domains/feature_engineering/calculation_engine.py:445:                if n < self.cfg.macro_sync_min_buffer:
apps/reference/domains/feature_engineering/calculation_engine.py:460:                state.macro_sync_not_ready_reason = "no_fresh_anchor_data"
apps/reference/domains/feature_engineering/calculation_engine.py:462:                state.macro_sync_not_ready_reason = "no_valid_correlation"
apps/reference/domains/feature_engineering/calculation_engine.py:470:        state.macro_sync_ready = True
apps/reference/domains/feature_engineering/calculation_engine.py:471:        state.macro_sync_not_ready_reason = None
apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json:88:        "macro_sync": {
apps/reference/domains/decision_making/decision_making.py:2566:            # macro_sync still from raw dict (not in Views yet)
apps/reference/domains/decision_making/decision_making.py:2567:            macro_sync_raw = features_data["macro_sync"] if "macro_sync" in features_data else 0
apps/reference/domains/decision_making/decision_making.py:2568:            macro_sync_phi = _to_dec(macro_sync_raw)
apps/reference/domains/decision_making/decision_making.py:2601:                "macro_sync": macro_sync_phi,
apps/reference/domains/decision_making/decision_making.py:2618:                "phi_Macro_Sync": float(macro_sync_phi),
apps/reference/config_models.py:54:    macro_sync: float = Field()
apps/reference/config_models.py:718:    macro_sync: Optional[MacroSyncConfig] = Field()
apps/reference/config_models.py:729:    macro_sync: Dict[str, Any] = Field()
apps/reference/config_models.py:871:    ttl_ms: int = Field(ge=100, le=600000, description='Anchor staleness TTL (ms). If anchor older than ttl_ms → macro_sync NOT_READY')
apps/reference/config_models.py:938:    - Phase 1: ema_bias, volume_spike, volatility_state, depth_imbalance, macro_sync
apps/reference/config_models.py:962:    macro_sync: MacroSyncMetricsConfig = Field()
```

### 2) `grep -RIn "corr" apps/reference/domains/features_engine | head -n 200`

```text
grep: apps/reference/domains/features_engine: Нет такого файла или каталога
```

### 3) `grep -RIn "eventTime|E\\]" apps/reference/domains/market_data | head -n 200`

```text
```

### 4) `grep -RIn "returns" apps/reference/domains/features_engine | head -n 200`

```text
grep: apps/reference/domains/features_engine: Нет такого файла или каталога
```

Notes:
- Реальна директорія: `apps/reference/domains/feature_engineering` (не `features_engine`), тому (2) і (4) закономірно фейляться.
- (3) нічого не повертає, бо в коді використовується поле `"E"` (event time) та `"T"` (trade time) як JSON keys, а не рядок `eventTime`, і `|` без `-E` не є alternation.

---

## 2) Data Lineage (SSOT map)

| Stage | Module | Function/Class | Input fields | Time source | Notes |
|---|---|---|---|---|---|
| WS ingest | `market_data` | `MarketDataWorker._handle_message` (`apps/reference/domains/market_data/worker.py:324`) | `e,s,E,T,b,B,a,A,p,q,m,a` | Binance WS `E`/`T` (`apps/reference/domains/market_data/worker.py:340`, `apps/reference/domains/market_data/worker.py:352`) | bookTicker оновлює book state, aggTrade оновлює trades+price |
| aggregation | `market_data` | `WebSocketAggregator.on_book_ticker` (`apps/reference/domains/market_data/websocket_aggregator.py:80`) | bid/ask sizes & prices | `ts` передається як `E` | Пише `bid_ask_time=ts` (`apps/reference/domains/market_data/websocket_aggregator.py:108`) |
| aggregation | `market_data` | `WebSocketAggregator.on_trade` (`apps/reference/domains/market_data/websocket_aggregator.py:112`) | `price, ts(T), trade_id` | Binance trade `T` | Оновлює `latest_price` та `prices` deque (`apps/reference/domains/market_data/websocket_aggregator.py:158`) |
| tick build | `market_data` | `WebSocketAggregator.get_market_tick` (`apps/reference/domains/market_data/websocket_aggregator.py:192`) | state | mixed | Вимагає і `bid_ask_time`, і `prices` (`apps/reference/domains/market_data/websocket_aggregator.py:210`); `ts` береться з bookTicker, `price` — з trade |
| worker emit | `market_data` | `MarketDataWorker._periodic_emit` (`apps/reference/domains/market_data/worker.py:478`) | tick dict | tick.ts = bookTicker `E` | Tick msg: `ts=tick["ts"]` (`apps/reference/domains/market_data/worker.py:494`) |
| worker emit | `market_data` | `MarketDataWorker._periodic_emit` (`apps/reference/domains/market_data/worker.py:478`) | anchor price | **arrivalTime (wallclock)** | Anchor msg: `ts=int(time.time()*1000)` (`apps/reference/domains/market_data/worker.py:508`) |
| IPC→FSM | `market_data` | `MarketDataProxy._emit_tick` (`apps/reference/domains/market_data/proxy.py:161`) | tick msg | passed-through | EVT:MARKET_TICK_RECEIVED payload uses tick `ts` (`apps/reference/domains/market_data/proxy.py:171`) |
| IPC→FSM | `market_data` | `MarketDataProxy._emit_anchor_update` (`apps/reference/domains/market_data/proxy.py:196`) | anchor msg | **ts dropped** | Proxy emits payload without `ts` (`apps/reference/domains/market_data/proxy.py:202`) |
| feature calc | `feature_engineering` | `FeatureEngineering.on_market_tick` (`apps/reference/domains/feature_engineering/feature_engineering.py:365`) | tick payload | tick.ts | `time_diff=current_ts-last_ts` (`apps/reference/domains/feature_engineering/feature_engineering.py:405`) |
| state store | `feature_engineering` | `FeatureEngineering.anchor_prices` (`apps/reference/domains/feature_engineering/feature_engineering.py:95`) | `price` | none | anchors зберігаються як **deque(price)** без timestamp |
| state store | `feature_engineering` | `FeatureEngineering.update_anchor_price` (`apps/reference/domains/feature_engineering/feature_engineering.py:143`) | `anchor, price, ts_ms?` | **arrivalTime fallback** | якщо `ts_ms` відсутній → `time.time()` (`apps/reference/domains/feature_engineering/feature_engineering.py:148`) |
| returns | `feature_engineering` | `FeatureCalculationEngine.update_macro_sync_buffer` (`apps/reference/domains/feature_engineering/calculation_engine.py:365`) | `price, time_diff_ms` | tick.ts diff | повертає **tick-to-tick returns** (`apps/reference/domains/feature_engineering/calculation_engine.py:381`) |
| macro_sync | `feature_engineering` | `FeatureCalculationEngine.compute_macro_sync` (`apps/reference/domains/feature_engineering/calculation_engine.py:386`) | `sym_returns`, `anchor_prices` | mixed | anchor freshness: `current_ts_ms - last_ts` (`apps/reference/domains/feature_engineering/calculation_engine.py:416`) |
| macro_sync | `feature_engineering` | `compute_macro_sync` | `anchor_prices_list` | none | anchor returns рахує **без time** (`apps/reference/domains/feature_engineering/calculation_engine.py:426`) |
| consumer config | `config` | `MacroSyncMetricsConfig` (`apps/reference/config_models.py:865`) | YAML values | n/a | typed validation: window/min_buffer/ttl/align_mode, etc. |
| config source (FE) | `config` | `feature_engineering.macro_sync` (`config/aurora/domains.yaml:87`) | ttl/window/min_buffer/anchors/align | n/a | Це SSOT для **обчислення corr** у FeatureEngineering |
| config source (MD) | `config` | `trading.market_data.macro_sync` (`config/aurora/trading.yaml:152`) | anchors/window/etc | n/a | Це використовується MarketData для anchor stream / anchor list (worker) |

---

## 3) Impact Map (де macro_sync використовується)

| Consumer | Module | Function/Class | How used | Criticality |
|---|---|---|---|---|
| Feature warmup gating | `feature_engineering` | warmup builder (`apps/reference/domains/feature_engineering/feature_engineering.py:513`) | `warmup.full_ready` включає `hot.macro_sync_ready` (`apps/reference/domains/feature_engineering/feature_engineering.py:526`) | P1 |
| Telemetry | `telemetry` | `inc_data_quality_drop` (`apps/reference/telemetry/metrics.py:226`) | лічильник `macro_sync_not_ready` (`apps/reference/domains/feature_engineering/feature_engineering.py:535`) | P2 |
| Trade gating | `decision_making` | warmup guard (`apps/reference/domains/decision_making/decision_making.py:2023`) | блокує decision якщо `features_warmup.full_ready=false` (`apps/reference/domains/decision_making/decision_making.py:2030`) | P1 |
| Signal score | `decision_making` | phi map (`apps/reference/domains/decision_making/decision_making.py:2592`) | `macro_sync` входить у `phi_map` і суму `signal_score` (`apps/reference/domains/decision_making/decision_making.py:2601`) | P1 |
| XAI / psi_vector | `decision_making` | psi vector (`apps/reference/domains/decision_making/decision_making.py:2610`) | `phi_Macro_Sync` лог/telemetry (`apps/reference/domains/decision_making/decision_making.py:2618`) | P2 |

Notes:
- У проекті є **дві конфігурації macro_sync**: (a) `config/aurora/domains.yaml` (FeatureEngineering estimator) і (b) `config/aurora/trading.yaml` (MarketData anchors/config).
- `regime_detector` напряму не використовує `macro_sync` (пошук по `apps/reference/domains/regime_detector` не знайшов `macro_sync`), але **DecisionMaking fail-closed** на FE warmup, який включає macro_sync readiness.

---

## 4) Root Cause Proof (async evidence)

### 4.1 Де саме беруться returns

- **Symbol returns**: `ret = (price - prev_price)/prev_price` додається в `returns_buffer` лише коли `0 < time_diff_ms <= threshold` (`apps/reference/domains/feature_engineering/calculation_engine.py:376`, `apps/reference/domains/feature_engineering/calculation_engine.py:381`).  
  `time_diff_ms` береться як `current_tick["ts"] - last_tick["ts"]` (`apps/reference/domains/feature_engineering/feature_engineering.py:405`).

- **Anchor returns**: `anchor_returns` рахується як послідовні returns по списку `anchor_prices_list` (`apps/reference/domains/feature_engineering/calculation_engine.py:426`) **без timestamps** (тобто, implicit assumption: equally-spaced samples).

### 4.2 Доказ “asynchrony” / mixed clocks / mixed cadence

1) **Різні time sources для series**
   - Symbol tick `ts`: bookTicker `E` (`apps/reference/domains/market_data/worker.py:340`, `apps/reference/domains/market_data/websocket_aggregator.py:108`), передається через worker tick msg (`apps/reference/domains/market_data/worker.py:494`) → FE використовує як `current_tick["ts"]` (`apps/reference/domains/feature_engineering/feature_engineering.py:405`).
   - Anchor update `ts`: worker ставить `ts=int(time.time()*1000)` (`apps/reference/domains/market_data/worker.py:512`), але proxy **викидає `ts`** (`apps/reference/domains/market_data/proxy.py:202`), і FE тоді проставляє `time.time()` як fallback (`apps/reference/domains/feature_engineering/feature_engineering.py:148`).

2) **Окремий потік anchor updates**
   - anchors оновлюються через `EVT:ANCHOR_UPDATED` (`apps/reference/domains/feature_engineering/feature_engineering.py:153`), незалежно від `EVT:MARKET_TICK_RECEIVED` (`apps/reference/domains/feature_engineering/feature_engineering.py:107`).
   - порядок доставки ticks vs anchors не гарантований (окремі queue items), а correlation вирівнює масиви лише по tail length (`apps/reference/domains/feature_engineering/calculation_engine.py:444`).

3) **Index-alignment ≠ time-alignment**
   - `compute_macro_sync` робить `x=sym_returns[-n:]`, `y=anchor_returns[-n:]` (`apps/reference/domains/feature_engineering/calculation_engine.py:447`) — це alignment **по індексу**, не по реальному часу.

### 4.3 Висновок: чому corr → 0 (Epps)

- Коли `x_k` і `y_k` відповідають returns на **різних реальних інтервалах** (через джиттер/каденс/окремі потоки), ковариація “розмазується”, Pearson занижується → `avg_corr≈0` → `phi≈0.5`.
- Спостереження з live-логу features (приклад): `macro_sync` часто дорівнює `"0.5"` (`logs/features/BTCUSDT.log`, tail), що узгоджується з corr≈0 або NOT_READY→neutral.

---

## 5) Repair Options (мінімум 2)

### Option A (recommended): Time-grid resampling + aligned Pearson corr

**Mathematical definition**

Нехай Δ — size біну (ms). Для кожного символу `S` і anchor `A` будуємо series close-price на grid:

- `bin(t) = floor(t/Δ)*Δ`
- `P_S[bin] = last_price_observed_in_bin`
- `r_S[bin] = log(P_S[bin] / P_S[bin-Δ])` (або simple return)

Для кореляції:

- `B = intersection(keys(r_S), keys(r_A))` на останньому `N` вікні
- `corr(S,A) = Pearson({r_S[b]}_{b∈B}, {r_A[b]}_{b∈B})`
- `macro_sync = mean_A corr(S,A)`; `phi=(macro_sync+1)/2`

**Runtime cost**

- O(1)/tick для update bin state.
- O(anchors × N) на розрахунок corr (аналогічно поточному, але з bin keys).

**Failure modes**

- gaps → недостатньо bins → `neutral + why=insufficient_bins`
- out-of-order → drop event + counter
- σ≈0 (flat series) → `neutral + why=sigma_zero`

**Compatibility risk**

- Діапазон лишається [0,1], але distribution зміниться (вийде з “0.5-plateau”).
- downstream weights/thresholds можуть потребувати перевірки.

### Option B: Asynchronous estimator (Hayashi–Yoshida)

**Mathematical definition**

Оцінка cov для асинхронних спостережень через суму продуктів increments на перекривних інтервалах:

- `Cov_HY = Σ ΔX_i ΔY_j * 1_{(t_i,t_{i+1}] ∩ (s_j,s_{j+1}] ≠ ∅}`
- `Corr_HY = Cov_HY / (sqrt(Var_X_HY) sqrt(Var_Y_HY))`

**Runtime cost**

- складніше: підтримка interval overlap; потенційно O(n+m) або гірше при naive.

**Failure modes**

- підвищена складність/CPU; складніше дебажити і тестувати.

**Compatibility risk**

- Вища: інший estimator, інші sensitivity.

**Choice**

Рекомендую **Option A**: прозорий, дешево, добре лягає в існуючий “typed config + explicit readiness” стиль, і прямо прибирає Epps через time alignment.

---

## 6) Proposed Implementation Plan (конкретний)

### New files / classes (additive)

1) `apps/reference/domains/feature_engineering/macro_sync_resampler.py`
   - `@dataclass class TimeGridSeries`: `last_bin`, `bin_prices: deque[(bin_ts, price)]`, `drops_out_of_order: int`, `gaps: int`
   - `class MacroSyncResampler`:
     - `update(symbol: str, ts_ms: int, price: Decimal) -> None`
     - `compute(symbol: str, anchors: list[str], now_ts_ms: int) -> MacroSyncResult`

2) `apps/reference/domains/feature_engineering/types.py`
   - Add typed container `MacroSyncResult(value_phi: Decimal, ready: bool, why: Optional[str], drops: int, bins_used: int)`

### API contracts

Input (per tick):
- `symbol: str`
- `ts_ms: int` (SSOT time: **eventTime** from market tick)
- `price: Decimal`

Output:
- `macro_sync_phi: Decimal` in [0,1]
- `ready: bool`
- `why: Optional[str]` (explicit деградація)

### Cadence (when to compute)

- Compute on each `_calculate_and_emit_features` (per symbol tick), or on “bin close” (if `ts` crossed into new bin).
- Δ (bin size) — new config field under `trading.market_data.macro_sync` (або reuse існуючого `poll_interval` якщо хочеш мінімальну зміну).

### Degradation policy (explicit; no silent fallbacks)

- `insufficient_bins`: bins_used < min_buffer_size
- `no_fresh_anchor_data`: anchor stale beyond ttl_ms
- `sigma_zero`: variance≈0 for x або y
- `out_of_order`: event dropped; counter increments; if too frequent → `neutral + why=too_many_out_of_order`
- `gap_too_large`: missing bins beyond max_gap_bins

### Minimal integration points (no behavior change outside macro_sync)

- Replace current `compute_macro_sync` logic with resampler-backed computation, but keep:
  - same output scaling `phi=(corr+1)/2`
  - same readiness contract fields (`macro_sync_ready`, `macro_sync_not_ready_reason`)

---

## 7) Test Plan (мінімум 5 тестів)

1) **Async tick rates but correlated prices → corr high after fix**
   - Generate two price series with same underlying process but different sampling times; after binning, `phi > 0.8`.
2) **Uncorrelated series → corr near 0**
   - Independent random walks; expect `phi ~ 0.5 ± ε`.
3) **Out-of-order events**
   - Feed ts sequence: 1000, 900, 1100; ensure out-of-order dropped, counter increments, and compute remains stable.
4) **Low-liquidity / sparse bins**
   - Missing bins for symbol or anchor; expect `ready=false`, `phi=neutral`, `why=insufficient_bins` (або `gap_too_large`).
5) **Performance sanity**
   - For `anchors=2`, `window=60`, ensure compute time ≤ **5ms** (pytest benchmark-ish assertion via time.perf_counter, tolerant).

Suggested placement:
- `tests/domains/feature_engineering/test_macro_sync_timegrid_alignment.py` (new)
- `tests/domains/feature_engineering/test_macro_sync_out_of_order_and_gaps.py` (new)
