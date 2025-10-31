# vFoundation ⇆ LLA Transition Roadmap (CA-FSM, Bridges, Proof Kernel) — v1.0

> **Мета документа:** дати чітке, технічно конкретне бачення переходу на архітектуру vFoundation-CA з LLA як о� ьового ядра (Meta-FSM → CA-FSM → домени).
> Тут опи� ані: ціль, поетапний план, Definition of Done (DoD) для кожного етапу, типові ризики/� кладнощі й � по� оби їх вирішення, артефакти, команди та чек-ли� ти приймання.

---

## 0) Коротко про цілі

1. **LLA як “душа” � и� теми:** LLA керує **Meta-FSM/CA-FSM**, збирає індикатори з доменів (execution, risk, data_provider), планує по� лідовні� ть і ієрархію � игналів, адаптує пороги/ваги переходів.
2. **Causal Adaptation:** у� і переходи FSM мають **причинний � лід** і оцінюють� я **Axial Gradient** (AG), який ми концентруємо на **+PnL** (з балан� ом CVaR/латентно� ті/� табільно� ті).
3. **Bridges як нервова � и� тема:** � тандартні **EventBridge / MetricBridge / CommandBridge** дають прозорий канал між vFoundation і LLA.
4. **Proof Kernel + LTL інваріанти:** формальна перевірка, що адаптації не порушують інваріанти безпеки/живучо� ті.
5. **72h Shadow readiness:** перед боєм — 72 години � табільного тікання контуру з логами, acceptance-зрізами, freeze/SBOM і GO-флагом.

---

## 1) Поточний контек� т (узагальнення з ваших інпутів)

* **Репозиторій A (� кладніший, R2Hybrid майже PASS):** робочі те� ти/CI, але ще немає vFoundation; є R2Hybrid орке� тратор, DoD, strict gates.
* **Репозиторій B (про� тішій, базовий vFoundation):** домени (execution, risk, data_provider) є, формат “без моноліту”, � ловники/домени, **але керування доменами ще кульгає**; � аме тут найпро� тіше швидко по� тавити LLA як Meta-FSM/CA-FSM поверх доменів через мо� ти.

**Рекомендація � тарту:**
Почати з **B (про� тішого vFoundation)** як “референ� ної платформи” — тут **швидше** підняти CA-FSM + Bridges + Proof Kernel і до� ягти **72h readiness**. Потім повторно викори� тати цей карка�  у � кладнішому A (R2Hybrid).

---

## 2) Цільова архітектура

```
LLA (Meta-FSM/CA-FSM)
  ├─ Axial Gradient (AG) [+PnL, -CVaR, +Stability, -Latency]
  ├─ Causal Graph (event → transition → outcome)
  ├─ Gradient Evaluator (online / Optuna-like tuner)
  ├─ Proof Kernel (LTL Invariants + Ontological Checksum)
  └─ Adapters/Bridges
       ├─ EventBridge     (foundation → LLA causal_event)
       ├─ MetricBridge    (foundation → LLA metrics)
       └─ CommandBridge   (LLA → foundation commands)

vFoundation
  ├─ Domain: execution
  ├─ Domain: risk
  └─ Domain: data_provider
```

**Ключові вла� тиво� ті:**

* **Адаптації параметризовані:** змінюємо не код доменів, а параметри гвардів/ваг переходів.
* **Повна тра� овані� ть:** кожний перехід має causal_event, кожне рішення прив’язане до AG.
* **Безпека змін:** LTL-монітор блокує небезпечні оновлення; checksum-gate дає тампер-евіден� .

---

## 3) Дорожня карта (етапи → DoD, ризики та вирішення)

> В� і етапи нижче — **інкрементальні**, з **артефактами** і **командами**, які фік� ують � тан.

### Етап S0. Інфра� труктурний бази�  & Preflight

**Ціль:** “чи� тий � тіл” для дев/CI, одна комбінація Python (3.11) + мінімальні залежно� ті, **warnings-as-errors** (Deprecation/Runtime).

**Кроки:**

* [ ] Перене� ти карка�  LLA у `foundation/meta_fsm/` (без важких залежно� тей: “шим” замі� ть numpy/scipy у юніт-матриці).
* [ ] Заве� ти `adapters/` (event/metric/command), без побічних ефектів.
* [ ] Підготувати `pytest.ini` (asyncio_mode=auto, error::DeprecationWarning/RuntimeWarning).
* [ ] Додати dev-залежно� ті `requirements-dev.txt` (pytest, pytest-asyncio, pyyaml, jsonschema).

**DoD (артефакти):**

* [ ] GREEN unit run: `pytest -q -W error::DeprecationWarning -W error::RuntimeWarning`.
* [ ] `reports/sbom_*`, `reports/cfg_freeze_pre.yaml, .sha256`.
* [ ] `logs/hybrid/preflight_status.json` (overall_pass: true).

**Типові � кладнощі та рішення:**

* **Windows шляхи (`runs/runs\last`)** → � тандартизувати через `pathlib`, жодних конкатенацій рядками.
* **Важкі залежно� ті** → юніт-матриця з “шимами” та lazy-imports.

---

### Етап S1. Bridges v1 (минимальний інтеграційний шар)

**Ціль:** підключити виконані домени до LLA через три мо� ти.

**Кроки:**

* [ ] `adapters/event_bridge.py`: `emit_event(domain, event, payload)` → пише JSONL у `logs/causal_events.jsonl`.
* [ ] `adapters/metric_bridge.py`: `collect_metrics()` → PnL, CVaR, latency, drawdown (з доменів).
* [ ] `adapters/command_bridge.py`: `send_command(domain, command, **params)` → делегує в домени.

**DoD:**

* [ ] Події доменів реально з’являють� я у `logs/causal_events.jsonl` (≥ 50 подій у smoke-прогоні).
* [ ] `collect_metrics()` повертає валідні значення (не `None`, не `nan`).
* [ ] Команди з LLA викликають очікувану реакцію доменів (ідемпотентні� ть + rate-limit).

**Складнощі:**

* **Немає зв’язку або події не пишуть� я:** перевірити дозволи/шляхи/а� инхронні� ть, додати ретраї.
* **Команди небезпечні у LIVE:** додати “shadow” прапорець (логувати замі� ть виконувати).

---

### Етап S2. CA-FSM карка�  (без адаптацій)

**Ціль:** **Meta-FSM** керує по� лідовні� тю дій між доменами; **CA-FSM** зберігає параметри гвардів/ваг; **без** автоматичних оновлень.

**Кроки:**

* [ ] `meta_fsm/ca_fsm.py`: модель � танів, подій і декларативні гварди (yaml).
* [ ] Контур “� по� тереження → перехід → запи�  у causal_events”.
* [ ] Планувальник по� лідовно� тей: за замовчуванням фік� ований (щоб перевірити базовий цикл).

**DoD:**

* [ ] Демон� трація “епізоду” від intent до термінального � тану (open→manage→close).
* [ ] 0 критичних помилок у логах під ча�  � ерії з ≥100 епізодів у sandbox.

**Складнощі:**

* **Не� инхронні� ть � игналів доменів:** у� і call-backs доменів обгорнути у timeouts/guards; логіку “ready” � тандартизувати через � ловники-інтерфей� и.

---

### Етап S3. Axial Gradient (+PnL-центрична) та Gradient Evaluator

**Ціль:** вбудувати **AG** і **оцінювач градієнта** (EMA, Hoeffding-порогування; безпечний безградієнтний тюнер на перший ча� ).

**Кроки:**

* [ ] `ag/axial_gradient.py` з параметрами ваг (pnl, cvar, stability, latency).
* [ ] `ge/evaluator.py`: EMA над епізодами + Hoeffding для n вибірок; **без** зміни \theta на � тарті (тільки облік).
* [ ] Потім увімкнути ди� кретний тюнер: пробні ±δ зміни порогу в одному guard, приймаємо напрям з кращим \bar{AG}.

**DoD:**

* [ ] AG логують� я для кожного епізоду (`logs/ag_eval.jsonl`).
* [ ] Для � табільної � ерії (n≥30) — \bar{AG} має адекватний розподіл (не в� я ма� а в ±∞/NaN).
* [ ] Безпечно увімкнений тюнер: не порушує інваріанти (див. S4).

**Складнощі:**

* **Small-N шум:** не е� калювати до RuntimeWarning; залишити як UserWarning і тримати Hoeffding-фільтр.
* **Дрейф бази:** періодично перераховувати baseline.

---

### Етап S4. Proof Kernel (LTL + Ontological Checksum)

**Ціль:** **ніякої адаптації**, якщо порушують� я інваріанти або не пройдено checksum-gate.

**Кроки:**

* [ ] LTL-монітор (safety/liveness): duplicate_entry, reduce_only, brackets, і т.д.
* [ ] Ontological checksum (некриптографічний фільтр): H(S) = hash(update-tuple) mod P == c.
* [ ] Truth-Score (TS) і gate: freeze адаптацій при TS < τ.

**DoD:**

* [ ] Будь-яке за� то� ування оновлення має запи�  “proof_record” (ok/denied + причина).
* [ ] При порушенні LTL — оновлення не за� то� овуєть� я, CA-FSM лишаєть� я кон� и� тентною.
* [ ] TS-гейтинг вмикає safe-policy при деградації.

**Складнощі:**

* **Хибні позитиви/негативи у LTL:** ізолювати � емантику, те� ти-� ценарії для ядра переходів.

---

### Етап S5. Інтеграція з орке� тратором & DoD-машинка

**Ціль:** приве� ти **DoD-артефакти** у � тандартну форму й залити в CI.

**Кроки:**

* [ ] Скрипти: freeze (`cfg_freeze_*`), SBOM (`sbom_*`), DoD-звіт (R2_DOD_*), acceptance snapshots, strict gate events, GO-flag.
* [ ] Run-ID інжекція у DoD (для тра� ування).
* [ ] Перевірки wirehead-scan (`--fail-on any`), preflight, unit strict.

**DoD (артефакти у `reports/` і `logs/`):**

* [ ] `reports/cfg_freeze_*.yaml/.sha256`, `reports/sbom_*`, `reports/R2_DOD_*.md`.
* [ ] `logs/hybrid/acceptance_summary_*.json`, `logs/hybrid/strict_gate_events.jsonl`.
* [ ] `reports/R2_FULL_PASS_OK_*.flag` з “GO”.

**Складнощі:**

* **Платформені path-баги:** в� е через `pathlib`.
* **Конфіги роз’їжджають� я:** `r2_cfg_guard` + “autofix” профіль.

---

### Етап S6. 72h Shadow (readiness)

**Ціль:** **72 години** без критичних збоїв, з **AG > 0** (на вибраному інтервалі), **TS ≥ τ**, **інваріанти виконують� я**, Acceptance PASS.

**Кроки:**

* [ ] Запу� к в “shadow” режимі: команди **логують� я**, але обмежено виконують� я (лише безпечні).
* [ ] Моніторинг heartbeat/lock, causal_events, ag_eval, proof_record.
* [ ] Періодична генерація acceptance та DoD.

**DoD:**

* [ ] `R2_72H_READY=YES` (вла� ний checker-� крипт, exit 0/1).
* [ ] 0 CRITICAL у журналах; TS не падає нижче τ; LTL-порушення = 0.
* [ ] Acceptance SUMMARY: READY.

**Складнощі:**

* **Перезапу� ки через strict PRE-gate:** дати те� тові дані для CVaR/online, виправити шляхи “runs/last”, зменшити “flaky” контури (timeouts/ретраї).

---

### Етап S7. Staging → Live (керований вихід)

**Ціль:** обмежено включити виконання команд (CommandBridge) → staging; далі — **керований live**.

**Кроки:**

* [ ] Вмикати дію команд по whitelist (safe list) і rate-limit.
* [ ] Snapshots політик щоденно; rollback при деградації SLO.

**DoD:**

* [ ] Staging PASS: � табільний TS і AG, LTL=0, інцидентів=0.
* [ ] Live PASS: контрольоване розширення периметра.

**Складнощі:**

* **О� циляції при агре� ивному тюнері:** адаптивні η_t, обмеження Δ на крок, EMA з більшою інерцією.

---

## 4) Єдина табличка DoD (огляд)

| Етап | Що � аме готово                | Обов’язкові артефакти                                                                                 |
| ---- | ----------------------------- | ----------------------------------------------------------------------------------------------------- |
| S0   | Dev/CI бази� , strict warnings | Unit GREEN, `cfg_freeze_pre.*`, `preflight_status.json`, SBOM                                         |
| S1   | Три мо� ти працюють            | `logs/causal_events.jsonl`, валідні метрики, перевірені команди                                       |
| S2   | CA-FSM без адаптацій          | 100+ епізодів sandbox, 0 критичних помилок                                                            |
| S3   | AG & Evaluator                | `logs/ag_eval.jsonl`, � ерії \bar{AG}, увімкнений тюнер (без LTL порушень)                             |
| S4   | Proof Kernel                  | `logs/proof_record.jsonl`, відхилення небезпечних оновлень                                            |
| S5   | DoD-машинка                   | `reports/R2_DOD_*.md`, `sbom_*`, `acceptance_*`, `strict_gate_events.jsonl`, `R2_FULL_PASS_OK_*.flag` |
| S6   | 72h Shadow                    | `R2_72H_READY=YES`, Acceptance READY                                                                  |
| S7   | Staging/Live                  | TS/AG � табільні, LTL=0, snapshots/rollback                                                            |

---

## 5) Дані та контракти (мінімум для � тарту)

### 5.1. `causal_events.jsonl` (вивід EventBridge)

```json
{"t":"2025-09-10T19:02:01Z","domain":"execution","event":"ORDER_FILLED","from":"OPEN","to":"OPEN","ctx":{"symbol":"BTCUSDT","qty":0.1},"m":{"pnl_delta":0.0032,"latency_ms":52}}
```

### 5.2. Метрики (MetricBridge)

```json
{"pnl": 0.012, "cvar": 0.18, "latency_ms": 47, "drawdown": 0.06}
```

### 5.3. Команди (CommandBridge)

```json
{"domain":"execution","command":"rebalance","params":{"target_risk":0.7}}
```

**Вимоги:** idempotency key, rate-limit, dry-run/shadow прапорець.

---

## 6) Axial Gradient (AG) — � тартова формула

```
AG = w_p * norm(PnL) + w_c * (τ_cvar - norm(CVaR))_+ + w_s * (1 - norm(Stability)) + w_l * (τ_lat - norm(Latency))_+
```

* На � тарті — **PnL-центрична** (w_p найбільше).
* **EMA** поверх епізодів; Hoeffding визначає, чи до� татньо вибірок для зміни \theta.
* Зміна ваг — **через тюнер**, не руками.

---

## 7) CI/CD і репродуктивні� ть

* **Unit (strict):** Deprecation/Runtime → error, pytest-asyncio підключено (без конфіг-warning).
* **Artifacts:** `reports/*`, `logs/hybrid/*` завжди вантажать� я у CI.
* **Freeze/SBOM:** на preflight та при кожному “release candidate”.
* **Run-ID в DoD:** для тра� ування артефактів і acceptance.

---

## 8) Ризики й як їх га� ять

* **Windows path мік� и:** тільки `pathlib`, у те� тах — контрольовані root/env.
* **Heavy deps:** у unit — шими/lazy; у інтеграції — реальні пакети.
* **“Гойдання” політик:** η_t зменшуєть� я, крок обмежений, оновлення не ча� тіше K/год.
* **Хибна каузальні� ть:** те� т-A/B, ін� трументальні змінні, регуляризація.

---

## 9) План міграції (рекомендований)

1. **База в B (про� тий vFoundation):** S0→S4 (Bridges, CA-FSM, AG, Proof Kernel).
2. **72h Shadow у B:** S5→S6 (DoD, acceptance, готовні� ть).
3. **Перене� ення карка� у в A:** заміна локальних glue на � тандартні bridges; reuse Proof Kernel; � тягування DoD.
4. **Стейджинг у A → Live:** з тим же checklist.

---

## 10) Команди (кори� ні підказки)

```bash
# Unit strict (локально)
pytest -q -W error::DeprecationWarning -W error::RuntimeWarning --maxfail=1

# Префлайт
python tools/r2_hybrid_stage.py start --ensure-cfg --mode ab --out logs/hybrid/preflight_status.json

# DoD / Freeze / SBOM / Acceptance (де це є у проєкті)
python tools/r2_cfg_freeze.py --config cfg/r2.yaml --out reports/cfg_freeze_pre.yaml --hash-out reports/cfg_freeze_pre.sha256
python tools/r2_sbom.py --out-dir reports/
python tools/r2_dod_report.py --out reports/R2_DOD_$(date -u +%Y%m%dT%H%M%SZ).md

# Wirehead scan
python tools/wirehead_scan.py --fail-on any

# Readiness checker (вла� ний)
python tools/r2_readiness_check.py   # друкує R2_72H_READY=YES/NO і віддає 0/1
```

---

## 11) Готовні� ть до 72h (Definition of Ready)

* [ ] S0–S5 DoD виконані; acceptance READY; strict gates PASS.
* [ ] Proof Kernel блокує небезпечні адаптації; checksum-gate увімкнено.
* [ ] Моніторинг heartbeat/lock; ротація логів; алерти на CRITICAL.
* **Формула:** коли `r2_readiness_check.py` → `R2_72H_READY=YES` **та** acceptance READY, дозволено � тарт.

---

## 12) Що автоматизуємо Copilot’ом першими (операційний � пи� ок)

1. Створити `foundation/meta_fsm/adapters/{event,metric,command}_bridge.py` (� келети з вище).
2. Додати виклики `emit_event()` у ключові точки доменів (execution/risk/data_provider).
3. По� тавити `axial_gradient.py` і `evaluator.py` (EMA + Hoeffding; без оновлень \theta перші 1–2 дні).
4. Впровадити `ca_fsm.py` з yaml-конфігом гвардів/ваг, **без** адаптацій (тільки запи� ).
5. Додати Proof Kernel: мінімальний LTL-набір + checksum-gate; логувати `proof_record.jsonl`.
6. Налаштувати � крипти DoD/Freeze/SBOM/Acceptance, додати run_id у DoD.
7. Прове� ти **72h shadow** (Сhecker: `R2_72H_READY=YES`).
8. Перене� ти карка�  у � кладніший репозиторій A.

---

## 13) Ви� новок

* **Мо� ти** роблять домени “видимими” для LLA.
* **CA-FSM** надає пла� тичні� ть поведінки без хао� у — адаптуємо **параметри** під контролем інваріантів.
* **Proof Kernel** гарантує кон� и� тентні� ть; **DoD-машинка** — відтворювані� ть і тра� овні� ть.
* **72h Shadow** — наша лінія оборони перед staging/live.





---

# План запу� ку LLA ⇆ vFoundation в Olimp_v1 (до “72h READY”)

## 0) Стратегія інтеграції (рішення)

* **Цільовий репозиторій:** той, що “про� тішій”, але **вже працює на testnet** і побудований на vFoundation (домени вже виділені). Це да� ть найшвидший практичний результат.
* **Підхід:** перено� имо лише **потрібні вузли LLA** (орке� трація/гейти/шари) і одразу обгортаємо в � труктуру vFoundation. В� е інше допи� уємо легкими адаптерами.
* **О� нова управління:** LLA ви� тупає як **Meta-FSM / CA-FSM**, “мозок над доменами” (execution, risk, data_provider). Ве� ь рух іде через Bridges.

---

## 1) Sprint A — Bridges (нервова � и� тема)

### Створити � труктуру

```
foundation/
  adapters/
    event_bridge.py
    metric_bridge.py
    command_bridge.py
  meta_fsm/
    ca_fsm.py            # поки мінімальний карка� 
  system/
    paths.py             # якщо нема — централізуємо тут
logs/
  causal_events.jsonl
  ag_eval.jsonl
  proof_record.jsonl
```

### Контракти (мінімум)

**event_bridge.py**

```python
from pathlib import Path
import json, time

LOG = Path("logs/causal_events.jsonl")

def emit_event(domain: str, event: str, payload: dict):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {"t": time.time(), "domain": domain, "event": event, "payload": payload}
    LOG.write_text(LOG.read_text() + json.dumps(rec) + "\n" if LOG.exists() else json.dumps(rec) + "\n")
```

**metric_bridge.py**

```python
def collect_metrics():
    # TODO: підключити до ваших доменів
    # Повертаємо PnL/CVaR/latency/volatility хоча б у “� таб”-вигляді
    return {"pnl_delta": 0.0, "cvar": 0.0, "latency_ms": 0, "volatility_ratio": 0.0}
```

**command_bridge.py**

```python
ALLOW = {"execution": {"place_order","cancel_all"}, "risk": {"rebalance"}, "data_provider": {"refresh"}}

def send_command(domain: str, command: str, **params):
    if command not in ALLOW.get(domain, {}):
        return {"ok": False, "err": "denied"}
    # TODO: виклик вашого домену (фа� ад/порт)
    return {"ok": True, "info": {"domain": domain, "command": command, "params": params}}
```

### Ін� трументування доменів

* У ключових точках `execution`, `risk`, `data_provider` викликаємо `emit_event(...)` (пі� ля обробки � игналів, перед/пі� ля ключових дій).
* Легкий smoke-луп на 100+ подій (sandbox/testrun).

### Команди

```bash
pytest -q -k "not integration" -W error::DeprecationWarning -W error::RuntimeWarning --maxfail=1
python - <<'PY'
from foundation.adapters.event_bridge import emit_event
for i in range(120):
    emit_event("risk","MARKET_DATA_UPDATE",{"i": i})
print("events logged")
PY
```

### DoD (A)

* `logs/causal_events.jsonl` мі� тить ≥ 50 запи� ів, формат валідний.
* Unit strict — зелено.

---

## 2) Sprint B — CA-FSM (карка� , без адаптацій)

**meta_fsm/ca_fsm.py**

```python
from dataclasses import dataclass
from foundation.adapters.event_bridge import emit_event
from foundation.adapters.metric_bridge import collect_metrics
from foundation.adapters.command_bridge import send_command

@dataclass
class Transition:
    from_state: str
    event: str
    to_state: str
    guard: str     # вираз у � тилі "signal_confidence > 0.7"
    weight: float  # початкова вага

class CAFSM:
    def __init__(self, transitions, start="IDLE"):
        self.s = start
        self.transitions = transitions

    def step(self, event:str, ctx:dict):
        cand = [t for t in self.transitions if t.from_state==self.s and t.event==event]
        if not cand: return self.s
        t = max(cand, key=lambda x: x.weight)  # поки про� тий вибір
        # TODO: оцінка guard із ctx (безпечний eval/інтерпретатор)
        self.s = t.to_state
        emit_event("meta_fsm","transition",{"from": t.from_state,"event": event,"to": t.to_state})
        return self.s

    def on_tick(self):
        m = collect_metrics()
        emit_event("meta_fsm","metrics",m)
        # поки не оновлюємо параметри
```

**config/ca_fsm.yaml** (приклад)

```yaml
transitions:
  - { from: IDLE, event: START, to: SCAN, guard: "True", weight: 0.8 }
  - { from: SCAN, event: SIGNAL, to: RISK_CHECK, guard: "signal_confidence > 0.7", weight: 0.8 }
  - { from: RISK_CHECK, event: PASS, to: EXECUTE, guard: "risk_score < 0.5", weight: 0.7 }
  - { from: EXECUTE, event: DONE, to: IDLE, guard: "True", weight: 1.0 }
```

**Вбудування у ваш `run_r0.py` / головний цикл:**

* Ініціалізуємо `CAFSM` зі � тартового � тану.
* На кожній події від доменів — викликаємо `fsm.step(event, ctx)`.
* На timer/heartbeat — `fsm.on_tick()`.

### DoD (B)

* FSM “ходить” по мінімальному � ценарію (IDLE→SCAN→RISK_CHECK→EXECUTE→IDLE), події пишуть� я у `causal_events.jsonl`.
* Немає падінь/блокувань.

---

## 3) Sprint C — Axial Gradient (PnL-центричний) + Evaluator (без оновлень)

**ag/axial_gradient.py**

```python
def axial_gradient(m):
    pnl_term = 0.7 * m.get('pnl_delta', 0.0)
    cvar_term = 0.2 * (0.05 - m.get('cvar', 0.0))
    stab_term = 0.1 * (1.0 - m.get('volatility_ratio', 0.0))
    return pnl_term + cvar_term + stab_term
```

**ge/evaluator.py**

```python
from foundation.adapters.metric_bridge import collect_metrics
from foundation.ag.axial_gradient import axial_gradient
from pathlib import Path, PurePath
import json, time

LOG = Path("logs/ag_eval.jsonl")

def eval_once():
    m = collect_metrics()
    ag = axial_gradient(m)
    rec = {"t": time.time(), "metrics": m, "ag": ag}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(LOG.read_text() + json.dumps(rec) + "\n" if LOG.exists() else json.dumps(rec) + "\n")
    return ag
```

Викликати `eval_once()` у таймері FSM.

### DoD (C)

* `logs/ag_eval.jsonl` має запи� и; **ag** не NaN/inf; розподіл реалі� тичний (може бути ~0 на � тарті).
* Unit strict — зелено.

---

## 4) Sprint D — Proof Kernel (LTL мінімум + checksum-gate)

**proof_kernel/ltl_invariants.yaml** (мінімальний � тарт)

```yaml
safety:
  - "G ! duplicate_entry"     # ніколи не подвійний submit
  - "G (OPEN -> F BRACKETS)"  # якщо відкрили — мають з’явити� ь брекети
```

**proof_kernel/ltl_shield.py** — про� тий монітор (легкі правила, унітарні перевірки тра� ), плю� :
**proof_kernel/ontological_checksum.py**

```python
def checksum_ok(proposal: dict, P=97, c=4):
    s = json_dumps_canon(proposal)  # канонізувати ключі/рядки
    return (hash(s) % P) == c
```

Підключити перед будь-яким “apply_guard_update”.

### DoD (D)

* Порушення safety те� том → “denied” у `proof_record.jsonl`.
* Коректні оновлення (коли з’являть� я) → “accepted”.

---

## 5) Sprint E — Підмішати LLA вузли (мінімально необхідне)

Перено� имо **тільки** те, що реально дає цінні� ть зараз:

* `tools/r2_hybrid_stage.py`, `tools/r2_readiness_check.py`, `tools/r2_cfg_freeze.py`, `tools/r2_sbom.py`, `tools/r2_dod_report.py`, `tools/r2_full_pass_gate.py`, `tools/r2_all_gates.py`, `tools/r2_cfg_guard.py`, `tools/cfg_patch_defaults.json`.
* `living_latent/r2/hybrid/ltl_shield.py` → як надбудова над нашим мінімальним PK (якщо хочеш); або залишаємо наш мін PK на перших 2 � принти.
* (Опційно, пізніше) `pipeline.py`, `conf_gate.py`, `dro_gate.py` — **тільки** якщо потрібен їхній функціонал і ми готові до шима важких залежно� тей.

Правило: **жодних hard-deps** у unit-циклі. В� е важке — за флагами/маркером `@pytest.mark.integration` і через шими/lazy-imports (як ми робили раніше).

### DoD (E)

* Префлайт з `tools/r2_hybrid_stage.py` → **OK**, артефакти на мі� ці.
* Readiness check → `R2_72H_READY=YES`.

---

## 6) Sprint F — CI/Unit “strict” (� табільний baseline)

* Додаємо workflow з **strict warnings** і `pytest-asyncio` у матриці (ubuntu/windows × 3.10/3.11).
* Артефакти: `UNIT_TEST_LOG.txt`, freeze, sbom, DoD.

### DoD (F)

* Unit матриця **GREEN**; артефакти в Actions.

---

## 7) Sprint G — 72h Shadow

* Запу� к у **shadow-режимі** (команди в лог, без реальних side-effects).
* Моніторимо heartbeat/lock, causal_events, ag_eval, proof_record; генеруємо acceptance/DoD за розкладом.

### Команди (приклад)

```bash
python tools/r2_hybrid_stage.py start --ensure-cfg --mode ab --out logs/hybrid/preflight_status.json
python tools/r2_readiness_check.py   # очікуємо R2_72H_READY=YES
# далі — запу� к shadow-цикла (ваш runner), лог у logs/hybrid/run_stdout.log
```

### DoD (G)

* `R2_72H_READY=YES`, Acceptance READY, 0 CRITICAL, LTL-порушень немає.

---

## Ризики та як закривати

* **Windows пути/“runs\runs/last”** → тільки `pathlib` у `foundation/system/paths.py`; окремі те� ти на це (ми їх додамо).
* **Флаки PRE-гейтів** (порожні метрики CVaR/obs) → у shadow � творюємо мінімальні “� напшоти”/� урогатні метрики, щоб PRE не падав від пу� того входу.
* **О� циляції при тюнері** → поки **вимкнуто**; � початку збираємо причинний � лід і AG, лише потім вмикаємо на одному порозі з Hoeffding-порогами.
* **Важкі залежно� ті** → геть із unit; в� е важке — за інтеграційним маркером + шим.

---

## Що отримаємо пі� ля Sprint G

* LLA керує **Meta-FSM / CA-FSM** поверх ваших доменів.
* Є **причинний � лід** (causal_events), **AG-оцінка** і **Proof Kernel** (мінімум safety).
* CI green, базові релізні артефакти, і **� и� тема готова до 72h shadow**.

---

## Фінальне: команда для “72h готові до запу� ку”

Пі� ля того як пройдеш Sprints A–F і `python tools/r2_readiness_check.py` видрукує `R2_72H_READY=YES`, запу� к shadow-циклу (у вашому раннері) вважаємо � тартом “72 годин”.

---



---

# ВАРІАНТ A — “візьми готові файли з LLA” (мінімальний порт)

Оце те, що **до� татньо перене� ти** з LLA в твій проєкт, щоб LLA-шар накрив твій r0-орке� тратор і ми запу� тили CA-FSM + 72h Shadow:

1. **tools/**

* `r2_hybrid_stage.py` — запу� к/орке� тратор � тадій (preflight, shadow, acceptance).
* `r2_readiness_check.py` — інтегрований чекер, який дає однозначний прапор `R2_72H_READY=YES/NO`.
* `r2_cfg_guard.py` + `cfg_patch_defaults.json` — автопатч і валідація `cfg/r2.yaml`.
* `r2_cfg_freeze.py` — freeze конфігів (yaml + sha256).
* `r2_sbom.py` — SBOM/інвентар залежно� тей.
* `r2_all_gates.py`, `r2_full_pass_gate.py`, `r2_dod_report.py` — � трогі гейти, рішення “GO/NO-GO”, DoD-звіт.

2. **foundation/hybrid/**

* `stage_orchestrator.py` — цикл � тадій + таймінги + артефакти.
* `pi_bridge.py` — ліміт/бюджет рішень (policy interface, rate/latency бюджети).
* `rate_limit.py` — токен-бакет/дро� ель для змін.
* `conf_gate.py`, `dro_gate.py` — конфігураційні/роба� тні гейти (детектують небезпечні зміни).

3. **foundation/proof_kernel/**

* `ltl_shield.py` — LTL-монітор і checksum-gate (блокування “небезпечних” оновлень).

4. **foundation/system/**

* `paths.py` — єдиний нормалізатор шляхів (Windows-safe), щоб прибрати `runs\runs/last` і подібні фейли.

5. **cfg/**

* `r2.yaml` — базова конфігурація � тадій/гейтів (відразу пі� ля копіювання проганяєш `r2_cfg_guard.py --autofix`).

6. **foundation/hybrid/r0_adapter.py** *(новий у твоєму репо)*
   тонкий адаптер, що � тартує твій `r0_*.py` через 3 гачки: `r0_on_start/step/stop`.

> **Примітка:** назви каталогів `foundation/*` можеш перейменувати під � вою � труктуру (наприклад `vfoundation/*`). Головне — зберегти функціональні ролі.

---

# ВАРІАНТ B — “що ці файли мають робити” (якщо пишеш � вої, без копіювання)

Нижче — **обов’язкові модулі та їхня роль**. Можеш назвати їх як завгодно; важливо, щоб виконували ці задачі.

### 1) Орке� тратор � тадій

* **Що робить:** запу� кає префлайт → тіньовий режим → acceptance → freeze/SBOM → DoD.
* **API:** `start(mode: str, out: Path)`, `simulate(ticks: int)`.
* **DoD:** � творює `logs/hybrid/preflight_status.json`, `acceptance_summary_*.json`, `strict_gate_events.jsonl`.

### 2) Readiness-checker

* **Що робить:** читає артефакти та друкує однозначно `R2_72H_READY=YES/NO` (exit-code 0/1).
* **Вхід:** `preflight_status.json`, `acceptance_summary_*.json`, freeze/sha, SBOM.
* **DoD:** одна команда дає відповідь; інтегруєть� я в CI.

### 3) Config-guard (+ автопатч)

* **Що робить:** валідатор/автопоповнювач `cfg/r2.yaml` (додає � екцію `hybrid.*`, дефолти, ча� ові вікна).
* **DoD:** пі� ля запу� ку — завжди валідний `r2.yaml` без ручного редагування.

### 4) Freeze/SBOM/DoD-репортери

* **Що роблять:**
  freeze — зберігає snapshot конфіга + sha256;
  sbom — знімає залежно� ті;
  dod — робить короткий звіт “що виконано і чому GO/NO-GO”.
* **DoD:** наявні файли у `reports/` (`cfg_freeze_*.yaml/.sha256`, `sbom_*`, `R2_DOD_*.md`).

### 5) Stage-orchestrator core

* **Що робить:** цикл � тадій (S0…Sn), таймери, heartbeat, file-locks, state-машина, логіка повторних � проб.
* **DoD:** `logs/hybrid/.heartbeat`, `stage_state.json`, коректне відновлення пі� ля ре� тарту.

### 6) R0-adapter (двигун)

* **Що робить:** запу� кає твій `r0_*.py` як під� и� тему через 3 гачки:

  * `r0_on_start(ctx)`, `r0_on_step(ctx)`, `r0_on_stop(ctx)`
* **DoD:** один `step()` = один «тік» � и� теми; енджін не падає при помилці домену (ізолює винятки).

### 7) Bridges (твоя “ізюмінка”)

* **event_bridge:** пише **causal events** у `logs/causal_events.jsonl`
  `emit_event(domain, event, payload)`
* **metric_bridge:** збирає PnL/CVaR/latency з доменів
  `collect_metrics() -> dict`
* **command_bridge:** безпечне виконання команд у домени (whitelist + rate-limit)
  `send_command(domain, command, args) -> Result`
* **DoD:** є ≥50 `causal_events` за smoke-� е� ію; latency/CVaR не нулі.

### 8) Proof-kernel

* **Що робить:** LTL-монітор + checksum-gate для блокування небезпечних переходів/апдейтів.
* **API:** `ltl_accepts(trace|proposal) -> bool`, `checksum_ok(proposal) -> bool`.
* **DoD:** при порушенні — подія блокуєть� я; `logs/proof_record.jsonl` мі� тить причину.

### 9) Policy-interface (PI-bridge)

* **Що робить:** єдиний інтерфей�  керування політикою/порогами з rate-limit/latency-budget.
* **API:** `should_accept_candidate(key, delta, cost, clock) -> (bool, info)`.
* **DoD:** ча� тота змін і бюджет не порушують� я; логи `policy_updates.jsonl`.

### 10) Rate-limit

* **Що робить:** токен-бакет, що дро� елить зміни параметрів та ча� тоту команд.
* **DoD:** ніколи не перевищує K оновлень/год; метрики в логах.

### 11) CA-FSM (Meta-FSM над доменами)

* **Що робить:** вирішує, у якому порядку викликати домени (`execution`, `risk`, `data_provider`) і які дії робити; � початку політика фік� ована.
* **API:** `tick(obs)`, `transition(state, event) -> (next_state, action)`.
* **DoD:** smoke 100–500 тікiв без падінь; `causal_events.jsonl` наповнюєть� я.

### 12) Axial-gradient + адаптації (мінімально)

* **Що робить:** перетворює метрики у � калярний AG (PnL-центричний) + легкі зміни порогів раз на K кроків (**тільки** якщо Proof-kernel дозволив).
* **DoD:** `ag_eval.jsonl` заповнюєть� я; зміни рідкі, маленькі, без о� циляцій.

### 13) Paths helper

* **Що робить:** нормалізує в� і шляхи (о� обливо на Windows): `get_logs_dir()`, `get_runs_dir()`, `ensure_dir()`.
* **DoD:** жодних `runs/runs\last`; в� е під єдиним коренем.

### 14) Config (`cfg/r2.yaml`)

* **Що робить:** опи� ує � тадії, бюджети, ча� тоти, точки інтеграції.
* **DoD:** валідний пі� ля guard-� крипта; орке� тратор не про� ить ручних правок.

---

## Щоб � тартувати про� то зараз

1. **У r0** додай гачки:

```python
def r0_on_start(ctx): ...
def r0_on_step(ctx):  ...
def r0_on_stop(ctx):  ...
```

2. **Створи** адаптер і бриджі (навіть зі � тубами метрик):

```python
from foundation.hybrid.r0_adapter import R0Engine
e = R0Engine('r0_main'); e.start(); e.step(); e.stop()
```

3. **Або** � копіюй файли з Варіанта A, далі:

```bash
python tools/r2_cfg_guard.py cfg/r2.yaml --autofix --patch-file tools/cfg_patch_defaults.json
python tools/r2_hybrid_stage.py start --ensure-cfg --mode ab --out logs/hybrid/preflight_status.json
python tools/r2_readiness_check.py   # має виве� ти R2_72H_READY=YES (коли в� е на мі� ці)
```


