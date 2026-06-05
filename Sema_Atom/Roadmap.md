# SEMA_ATOM ROADMAP v1

## Offline episodic memory / evidence engine для Aurora/Phenix

```text
CURRENT STATUS:
OFFLINE MEMORY PIPELINE PROVEN,
FORWARD COLLECTION INFRASTRUCTURE PATCHED,
READY FOR 72H DATA COLLECTION + CONTRACT HARDENING,
NO RUNTIME AUTHORITY,
NO POLICY RELAXATION.
```

---

# 0. Коротка суть ідеї

**SemaAtom** — це не нова стратегія, не live-gate, не нейромережа і не execution-модуль.

Це **доказова памʼять торгової системи**.

Її задача:

```text
зберігати не всі логи,
а структуровані атоми досвіду:
що система бачила,
яке рішення прийняла або відхилила,
у якому контексті,
чим це завершилось,
чи було це корисно,
чи було це токсично,
чи policy була занадто жорстка,
чи gate реально захистив.
```

Головна відмінність від звичайного trade journal:

```text
ми зберігаємо не тільки executed trades,
а й rejected decisions.
```

Бо rejected-рішення — це місце, де ховається головна правда про gates:

```text
REJECT_CORRECT_BLOCK      → gate захистив
REJECT_MISSED_POSITIVE    → gate, можливо, задушив корисну угоду
```

Claude правильно сформулював це як “післядійову памʼять” торгового агента, де accepted і rejected рішення перетворюються на структуровані атоми, потім проходять context verdict, validation, stability filter і counterfactual economics перед будь-яким впливом на policy .

---

# 1. Навіщо це Aurora/Phenix

Поточна проблема системи не в тому, що “нічого нема”.
Проблема в тому, що система велика, переобережна, має багато policy/gate шарів і потребує доказового шляху до першого малого стабільного net-positive operating band.

Profit Roadmap уже прямо фіксує SemaAtom як `P0_high`, бо він напряму допомагає NNR/gate calibration, коштує дешевше за широкі runtime-архітектурні перебудови і вже дав корисні POC-результати .

SemaAtom має відповідати на питання:

```text
1. Які gates реально захищають?
2. Які gates душать корисні входи?
3. Які accepted context-и токсичні?
4. Які rejected context-и були correct block?
5. Де статистичний сигнал не переживає економіку?
6. Де потрібен не policy patch, а більше даних?
```

---

# 2. Головний принцип

```text
Memory verdict ≠ policy change.
```

Порядок такий:

```text
logs
→ atoms
→ context verdict
→ chronological validation
→ stability filter
→ counterfactual economics
→ forward collection
→ multi-slice revalidation
→ тільки потім shadow/advisory candidate
```

Це головний запобіжник.

POC_04 уже довів, чому це важливо: один статистично стабільний `POLICY_TOO_STRICT_CANDIDATE` після economics став `COUNTERFACTUAL_NEGATIVE`. Тобто “ми пропустили рух” не означає “ми пропустили прибуткову угоду”.

---

# 3. Що вже реалізовано

## 3.1 POC_01 — synthetic proof

Створено базову модель SemaAtom і synthetic pipeline:

```text
synthetic decisions
→ SemaEncoder
→ SemaMemory
→ memory verdict report
```

Доведено, що концепція може класифікувати:

```text
GOOD_DECISION
CLEAN_LOSS
BAD_EXIT
POLICY_TOO_STRICT
POLICY_PROTECTED
LOW_SUPPORT / INSUFFICIENT_MEMORY
```

Статус:

```text
POC_01:
CONCEPTUAL / SYNTHETIC PROOF PASSED
```

---

## 3.2 POC_02 — real-log adapter

Побудовано read-only adapter:

```text
Aurora real logs
→ accepted/rejected raw contracts
→ SemaAtom SAF
→ memory verdict report
```

Ключове доведення:

```text
реальні Aurora logs можна перетворити в атоми досвіду
без live logic змін
```

Статус:

```text
POC_02:
REAL_LOG_BIRTH_PROOF PASSED
```

---

## 3.3 POC_03 — memory verdict validation

Зроблено chronological validation:

```text
train atoms → verdict
validation atoms → перевірка
```

Результат першого frozen slice:

```text
153 atoms
10 tested contexts
27 low-support contexts
~70% confirmation rate
false positives present
```

Це означає:

```text
памʼять має первинний predictive signal,
але не є достатньо сильною для policy authority.
```

Статус:

```text
POC_03:
VALIDATION_PASSED_WITH_LOW_POWER_RESIDUALS
```

---

## 3.4 POC_03B — stability filter

Побудовано artifact-driven filter, який не пускає всі “цікаві” verdict-и в економічну симуляцію.

Він розклав context-и на:

```text
READY_FOR_COUNTERFACTUAL_SIM
PROMISING_LOW_SUPPORT
REJECTED_FALSE_POSITIVE / CONTRADICTED
INCONCLUSIVE_LOW_POWER
CONFIRMED_BUT_UNSTABLE
```

З 37 context evaluations до POC_04 пройшов тільки один.

Статус:

```text
POC_03B:
ACCEPTED
```

---

## 3.5 POC_04 — counterfactual economics

Єдиний допущений context:

```text
BTCUSDT | BUY | aurora | LOW_VOLATILITY | 0.25..0.50
```

був економічно відхилений.

Висновок:

```text
NO_POLICY_RELAXATION_FROM_CURRENT_EVIDENCE
```

Це не провал. Це proof, що pipeline не дає системі обманути себе красивою статистикою.

Статус:

```text
POC_04:
COUNTERFACTUAL_NEGATIVE_ACCEPTED
```

---

## 3.6 FC_01 — forward collector

Створено batch-first forward collector:

```text
frozen logs + recorder
→ new immutable SAF slice
→ forward collection report
→ collection index
```

Перший forward slice показав сильний rejected reference coverage:

```text
43 / 47 rejected with reference_price ≈ 91.49%
```

Але FC_01A виявив blocker: unresolved accepted close із missing `realized_pnl_net` потрапив у trainable SAF.

---

## 3.7 FC_01B — accepted incomplete guard patch

Blocker закрито.

Нові правила:

```text
pnl_status == unresolved → not trainable
realized_pnl_net is None → not trainable
```

Після patch:

```text
accepted_atoms_created = 0
rejected_atoms_created = 43
atoms_created = 43
ACCEPTED_INCOMPLETE_TRAINABLE_ATOM_DEFECT = FALSE
```

Статус:

```text
FC_01B:
PATCHED_AND_RECONCILED_WITH_NON_BLOCKING_RESIDUALS
```

---

# 4. Поточний стан

```text
SEMA_ATOM_CURRENT_STAGE:
OFFLINE MEMORY INFRASTRUCTURE READY_FOR_FORWARD_COLLECTION
```

Що це означає:

```text
1. Ідея реальна.
2. Логи реально перетворюються в atoms.
3. Validation pipeline працює.
4. Stability filter працює.
5. Economics veto працює.
6. Forward collector працює.
7. Trainable corpus тепер захищений від unresolved accepted outcomes.
```

Що ще не доведено:

```text
1. Що є економічно позитивний context.
2. Що verdict-и стабільні на нових runtime slices.
3. Що можна relax policy.
4. Що memory може мати runtime authority.
5. Що cross-strategy transfer безпечний.
6. Що counterfactual economics достатньо точна для live decisions.
```

---

# 5. Чому ми обрали batch-first шлях

DeepSeek і Claude обидва пропонували майбутні напрями: realtime shadow collector, drift detection, recency decay, economics V2, shared prior, API/dashboard. Але поточна правильна позиція лишається:

```text
batch-first,
read-only,
immutable slices,
no EventBus listener,
no runtime dependency.
```

Причина проста: SemaAtom зараз має довести не швидкість, а **достовірність памʼяті**.

Безперервний shadow-module зараз додав би:

```text
EventBus pressure
partial lifecycle states
backpressure risk
runtime coupling
new failure modes
possible hidden dependency
```

А нам зараз потрібні:

```text
clean frozen slices
contract stability
multi-slice validation
coverage metrics
economics proof
```

---

# 6. Що нового додали DeepSeek і Claude

## 6.1 Reference price recovery policy

Приймаємо каскад:

```text
trainable:
1. metadata.low_vol_cost_floor.entry_price
2. metadata.reference_price / intended_entry_price
3. metadata.economics_context.entry_price
4. linked order_intent.entry_price

diagnostics-only:
5. recorder mid price
6. recorder open/close

skipped:
7. no usable price
```

Ключове рішення: recorder-derived price **не trainable**, бо це не доведена intended entry price стратегії .

Потрібен окремий контракт:

```text
SEMA_ATOM_REFERENCE_PRICE_RECOVERY_POLICY_V01
```

---

## 6.2 JSON sidecar для POC_03

Поточний Markdown transport треба прибрати.

Нова схема вже запропонована як:

```text
SemaAtomPoc03EvaluationSidecarV01
```

Вона містить:

```text
schema_id
schema_version
generated_at_utc
saf_path
total_atoms
split_config
summary
contexts
```

і context-level поля:

```text
context_key
symbol
side
strategy_id
regime
confidence_bucket
verdict
validation_result
train/validation counts
train/validation outcomes
rates
support_quality
timestamp_range
```

Схема прямо фіксує, що `context_key = SYMBOL|SIDE|STRATEGY_ID|REGIME|BUCKET`, а `strategy_id` є обовʼязковим і не може silent-merge між стратегіями .

---

## 6.3 Support quality tiers

Приймаємо ідею:

```text
INSUFFICIENT
BORDERLINE
SUFFICIENT
STRONG
```

Але з нашою safety поправкою:

```text
BORDERLINE = watchlist / secondary simulation only
SUFFICIENT або STRONG = primary counterfactual candidate
```

Claude/DeepSeek пропонують 5/5 як мінімум і tiered fill factor; технічний аналіз показує, що 5/5 дає компроміс між очікуванням даних і false positive risk .

Наша фіксація:

```text
canonical primary admission:
train_count >= 5
validation_count >= 5
support_quality in [SUFFICIENT, STRONG]
validation_result == CONFIRMED
verdict-specific stability rules passed
```

---

## 6.4 Drift detection

Приймаємо як майбутній шар:

```text
primary: PSI по outcome distribution
secondary: rolling net_score sign flip
```

Technical design пропонує outcome groups:

```text
favorable
missed_positive
negative
neutral
```

і PSI thresholds:

```text
PSI < 0.10       → STABLE
0.10..0.25       → MONITORING
>= 0.25          → DRIFTED
```

Також пропонується sign-flip detector по rolling net_score .

Але це **після FC_02**, не зараз.

---

## 6.5 Recency decay

Приймаємо принцип:

```text
decay is query-time only,
never storage-time.
```

Raw atoms immutable.
Decay weight — тільки обчислюваний атрибут у report/query layer.

Technical design пропонує exponential half-life і паралельне збереження raw/effective counts для auditability .

Але це теж після FC_02.

---

## 6.6 Counterfactual Economics V2

Приймаємо напрям:

```text
fixed fill_factor / fixed fee_slippage_buffer
→ dynamic model based on spread_bps, notional_usdt, ADV, volatility
```

Мінімальні нові поля:

```text
spread_bps
notional_usdt
adv_1h_usdt
reference_spread_bps
```

Orderbook snapshots не потрібні для V2. Це майбутній V3. Technical design прямо каже, що spread + notional + ADV дають більшу частину користі при значно меншій складності, ніж order book modeling .

Але V2 — після multi-slice proof.

---

## 6.7 Cross-strategy transfer

Приймаємо тільки як future diagnostics layer.

Canonical key лишається:

```text
symbol + side + strategy_id + regime + confidence_bucket
```

Shared prior може існувати пізніше як:

```text
diagnostics-only
weak prior
bounded weight
never silent merge
```

Technical design правильно фіксує: `strategy_id` у canonical key назавжди, shared prior — окремий diagnostics layer, а alpha-family conflict має бути сигналом, не приводом для агрегації .

---

# 7. Що потрібно реалізувати далі

## PHASE A — Contract hardening before next validation

### A1. `POC_03_JSON_SIDECAR_CONTRACT_CLEANUP`

Мета:

```text
прибрати Markdown parsing із POC_03B
```

Роботи:

```text
1. Виправити JSON schema.
2. Додати sidecar output у POC_03.
3. Додати schema validation.
4. Переписати POC_03B на JSON consumer.
5. Зберегти MD report як human-readable only.
```

Обовʼязкові правки до схеми:

```text
- min_train_atoms/min_validation_atoms привести до canonical 5/5 або чітко розділити scoring_min vs display_min;
- split_method розширити: chronological_50_50 / 60_40 / 70_30 або chronological_ratio;
- final_verdict відокремити від residual_status;
- додати support_counts block;
- зафіксувати BORDERLINE admission policy;
- виправити PSI pseudo-code перед копіюванням у код.
```

Output:

```text
SEMA_ATOM_POC_03_EVALUATION_SIDECAR_SCHEMA_V01.json
SEMA_ATOM_POC_03_EVALUATION_SIDECAR_CONTRACT_REPORT.md
```

Verdict:

```text
JSON_SIDECAR_CONTRACT_ACCEPTED
```

---

### A2. `REFERENCE_PRICE_RECOVERY_POLICY_V01`

Мета:

```text
уніфікувати, звідки береться reference_price для rejected
і що є trainable, а що diagnostics-only
```

Роботи:

```text
1. Реалізувати recovery levels 0–6.
2. Додати source field:
   reference_price_source
   reference_price_trainability
3. Recorder-derived reference price не створює trainable atom.
4. Report coverage per source.
5. Tests на кожний recovery level.
```

Output:

```text
SEMA_ATOM_REFERENCE_PRICE_RECOVERY_POLICY_V01.md
SEMA_ATOM_REFERENCE_PRICE_RECOVERY_TEST_REPORT.md
```

---

### A3. `REJECTED_DEDUPE_KEY_PATCH`

Мета:

```text
прибрати reject_reason із dedupe key
```

Новий ключ:

```text
rejected:<decision_id>:<symbol>:<side>:<event_ts_ms>:<strategy_id>
```

`reject_reason` лишається в payload/provenance, але не в ключі.

---

# 8. PHASE B — 72h runtime collection

Після A1/A2 можна запускати систему на новий збір.

Але запускати можна і паралельно з A1/A2, якщо:

```text
1. policy не змінюється;
2. SemaAtom runtime не вмикається;
3. немає shadow listener;
4. просто накопичуються logs + recorder;
5. після завершення logs freeze.
```

Рекомендований режим:

```text
72 години runtime
hybrid_live_data_testnet_exec
без policy relaxation
без нових gates
без YAML mutation
```

Мета:

```text
отримати новий clean forward slice,
а не довести profit одразу.
```

---

# 9. PHASE C — FC_01 на новому slice

Після 72h:

```text
freeze logs
run SEMA_ATOM_FORWARD_COLLECTOR.py
```

Output:

```text
aurora_forward_slice_<from>_<to>.saf.jsonl
SEMA_ATOM_FORWARD_COLLECTION_<from>_<to>_REPORT.md
SEMA_ATOM_FORWARD_COLLECTION_INDEX.json
```

Acceptance:

```text
1. no runtime files modified
2. new immutable slice created
3. accepted incomplete guard works
4. rejected_reference_price_coverage reported
5. MFE/MAE coverage reported
6. duplicates handled
7. atoms by source reported
8. no trainable unresolved accepted atoms
```

Key metrics:

```text
rejected_reference_price_coverage
accepted_mfe_mae_coverage
encoding_errors
duplicates_skipped
new_contexts
contexts_promoted_from_low_support
```

---

# 10. PHASE D — FC_02 multi-slice revalidation

Це наступний великий milestone.

Мета:

```text
обʼєднати baseline + forward slices
і повторити:
POC_03 → POC_03B → POC_04
на ширшому корпусі.
```

Input:

```text
aurora_real_logs_v02.saf.jsonl
aurora_forward_slice_*.saf.jsonl
SEMA_ATOM_FORWARD_COLLECTION_INDEX.json
POC_03 sidecar schema
```

Output:

```text
SEMA_ATOM_FC_02_MULTI_SLICE_REVALIDATION_REPORT.md
SEMA_ATOM_FC_02_CONTEXT_EVALUATION_SIDECAR.json
SEMA_ATOM_FC_02_CANDIDATE_MANIFEST.json
```

Питання FC_02:

```text
1. Чи підтвердились старі context verdict-и?
2. Чи нові slices перевели low-support context-и в sufficient?
3. Чи зʼявився економічно позитивний candidate?
4. Чи reference coverage стабільна?
5. Чи accepted-path coverage стабільна?
6. Чи є drift або sign flip?
```

Allowed verdicts:

```text
FC_02_VALIDATION_PASSED
FC_02_INCONCLUSIVE_LOW_POWER
FC_02_COUNTERFACTUAL_NEGATIVE_ONLY
FC_02_FOUND_POSITIVE_CANDIDATE
FC_02_BLOCKED_BY_DATA_QUALITY
```

---

# 11. PHASE E — Counterfactual Economics V2

Після FC_02, якщо зʼявляться candidates або якщо V1 economics стане dominant uncertainty.

Мета:

```text
замінити fixed 10 bps buffer і fixed fill_factor
на dynamic model.
```

Поля:

```text
spread_bps
notional_usdt
adv_1h_usdt
reference_spread_bps
volatility_atm_bps
```

Не потрібно зараз:

```text
order book snapshots
queue modeling
live fill simulator
```

V2 має лишатися offline.

---

# 12. PHASE F — Drift + recency layer

Після кількох slices.

Мета:

```text
не дозволити старому досвіду домінувати,
якщо ринок змінився.
```

Компоненти:

```text
PSI outcome distribution
rolling net_score sign flip
query-time decay
raw/effective count reporting
```

Output:

```text
SEMA_ATOM_DRIFT_DECAY_REPORT.md
```

Rule:

```text
drift_status == DRIFTED
→ context не видаляється,
але деградує до revalidation-required.
```

---

# 13. PHASE G — Shadow advisory candidate, не authority

Тільки після:

```text
1. кілька clean slices;
2. стабільний JSON sidecar;
3. FC_02 passed;
4. positive counterfactual candidate;
5. no unresolved trainable contamination;
6. reference coverage стабільна;
7. economics positive after conservative assumptions.
```

Тоді можна думати про:

```text
SEMA_ATOM_SHADOW_ADVISORY_V1
```

Але навіть тоді:

```text
no direct gate mutation
no YAML patch
no CMD emission
no execution authority
```

Тільки:

```text
WOULD_BLOCK
WOULD_RELAX
WOULD_WARN
WOULD_COLLECT_MORE
```

---

# 14. Що категорично не робимо зараз

```text
1. Не міняємо thresholds через SemaAtom.
2. Не relax LOW_VOL gates.
3. Не робимо continuous shadow collector.
4. Не додаємо ML gate.
5. Не робимо live A/B.
6. Не переносимо досвід між стратегіями.
7. Не вмикаємо runtime memory authority.
8. Не робимо orderbook V3.
9. Не робимо self-learning.
```

---

# 15. Коли можна сказати “реалізовано на 100%”

Треба розділяти рівні.

## 15.1 Concept Proof — майже готово

Потрібно:

```text
A1 JSON sidecar cleanup
A2 reference price policy
A3 dedupe cleanup
```

Після цього:

```text
SemaAtom offline concept proof = 100%
```

Поточна оцінка:

```text
92%
```

---

## 15.2 Offline Memory MVP — ще не 100%

Потрібно:

```text
1. 72h slice.
2. FC_01 new slice.
3. FC_02 multi-slice revalidation.
4. POC_03 JSON sidecar.
5. POC_03B JSON consumer.
6. Clean index/dedupe/reference policy.
7. At least one full revalidation cycle.
```

Поточна оцінка:

```text
70–75%
```

---

## 15.3 Profit-supporting evidence engine — поки не 100%

Потрібно:

```text
1. знайти хоча б один positive counterfactual candidate;
2. підтвердити його на новому slice;
3. довести conservative net positive після fees/slippage/haircut;
4. показати, що це не low-support artifact;
5. оформити shadow advisory package.
```

Поточна оцінка:

```text
35–40%
```

---

## 15.4 Production memory/advisory layer — далеко

Потрібно:

```text
YAML/Pydantic config
schema registry
runtime observability
shadow-only deployment
rollback rules
multi-slice stability
drift/decay
economics V2
operator dashboard
no-effect guarantees
```

Поточна оцінка:

```text
20–25%
```

---

# 16. Найближчий практичний порядок

Я б ішов так:

```text
STEP 1:
SEMA_ATOM_POC_03_JSON_SIDECAR_CONTRACT_CLEANUP

STEP 2:
SEMA_ATOM_REFERENCE_PRICE_RECOVERY_POLICY_V01

STEP 3:
SEMA_ATOM_REJECTED_DEDUPE_KEY_PATCH

STEP 4:
Запуск Aurora на 72h без policy changes

STEP 5:
FC_01 collector на новий frozen slice

STEP 6:
FC_02 multi-slice revalidation

STEP 7:
тільки якщо є candidates:
POC_04 повтор на FC_02 candidates

STEP 8:
якщо counterfactual positive:
shadow advisory design

STEP 9:
якщо counterfactual negative/inconclusive:
continue forward collection
```

Можна запускати 72h вже зараз, якщо паралельно не чіпати policy. Але з інженерної чистоти краще спочатку зробити A1/A2/A3, щоб новий slice одразу проходив через стабільніші contracts.

---

# 17. Фінальна фіксація

```text
SEMA_ATOM_MASTER_PLAN_V1:
APPROVED AS OFFLINE EPISODIC MEMORY ROADMAP
```

## Current truth

```text
SemaAtom уже реальний як offline evidence pipeline.
SemaAtom ще не готовий як policy authority.
SemaAtom має високу цінність для NNR/gate calibration.
SemaAtom має продовжуватись batch-first.
SemaAtom потребує більше data slices.
```

## Головна фраза

```text
Ми будуємо не “AI, який сам міняє трейдинг”,
а доказову памʼять, яка не дозволяє нам міняти трейдинг без фактів.
```

## Найближча ціль

```text
перетворити SemaAtom із POC-серії
у стабільний offline memory MVP,
який регулярно приймає frozen runtime slices
і видає доказові candidates / rejections для policy calibration.
```

## Кінцева практична ціль

```text
знайти, довести і стабілізувати перші context-и,
де policy зміна або gate calibration
після fees/slippage/execution haircut
має позитивний очікуваний ефект.
```

Коротко: **ми вже довели, що памʼять народжується. Тепер треба довести, що вона стабільно допомагає заробляти або уникати поганих змін.**
