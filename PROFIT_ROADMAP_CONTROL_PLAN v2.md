# AURORA / PHENIX — PROFIT ROADMAP CONTROL PLAN v2

**Статус:** робочий SSOT-план для проєкту
**Версія:** v2 після ширшої звірки контексту
**Роль документа:** тримати всі нові чати, агентні задачі, архітектурні рішення, R&D-треки й runtime-аудити на одній дорозі
**Головна мета:** довести Aurora/Phenix до **стабільного хоча б невеликого прибутку**, щоб система почала частково або повністю фінансувати власний подальший розвиток.

---

# 0. Головна теза

Aurora/Phenix уже не є маленьким експериментом.

Це велика подієво-орієнтована trading-система з багатьма доменами, тисячами тестів, кількома стратегічними й когнітивними шарами, runtime-логами, shadow-телеметрією, policy gates, Neocortex, MetaFSM2, Judge / alpha_search, SemaAtom, calibrators, execution FSM, regime logic, scoring logic, sidecar groundwork і накопиченим конфігураційним боргом.

Поточна проблема не в тому, що “нічого нема”.

Поточна проблема:

```text
система велика,
система вже досить далеко побудована,
система переобережна,
система місцями over-policy,
система має timer/config/scoring drift,
і її треба довести до першого доказового прибуткового operating band.
```

Тому цей план існує для одного:

```text
тримати нас на дорозі до прибутку
і не дозволяти розпорошитись у нові красиві R&D-ідеї,
поки незакриті поточні критичні задачі.
```

Цей документ має бути не “ще одним roadmap”.

Це — **контрольний план концентрації**.

---

# 1. Кінцева мета

Фінальна мета поточного циклу:

```text
знайти, довести і стабілізувати перший прибутковий режим роботи Aurora/Phenix.
```

Не обовʼязково великий прибуток.

Перший прийнятний фініш:

```yaml
profit_goal_v1:
  target: small_stable_net_positive
  after_costs:
    - fees
    - slippage
    - execution haircut
  evidence:
    - runtime logs
    - accepted/rejected analysis
    - SemaAtom forward slice
    - policy calibrator report
    - NNR/gate map
    - timer interaction map
    - config/scoring ownership audit
  scope:
    - 1 primary strategy
    - optionally 1 secondary strategy after triage
    - limited symbol set
    - no broad live-risk expansion
```

Система має почати хоча б частково себе годувати:

```text
прибуток → додаткові AI-підписки / токени / R&D темп
```

Поки система не має profit loop, кожен новий великий R&D-напрям має проходити жорсткий фільтр:

```text
чи це реально наближає до малого стабільного net-positive режиму?
```

Якщо відповідь нечітка — напрям відкладається.

---

# 2. Поточна реальність проєкту

## 2.1 Великі треки

```yaml
current_tracks:
  MetaFSM2:
    status: late_stage
    official_state:
      phase_5: CLOSED
      execution_phase_6: CLOSED
      current_main_track: Phase_7_First_Cutover_Target_Selection
    role:
      - replayable decision/execution truth
      - lifecycle hardening
      - future cutover
      - restart/recovery correctness
      - causal observability
    current_priority: important_but_not_primary_profit_bottleneck

  Neocortex:
    status: approximately_50_60_percent_of_concept
    known_state:
      phase_7: ACCEPTED_WITH_RESIDUALS
      current_direction: phase_8A_evidence_collection
    role:
      - bounded adaptive trust controller
      - shadow evidence collection
      - ObservationEnvelope validation
      - authority request/response integrity
      - decision outcome ledger
    current_priority: shadow/evidence/authority_integrity
    forbidden_now:
      - live authority expansion without proof
      - direct CMD emission
      - direct open/close
      - YAML mutation
      - gate override

  Judge_alpha_search:
    status: codebase_almost_complete
    current_phase: validation
    role:
      - strategy comparison
      - shadow verdicts
      - policy cortex
      - expert arbitration
      - evidence normalization
    current_priority: validate_and_use_for_strategy_comparison
    forbidden_now:
      - execution authority
      - unvalidated policy override
      - hidden scoring replacement

  SemaAtom:
    status: strong_offline_RnD_POC
    role:
      - semantic episodic memory
      - accepted/rejected analysis
      - counterfactual economics
      - policy evidence engine
    current_priority: P0_high
    reason:
      - directly helps NNR/gate calibration
      - cheap relative to broad runtime architecture
      - already produced useful POC results

  PositionPolicySidecar:
    status: partially_implemented_shell
    known_capabilities:
      - typed config exists
      - modes disable/shadow/enable exist
      - execution_position-local collaborator wired
      - schemas / registry / trade_lifecycle logging added
      - replay validation tool exists
      - tests were reported green in prior packages
    current_gap:
      - runtime sidecar row emission still needs proof on fresh logs
    role:
      - policy container / observability shell
      - not yet proven profit-driving post-entry layer

  ROI_gate:
    status: not_started_as_policy_profile_or_action_track
    role:
      - future post-entry ROI-based continuation/protection policy
    current_priority: not_action_now
    allowed_now:
      - feasibility audit
      - input surface audit
      - overlap analysis with sidecar / NNR / lifecycle logs
    forbidden_now:
      - action-capable PROTECT/EXIT
      - new hard gate
      - live enforcement
```

## 2.2 Головний симптом

```text
Коли всі NNR / policy gates увімкнені → система майже паралізована, ордери майже не проходять.

Коли частину gates вимкнути → система починає торгувати, але дає маленький збиток.
```

Це означає:

```text
execution не мертвий;
стратегії здатні генерувати входи;
policy stack занадто жорсткий;
просте вимикання gates не дає прибутку;
прибуток, імовірно, лежить у точній калібрації між “паралічем” і “надмірною свободою”.
```

---

# 3. Головні блокери прибутку

## Blocker 1 — NNR / policy paralysis

Система має багато reject/gate шарів. Коли вони всі enforce, торгівля майже зупиняється.

Потрібно довести:

```yaml
nnr_questions:
  - які gates реально захищають від toxic trades?
  - які gates душать favorable trades?
  - які gates мають слабкий або відсутній економічний доказ?
  - які gates треба послабити?
  - які gates треба перевести в observe-only?
  - які gates треба залишити hard?
  - які gates конфліктують між собою?
  - які gates блокують не через alpha weakness, а через timer/config/scoring drift?
```

Це головний money choke point.

---

## Blocker 2 — timers / temporal incoherence

У системі накопичилось близько 50 таймерів / TTL / cooldown / backoff / defer / watchdog / liveness / hysteresis механізмів.

Ризик:

```text
сигнал готовий → gate ще в cooldown
cooldown завершився → features stale
features alive → regime stale
regime alive → defer expired
defer ready → opportunity gone
order ready → watchdog expired
entry possible → embargo active
```

Потрібен повний timer audit, бо таймери можуть бути невидимою причиною policy paralysis або втрати edge.

Timer audit — це не косметична робота. Це P0, бо time incoherence може фальсифікувати висновки всіх інших аналізів.

---

## Blocker 3 — config SSOT debt

Система виросла з маленького скрипта до великої машини. У конфігураціях накопичився борг:

```yaml
config_risks:
  - дубльовані поля
  - legacy поля
  - поля, які валідяться, але не споживаються runtime
  - поля, які споживаються не з того namespace
  - implicit fallback
  - stale defaults
  - strategy/profile/domain ownership drift
  - config values that look active but are metadata only
  - runtime consumers that bypass intended SSOT
```

Калібрувати policy поверх брудного config layer небезпечно.

Config cleanup має бути не “красиво привести YAML”, а:

```text
прибрати або зафіксувати те, що заважає runtime truth і calibration truth.
```

---

## Blocker 4 — scoring ownership contamination

Є стара проблема:

```text
Quadratic scoring / Aurora scoring v3 у якийсь момент став активною scoring-логікою Aurora
і потенційно міг вплинути на shared scoring або інші стратегії.
```

Потрібно довести:

```yaml
scoring_audit_questions:
  - чи quadratic scoring належить тільки Aurora?
  - чи він протік у shared gateway / calibrators / strategy traces?
  - чи інші стратегії несвідомо залежать від Aurora scoring semantics?
  - чи Judge / alpha_search бачить чисті strategy outputs?
  - чи policy calibrators калібрують правильну логіку?
  - чи score semantics не змішані між Aurora / MR / MD-AMR / external-intent?
  - чи legacy scoring surfaces не створюють ілюзію активності?
```

Без цього глибока калібрація може бути небезпечною: можна калібрувати не той score, не ту стратегію або не той gateway path.

---

## Blocker 5 — strategy portfolio frozen

На поточному етапі реально активна переважно Aurora. Інші стратегії заморожені або підозрілі.

Це звужує шанс знайти прибутковий режим.

Потрібно не розморожувати все, а провести triage:

```yaml
strategy_unfreeze_triage:
  aurora:
    status: active
    issue: overgated / small_loss_when_relaxed
    role: primary current profit candidate

  mean_reversion:
    status: frozen_or_suspect
    required:
      - reason audit
      - minimal replay
      - config/profile sanity check
      - economic proof before activation

  md_amr:
    status: frozen_or_suspect
    required:
      - baseline verification
      - accepted roadmap state check
      - economic replay
      - no broad cognitive expansion before baseline truth

  llm_microstructure:
    status: external_intent / not immediate money path
    required:
      - keep isolated
      - do not let external-intent path contaminate core scoring

  judge:
    status: validation
    role:
      - compare
      - arbitrate
      - explain
      - not execute
```

Після Aurora можна розморожувати тільки **одну другу стратегію-кандидат**.

Не всі одразу.

---

## Blocker 6 — insufficient high-quality backtest horizon

Відкриті дані, придатні для повного backtest, дають приблизно обмежений шмат історії. Для системи з режимами, gates, tail events, volatility regimes, black swans, новинами, trend/range cycles — цього мало.

Але синтетичні дані не мають бути “рандомними цифрами”.

Майбутня правильна ціль:

```text
real-candle-based Market Scenario Composer
```

Не генерувати ринок з нуля, а:

```text
Binance candles
→ regime/trend segmentation
→ semantic blocks
→ resampling/mutation/composition
→ inserted scenarios:
   news shock,
   black swan,
   pump,
   dump,
   squeeze,
   fake breakout,
   low-vol chop,
   liquidity thinning,
   post-spike decay
→ multi-year synthetic scenario stream
```

Це важливо, але не має зараз випередити закриття чатів і P0 profit blockers.

---

# 4. Поточне ресурсне обмеження

AI-токени, агенти й підписки стали дорожчими й більш лімітованими.

Наявні ресурси:

```yaml
resources:
  laptops:
    practical_active: 2

  binance_accounts:
    current: 4
    possible: 5_to_6

  subscriptions:
    github_copilot_pro_plus: available
    gpt_plus_codex: available_but_limited
    google_ai_pro: 2_accounts
    gemini_cli: available
    antigravity: available_but_strict_limits

  active_chats:
    count: approximately_13
    issue: many are waiting for new runtime evidence
```

Висновок:

```text
проблема не в нестачі агентів,
а в тому, що широкі задачі стали занадто дорогими.
```

Тепер кожен агентний запуск має бути bounded:

```text
один prompt
→ один вузький seam
→ один report
→ один verdict
→ або closure, або наступний bounded package.
```

---

# 5. Token Economy Law

Токени тепер є engineering constraint.

Це не побутова незручність. Це обмеження виробничого процесу.

```yaml
token_economy_law:
  every_agent_task_must_have:
    - one narrow question
    - one bounded scope
    - explicit forbidden actions
    - exact source of truth
    - report/verdict
    - closure condition

  forbidden_prompt_types:
    - "продовжуй розвиток"
    - "зроби повністю"
    - "проаналізуй все"
    - "реалізуй весь домен"
    - "подивись широко і придумай"
```

Замість цього:

```yaml
good_prompt_shape:
  mode:
    - read_only_audit
    - implementation_package
    - runtime_forensic
    - report_reconciliation
    - closure_card

  scope:
    - exact files or logs
    - exact question
    - exact forbidden actions
    - exact output report

  acceptance:
    - verdict enum
    - tests required
    - evidence required
    - residuals required
```

---

# 6. Single Authority Chain Law

Це один із найважливіших законів плану.

Aurora/Phenix не має права перетворитися на систему з багатьма runtime decision centers, які одночасно тягнуть кермо.

Canonical chain:

```text
Strategy
→ DecisionMaking
← Neocortex pre-check only
→ ExecutionPosition
→ PositionPolicySidecar post-entry evaluation only
→ MetaFSM2 lifecycle formalization / cutover seam
→ Judge evaluation / comparison unless explicitly promoted
→ SemaAtom offline evidence only
```

## Дозволені ролі

```yaml
authority_chain_roles:
  Strategy:
    owns:
      - signal/opinion generation
    does_not_own:
      - execution truth
      - portfolio truth
      - final gate policy

  DecisionMaking:
    owns:
      - trade intent policy
      - safety gate interpretation
      - intent formation
      - reject normalization
    does_not_own:
      - exchange lifecycle truth

  Neocortex:
    owns:
      - trust evaluation in shadow/advisory/gated modes
    does_not_own:
      - direct CMD emission
      - order placement
      - YAML mutation
      - execution truth

  ExecutionPosition:
    owns:
      - order lifecycle truth
      - position lifecycle truth
      - brackets
      - reconciliation
      - close execution
    does_not_own:
      - alpha reasoning
      - policy learning

  PositionPolicySidecar:
    owns:
      - derived post-entry policy evaluation
      - recommendation/observability shell
    does_not_own:
      - execution lifecycle truth
      - hidden close authority
      - bracket truth

  MetaFSM2:
    owns:
      - future formalized lifecycle transitions after cutover proof
    does_not_own:
      - whole-domain big-bang replacement

  Judge:
    owns:
      - shadow verdicts
      - expert comparison
      - arbitration analysis
    does_not_own:
      - execution
      - direct live orders
      - unvalidated policy override

  SemaAtom:
    owns:
      - offline memory/evidence artifacts
    does_not_own:
      - runtime authority
      - YAML mutation
      - direct gate changes
```

## Заборонено

```yaml
single_authority_forbidden:
  - Neocortex emitting CMD directly
  - Judge owning execution
  - SemaAtom mutating YAML
  - Sidecar becoming lifecycle truth owner
  - MetaFSM2 big-bang replacing execution_position
  - ROI-gate action logic before policy/timer/config clarity
  - any hidden fallback business logic
```

---

# 7. Новий операційний режим чатів

## 7.1 Chat Closure First Law

Перший крок — не новий development plan, а closure active chats.

Активні чати зараз є operational debt.

Перед новими великими роботами треба:

```yaml
chat_closure_first_law:
  before_new_major_work:
    - classify all active chats
    - close/archive completed ones
    - merge overlapping ones
    - mark waiting-runtime chats
    - reduce HOT chats to max 3-4
```

Кожен чат має отримати closure verdict:

```yaml
chat_closure_verdicts:
  DONE_AND_ARCHIVED:
    meaning: питання вирішене, звіт є, runtime/тести підтвердили або задача більше не актуальна

  WAITING_RUNTIME_EVIDENCE:
    meaning: без нового runtime slice чесно завершити неможливо

  NEEDS_ONE_FINAL_AUDIT:
    meaning: потрібен один короткий агентний аудит і після цього закриття

  MERGE_INTO_MONEY_PATH:
    meaning: чат важливий, але його треба злити в центральний profit-roadmap

  DEFER_COLD:
    meaning: не витрачати токени зараз, але не видаляти

  KILL:
    meaning: трек не дає прибутку, доказу або безпеки в найближчому циклі
```

---

## 7.2 Один runtime slice має годувати багато closure reports

Більшість чатів чекають нового runtime-прогону. Тому наступний runtime має стати контрольним зрізом:

```yaml
runtime_control_slice:
  purpose:
    - перевірити, що виправилось після патчів
    - дати evidence для закриття чатів
    - оновити SemaAtom forward corpus
    - перевірити NNR / timers / policy behavior
    - дати матеріал Judge / Neocortex / execution audits
    - перевірити sidecar runtime row emission
    - перевірити scoring/config/timer assumptions

  consumers:
    - SemaAtom
    - timer audit
    - NNR calibration
    - trading analysis
    - Neocortex shadow evidence
    - Judge validation
    - scoring audit
    - config cleanup
    - execution lifecycle checks
    - sidecar observability validation
```

Правило:

```text
один runtime → багато closure reports
```

Це економить токени.

---

# 8. Класифікація активних чатів

Кожен чат має бути переведений в один з режимів:

```yaml
chat_modes:
  HOT:
    meaning: прямо впливає на profit loop або critical blocker
    max_count: 3_to_4

  WARM:
    meaning: важливий, але не щоденний
    cadence: short bounded audit only

  COLD:
    meaning: цінний, але не зараз
    action: no tokens unless dependency opens

  ARCHIVE:
    meaning: closed context
    action: save summary, close browser tab

  KILL:
    meaning: not useful for current profit goal
    action: close without continuation
```

Зараз HOT не можуть бути всі 13 чатів.

Рекомендовані HOT-фронти:

```yaml
recommended_hot_fronts:
  - runtime_closure_and_chat_shutdown
  - NNR_policy_calibration
  - timers_audit
  - config_scoring_boundary
  - SemaAtom_forward_proof
```

Якщо HOT більше 4 — система управління знову розпорошується.

---

# 9. Правило проти нових ідей

Цей документ має тримати і користувача, і асистента.

Якщо в новому чаті або в процесі роботи зʼявляється нова ідея типу:

```text
а давай ще зробимо новий модуль
а давай ще один R&D напрям
а давай одразу ROI-gate action
а давай нову ML-модель
а давай ще один intelligence layer
а давай повний synthetic market перед closure
```

асистент має жорстко зупинити:

```text
Ні. Не зараз.
Це може бути хороша ідея, але вона не проходить profit-roadmap gate.
Спочатку закриваємо активні чати, runtime evidence, NNR/timers/config/scoring blockers,
SemaAtom forward proof і перший прибутковий operating band.
Після цього повернемось.
```

Формула:

```text
нові ідеї не заборонені назавжди,
але вони не мають права красти ресурси з profit path.
```

---

# 10. Пріоритети після закриття чатів

## P0 — Profit Loop Recovery

Це головна лінія.

```yaml
P0_profit_loop:
  goals:
    - знайти, чому система або паралізована, або small-loss
    - довести, які gates корисні / шкідливі / over-strict
    - вирівняти timers
    - прибрати config/scoring ambiguity
    - знайти перший net-positive operating band

  required_tracks:
    - active_chat_closure_matrix
    - runtime_control_slice_analysis
    - NNR calibration
    - timer audit
    - config SSOT blocker list
    - scoring ownership audit
    - SemaAtom forward evidence
    - sidecar row emission validation if using sidecar data
```

---

## P1 — Strategy Portfolio Recovery

Після того, як Aurora/gates/scoring не є мутними:

```yaml
P1_strategy_recovery:
  goal:
    - вибрати одну другу стратегію для розморозки

  candidates:
    - mean_reversion
    - md_amr

  rules:
    - не розморожувати все
    - одна стратегія-кандидат за раз
    - replay + economic proof
    - Judge може допомагати як shadow evaluator
    - scoring semantics must be clean before comparison
```

---

## P2 — Cognitive Validation

```yaml
P2_cognitive:
  Neocortex:
    role:
      - shadow trust controller
      - evidence integrity
      - ObservationEnvelope
      - authority ledger
    forbidden_now:
      - live authority expansion without proof
      - runtime policy mutation

  Judge:
    role:
      - shadow expert aggregator
      - strategy comparison
      - validation
    forbidden_now:
      - direct execution authority
      - unvalidated policy override

  MetaFSM2:
    role:
      - first cutover target selection
      - truth/cutover readiness
    forbidden_now:
      - whole execution_position migration
```

---

## P3 — Synthetic Market Scenario Composer

```yaml
P3_synthetic_data:
  reason:
    - limited real backtest horizon is insufficient

  first_goal:
    - not perfect market simulator
    - real-candle-based scenario composer

  scope:
    - 2_to_3_symbols
    - multi-year scenario streams
    - regime-labeled segments
    - news/shock/swan/trend/range scenarios

  priority:
    - important
    - but not before P0 closure
```

---

## P4 — ROI-gate Action Path

```yaml
P4_roi_gate:
  status: not_started_as_action_profile
  current_decision: do_not_start_as_action_track_yet

  allowed_now:
    - roadmap review
    - input surface audit
    - overlap analysis with sidecar / NNR / lifecycle logs

  forbidden_now:
    - action-capable implementation
    - new hard gate
    - protect/exit authority before P0 clarity

  reason:
    - current policy stack is already over-restrictive
    - adding another gate before calibration may deepen paralysis
```

---

# 11. SemaAtom role in the profit plan

SemaAtom is not Neocortex. It is not runtime authority.

SemaAtom is:

```text
offline semantic episodic memory and policy evidence engine
```

Current role:

```yaml
SemaAtom_current_role:
  - collect accepted/rejected experience
  - classify toxic/favorable/policy-too-strict contexts
  - compute counterfactual outcomes
  - compute side-aware MFE/MAE
  - apply stability matrix
  - apply economic simulation after fees/slippage/haircut
  - prevent fake optimization
  - protect trainable corpus from incomplete/unresolved rows
```

SemaAtom should directly support:

```yaml
SemaAtom_supports:
  - NNR calibration
  - gate relaxation/reinforcement decisions
  - accepted vs rejected outcome analysis
  - policy-too-strict detection
  - toxic context detection
  - first profitable operating band search
```

SemaAtom must remain:

```yaml
SemaAtom_constraints:
  mode: offline_read_only
  no_runtime_effect: true
  no_yaml_mutation: true
  no_direct_policy_change: true
```

## SemaAtom priority correction

SemaAtom is promoted to P0 evidence engine because:

```yaml
SemaAtom_P0_reason:
  - extraction POC is working
  - rejected/accepted memory directly answers gate calibration questions
  - POC already showed statistical signal can differ from economic profit
  - Stability Matrix reduces false positives
  - FC_01A/FC_01B hardened trainable corpus admission
```

---

# 12. MetaFSM2 role in the profit plan

MetaFSM2 is important, but not the first profit bottleneck unless current execution truth blocks evidence.

Official current orientation:

```yaml
MetaFSM2_status:
  phase_5: CLOSED
  execution_phase_6: CLOSED
  current_main_track: Phase_7_First_Cutover_Target_Selection
```

Role:

```yaml
MetaFSM2_role:
  - replayable execution/decision truth
  - lifecycle hardening
  - future cutover
  - restart/recovery correctness
  - causal observability
```

Current rule:

```text
Do not let MetaFSM2 consume the entire money-path unless it is directly blocking runtime evidence or execution safety.
```

MetaFSM2 continues, but bounded.

Forbidden:

```yaml
MetaFSM2_forbidden_now:
  - big_bang_migration
  - whole_execution_position_replacement
  - migration_by_aesthetics
  - cutover_without_runtime_proof
```

---

# 13. Neocortex role in the profit plan

Neocortex is not the immediate profit lever.

It is the future trust controller.

Current safe role:

```yaml
Neocortex_current_role:
  - shadow evidence collection
  - ObservationEnvelope validation
  - authority request/response integrity
  - decision outcome ledger
  - trust decision audit
  - no live control expansion
```

Forbidden until proof:

```yaml
Neocortex_forbidden_now:
  - direct CMD emission
  - direct open/close
  - YAML mutation
  - gate override
  - authority expansion based on incomplete memory
  - training/OPE/reward_valid before evidence corpus is proven
```

Correct connection with SemaAtom:

```yaml
SemaAtom_to_Neocortex_future:
  mode: read_only_artifact_bridge
  allowed:
    - offline memory candidate import
    - evidence comparison
    - calibration support
  forbidden:
    - runtime authority
    - direct trust override
    - direct policy mutation
```

---

# 14. Judge / alpha_search role in the profit plan

Judge should be completed because codebase is near-ready.

But its correct role now:

```yaml
Judge_current_role:
  - validation
  - shadow verdicts
  - strategy comparison
  - expert aggregation
  - evidence normalization
  - not execution authority
```

Judge can help decide:

```yaml
Judge_questions:
  - which strategy should be unfrozen first?
  - which strategy has regime-specific edge?
  - which strategy duplicates Aurora?
  - which signals conflict?
  - which policy rejects look over-strict?
  - which strategy outputs are incomparable because scoring semantics differ?
```

Forbidden:

```yaml
Judge_forbidden_now:
  - direct execution
  - live order authority
  - hidden policy override
  - bypassing DecisionMaking / ExecutionPosition ownership
```

---

# 15. PositionPolicySidecar vs ROI-gate

This distinction is mandatory.

## PositionPolicySidecar

```yaml
PositionPolicySidecar:
  status: partially_implemented_shell
  owns:
    - post-entry derived evaluation
    - recommendation / observability traces
    - sidecar policy surface if validated
  does_not_own:
    - lifecycle truth
    - close execution truth
    - bracket truth
```

Before using it for ROI-gate, prove:

```yaml
Sidecar_required_next_proofs:
  - runtime rows are emitted on fresh logs
  - suppression reasons are visible
  - sidecar is not silently inactive
  - no execution outcome is changed by shadow mode
  - no hidden action path exists
```

## ROI-gate

```yaml
ROI_gate:
  status: not_started_as_action_logic
  future_role:
    - post-entry continuation/protection/exit policy
  current_rule:
    - do not start action-capable implementation before P0 clarity
```

---

# 16. Timer audit role

Timer audit is P0 because time incoherence can fake every other conclusion.

Timer categories to map:

```yaml
timer_categories:
  market_data:
    - websocket heartbeat
    - receive timeout
    - tick ttl
    - bar ttl

  features:
    - features ttl
    - bar event age mode
    - warmup windows

  regime:
    - basis timeframe
    - liveness factor
    - hysteresis bars
    - stale regime handling

  decision_making:
    - cooldown
    - reentry cooldown
    - defer ttl
    - qos cooldown
    - embargo windows
    - arming retry backoff

  execution:
    - order ttl
    - watchdog timeout
    - bracket timeout
    - pending exposure ttl
    - orphan cleanup

  shadow_neocortex_judge:
    - authority timeout
    - capture deadline
    - ledger flush cadence
```

Required output:

```yaml
timer_audit_output:
  - canonical timer map
  - owner per timer
  - config path
  - runtime consumer
  - unit: ms/sec/bars
  - interaction risks
  - profit-impact hypothesis
  - recommended cleanup / no-change
```

---

# 17. Config cleanup role

Config cleanup must not be cosmetic.

Allowed config cleanup:

```yaml
allowed_config_cleanup:
  - remove or mark unused fields
  - identify no-runtime-consumer fields
  - fix SSOT duplication
  - remove silent fallbacks
  - align YAML/Pydantic/runtime ownership
  - expose missing config only if runtime already needs it
  - clarify strategy/domain/trading ownership
```

Forbidden config cleanup:

```yaml
forbidden_config_cleanup:
  - broad beautification
  - renaming without operational reason
  - changing defaults without replay/calibrator proof
  - mixing strategy policy into domain config without SSOT decision
  - deleting legacy fields without migration evidence
```

---

# 18. Scoring audit role

Scoring ownership must be clarified before deep calibration.

Required audit:

```yaml
SCORING_OWNERSHIP_AND_CROSS_STRATEGY_CONTAMINATION_AUDIT:
  questions:
    - where exactly does quadratic scoring live?
    - is it Aurora-only?
    - does any other strategy consume it?
    - does shared gateway normalize all strategy scores the same way?
    - do calibrators assume Aurora scoring shape?
    - do Judge envelopes preserve strategy-specific score semantics?
    - are legacy scoring surfaces still parsed but unused?
    - does any experience/memory layer affect scoring across strategies?
```

Output verdict:

```yaml
scoring_verdicts:
  CLEAN_AURORA_ONLY:
    meaning: no contamination

  SHARED_BUT_EXPLICIT:
    meaning: shared scoring exists but is contractually clear

  CONTAMINATION_FOUND:
    meaning: Aurora scoring semantics leak into other strategies

  CALIBRATION_BLOCKED:
    meaning: policy calibration unsafe until scoring ownership is repaired
```

---

# 19. Synthetic Market Scenario Composer

Synthetic data is important because limited real historical data is not enough.

But the first version must not try to become a perfect market simulator.

Correct first target:

```text
Market Scenario Composer, not random candle generator.
```

Inputs:

```yaml
synthetic_inputs:
  - Binance candles
  - regime segmentation
  - trend/range/volatility labels
  - real distribution statistics
  - known shock templates
```

Generated scenarios:

```yaml
synthetic_scenarios:
  - long trend up
  - long trend down
  - low-vol chop
  - high-vol chop
  - fake breakout
  - squeeze then expansion
  - pump then decay
  - dump then recovery
  - liquidity thinning
  - spread widening
  - black swan
  - news shock
  - post-spike exhaustion
```

Initial scope:

```yaml
synthetic_scope_v1:
  symbols: 2_to_3
  target_years: 5
  validation:
    - semantic similarity to real regimes
    - distribution sanity
    - strategy/gate response sanity
    - no claim of true market prediction
```

Priority:

```text
important, but after P0 blockers.
```

---

# 20. New chat startup protocol

Every new project chat must begin by checking this plan.

The assistant must not immediately start implementing.

First message in a new chat should:

```text
1. identify which active roadmap area this chat belongs to;
2. state current assumed goal;
3. ask only the missing questions needed to avoid wrong work;
4. classify the chat mode: HOT / WARM / COLD / ARCHIVE / KILL;
5. refuse broad expansion if it violates profit-roadmap priority.
```

## Required startup questions

The assistant should ask a compact subset of these, depending on context:

```yaml
new_chat_questions:
  identity:
    - Який це трек? NNR, timers, SemaAtom, MetaFSM2, Neocortex, Judge, scoring, config, strategy, synthetic?
    - Це новий чат чи продовження старого?

  current_state:
    - Який останній agent report / verdict по цьому треку?
    - Чи був новий runtime після останнього звіту?
    - Який runtime slice / дата / логи треба вважати актуальними?

  closure:
    - Цей чат треба закрити, продовжити чи злити в money-path?
    - Який closure verdict очікується?

  allowed_actions:
    - Це read-only audit чи можна міняти код?
    - Якщо можна міняти код — які файли/поверхні дозволені?
    - Чи дозволені YAML/config зміни?
    - Чи потрібен REPORT?

  profit_relevance:
    - Як ця задача наближає до малого стабільного прибутку?
    - Вона P0, P1, P2, P3 чи cold?

  evidence:
    - Які logs/artifacts/tests є джерелом правди?
    - Що буде вважатися validation?
    - Що буде вважатися fail?
```

Якщо користувач не відповів на критичні питання, асистент має не вигадувати стан, а дати bounded assumption і явно позначити unknown.

---

# 21. Definition of Done

Жодна задача не DONE без:

```yaml
done_requires:
  - explicit verdict
  - files changed if any
  - tests run if code changed
  - runtime evidence if runtime claim made
  - report artifact or closure card
  - proven facts
  - remaining unknowns
  - next step or archive decision
```

Forbidden:

```yaml
forbidden_done_claims:
  - "fixed" without validation
  - "works" without tests/runtime evidence
  - "root cause found" from static reading only
  - "ready for live" from POC only
```

---

# 22. Agent prompt policy

Because tokens are scarce, prompts must be narrow.

Good prompt shape:

```yaml
agent_prompt_shape:
  mode:
    - read_only_audit
    - implementation_package
    - runtime_forensic
    - report_reconciliation
    - closure_card

  scope:
    - exact files or logs
    - exact question
    - exact forbidden actions
    - exact output report

  acceptance:
    - verdict enum
    - tests required
    - evidence required
    - residuals required
```

Bad prompt shape:

```text
продовжуй розвиток
зроби повністю
поглиблено проаналізуй все
реалізуй весь Neocortex
зроби повний ROI-gate
```

---

# 23. Immediate operating doctrine

До закриття активних чатів:

```yaml
immediate_doctrine:
  do:
    - чекати / збирати новий runtime slice
    - закривати чати closure cards
    - не відкривати нові великі напрями
    - берегти токени
    - переносити важливе в central money-path
    - використовувати один runtime slice для багатьох reports

  do_not:
    - запускати ROI-gate action implementation
    - запускати повний synthetic generator
    - відкривати нові Judge/Neocortex feature expansions
    - робити broad config refactor
    - розморожувати всі стратегії одночасно
    - запускати широкі агентні prompts без closure contract
```

---

# 24. Central Roadmap Sequence

Після runtime і closure:

```yaml
central_sequence:
  phase_0:
    name: Chat Closure and Runtime Evidence Consolidation
    goal: close or classify all active chats
    output:
      - active_chat_closure_matrix
      - runtime_control_slice_index

  phase_1:
    name: Profit Blocker Localization
    goal: locate NNR/timer/config/scoring blockers
    output:
      - NNR gate map
      - timer interaction map
      - config SSOT blocker list
      - scoring ownership verdict
      - sidecar runtime row emission verdict

  phase_2:
    name: SemaAtom Forward Evidence
    goal: run accepted/rejected forward slice analysis
    output:
      - policy-too-strict candidates
      - toxic-context candidates
      - favorable-context candidates
      - economic verdict after costs
      - trainable/incomplete accounting

  phase_3:
    name: Bounded Policy Calibration
    goal: adjust 1-2 gates only if evidence supports it
    output:
      - YAML-only or observe-only proposal
      - replay/counterfactual validation
      - runtime canary plan

  phase_4:
    name: Runtime Canary
    goal: test first profit-band candidate
    output:
      - net PnL after fees/slippage
      - reject/accept distribution
      - lifecycle giveback analysis
      - timer/gate interaction evidence

  phase_5:
    name: Strategy Portfolio Triage
    goal: pick one secondary strategy candidate
    output:
      - unfreeze candidate verdict
      - minimal replay
      - Judge comparison
      - scoring compatibility verdict

  phase_6:
    name: Cognitive/Truth Layer Continuation
    goal: continue MetaFSM2/Neocortex/Judge without blocking money-path
    output:
      - bounded reports only
      - no authority expansion without proof

  phase_7:
    name: Synthetic Scenario Composer
    goal: build long-horizon scenario data after P0 clarity
    output:
      - scenario taxonomy
      - real-candle segmentation
      - synthetic multi-year test streams

  phase_8:
    name: ROI-Gated Post-Entry Policy
    goal: only after sidecar rows + P0 clarity, design bounded shadow ROI policy
    output:
      - shadow-only ROI policy candidate
      - no action until replay and runtime proof
```

---

# 25. Correction Addendum — wider context reconciliation

This plan explicitly incorporates broader project context:

```yaml
corrections:
  1:
    statement: Position Policy Sidecar is not "not started".
    correction:
      - sidecar shell/config/registry/logging pieces are partially implemented and tested
      - ROI-gated action policy is not started
      - sidecar must first prove runtime row emission

  2:
    statement: MetaFSM2 is not a vague future track.
    correction:
      - Phase 5 CLOSED
      - Execution Phase 6 CLOSED
      - current main track is Phase 7 First Cutover Target Selection
      - whole-domain migration remains forbidden

  3:
    statement: Neocortex is not empty.
    correction:
      - around 50-60% concept implementation
      - current safe direction is Phase 8A evidence collection
      - training/OPE/reward_valid/live authority remain forbidden

  4:
    statement: Judge is near code-complete.
    correction:
      - current role is validation and strategy comparison
      - not execution owner

  5:
    statement: SemaAtom is not minor.
    correction:
      - promote to P0 evidence engine for NNR/policy calibration
      - it has accepted/rejected extraction, counterfactual outcome, stability filtering, and economic simulation

  6:
    statement: main profit blocker is not architecture incompleteness.
    correction:
      - main blocker is over-policy + timer/config/scoring incoherence

  7:
    statement: active chat closure is mandatory.
    correction:
      - open chats are operational debt
      - close/classify before opening new major work

  8:
    statement: token economy is now first-class constraint.
    correction:
      - broad prompts forbidden unless converted into bounded report-producing packages
```

---

# 26. Assistant’s hard behavioral rule

This document is also a rule for the assistant.

If the user drifts into a new idea before core blockers are closed, the assistant must respond in spirit:

```text
Ні. Не зараз.
Це може бути хороша ідея, але зараз вона краде ресурс у profit path.
Спочатку закриваємо активні чати, runtime evidence, NNR/timers/config/scoring,
SemaAtom forward proof і перший прибутковий operating band.
Після цього повернемось.
```

Assistant must prioritize:

```yaml
assistant_priority:
  1: protect profit roadmap
  2: reduce open loops
  3: demand evidence
  4: avoid broad refactors
  5: refuse premature expansion
  6: preserve YAML/Pydantic/contract discipline
  7: keep user focused when user becomes overloaded
  8: protect token economy
  9: preserve single authority chain
```

---

# 27. Final compact mission statement

```text
Aurora/Phenix уже побудована достатньо далеко, щоб перестати нескінченно додавати шари.

Поточна місія — закрити активні чати, зібрати runtime evidence,
локалізувати NNR/timer/config/scoring blockers,
використати SemaAtom і calibrators для доказового tuning,
знайти перший малий net-positive operating band,
і тільки після цього масштабувати Neocortex, Judge, MetaFSM2, ROI-gate та synthetic data.

Головний фініш цього плану — прибуток.
Не красива архітектура.
Не ще один модуль.
Не ще один R&D-фронт.
А перший стабільний прибутковий режим, який дозволить системі фінансувати свій подальший розвиток.
```

---

# 28. Інструкція для додавання в базу / нові чати

Коли цей документ буде доданий у базу проєкту, кожен новий чат має стартувати так:

```text
1. Звіритися з AURORA / PHENIX — PROFIT ROADMAP CONTROL PLAN v2.
2. Визначити, який трек обговорюється.
3. Оцінити, чи задача HOT/WARM/COLD/ARCHIVE/KILL.
4. Задати короткий список missing-context questions.
5. Не починати implementation без відповіді на критичні питання.
6. Якщо задача не веде до profit path або closure — зупинити або відкласти.
7. Не дозволяти новим R&D-ідеям красти ресурс у P0.
```
