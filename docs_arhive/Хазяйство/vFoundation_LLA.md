# vFoundation     LLA Transition Roadmap (CA-FSM, Bridges, Proof Kernel)     v1.0

> **                           :**                    ,                                                                                                 vFoundation-CA    LLA                                (Meta-FSM     CA-FSM                 ).
>                      :         ,                            , Definition of Done (DoD)                                 ,                          /                                                            ,                   ,                           -                             .

---

## 0)                               

1. **LLA                                   :** LLA            **Meta-FSM/CA-FSM**,                                                     (execution, risk, data_provider),                                                                             ,                            /                           .
2. **Causal Adaptation:**                         FSM            **                           **                         **Axial Gradient** (AG),                                             **+PnL** (                    CVaR/                      /                        ).
3. **Bridges                                   :**                      **EventBridge / MetricBridge / CommandBridge**                                               vFoundation    LLA.
4. **Proof Kernel + LTL                     :**                                      ,                                                                                    /                  .
5. **72h Shadow readiness:**                         72                                                                                  , acceptance-              , freeze/SBOM    GO-            .

---

## 1)                                   (                                                     )

* **                       A (                    , R2Hybrid            PASS):**                        /CI,                        vFoundation;    R2Hybrid                       , DoD, strict gates.
* **                       B (                  ,                vFoundation):**              (execution, risk, data_provider)   ,                                           ,                 /            , **                                                              **;                                                                        LLA      Meta-FSM/CA-FSM                                                  .

**                                     :**
                **B (                     vFoundation)**                                                                 **            **                CA-FSM + Bridges + Proof Kernel                   **72h readiness**.                                                                                                  A (R2Hybrid).

---

## 2)                                      

```
LLA (Meta-FSM/CA-FSM)
         Axial Gradient (AG) [+PnL, -CVaR, +Stability, -Latency]
         Causal Graph (event     transition     outcome)
         Gradient Evaluator (online / Optuna-like tuner)
         Proof Kernel (LTL Invariants + Ontological Checksum)
         Adapters/Bridges
              EventBridge     (foundation     LLA causal_event)
              MetricBridge    (foundation     LLA metrics)
              CommandBridge   (LLA     foundation commands)

vFoundation
         Domain: execution
         Domain: risk
         Domain: data_provider
```

**                                     :**

* **                                                 :**                                            ,                                     /                         .
* **                                   :**                                    causal_event,                                                      AG.
* **                       :** LTL-                                                                   ; checksum-gate                    -              .

---

## 3)                           (               DoD,                                     )

>                                  **                            **,    **                      **    **                  **,                                 .

###          S0.                                             & Preflight

**        :**                                          /CI,                               Python (3.11) +                                          , **warnings-as-errors** (Deprecation/Runtime).

**          :**

* [ ]                                 LLA    `foundation/meta_fsm/` (                                          :                             numpy/scipy            -              ).
* [ ]                `adapters/` (event/metric/command),                                       .
* [ ]                        `pytest.ini` (asyncio_mode=auto, error::DeprecationWarning/RuntimeWarning).
* [ ]              dev-                     `requirements-dev.txt` (pytest, pytest-asyncio, pyyaml, jsonschema).

**DoD (                  ):**

* [ ] GREEN unit run: `pytest -q -W error::DeprecationWarning -W error::RuntimeWarning`.
* [ ] `reports/sbom_*`, `reports/cfg_freeze_pre.yaml, .sha256`.
* [ ] `logs/hybrid/preflight_status.json` (overall_pass: true).

**                                                   :**

* **Windows            (`runs/runs\last`)**                                               `pathlib`,                                                     .
* **                               **             -                                          lazy-imports.

---

###          S1. Bridges v1 (                                                        )

**        :**                                                         LLA                             .

**          :**

* [ ] `adapters/event_bridge.py`: `emit_event(domain, event, payload)`              JSONL    `logs/causal_events.jsonl`.
* [ ] `adapters/metric_bridge.py`: `collect_metrics()`     PnL, CVaR, latency, drawdown (                 ).
* [ ] `adapters/command_bridge.py`: `send_command(domain, command, **params)`                                   .

**DoD:**

* [ ]                                                                     `logs/causal_events.jsonl` (    50               smoke-              ).
* [ ] `collect_metrics()`                                                  (     `None`,      `nan`).
* [ ]                   LLA                                                                       (                               + rate-limit).

**                  :**

* **                                                                  :**                                    /          /                          ,                          .
* **                                       LIVE:**                 shadow                       (                                                    ).

---

###          S2. CA-FSM              (                         )

**        :** **Meta-FSM**                                                                     ; **CA-FSM**                                                   /      ; **      **                                          .

**          :**

* [ ] `meta_fsm/ca_fsm.py`:                          ,                                                     (yaml).
* [ ]                                                                                 causal_events   .
* [ ]                                                      :                                                      (                                                   ).

**DoD:**

* [ ]                                                      intent                                            (open   manage   close).
* [ ] 0                                                                                100                     sandbox.

**                  :**

* **                                                            :**        call-backs                                      timeouts/guards;                 ready                                                              -                    .

---

###          S3. Axial Gradient (+PnL-                  )      Gradient Evaluator

**        :**                    **AG**    **                                   ** (EMA, Hoeffding-                      ;                                                                                    ).

**          :**

* [ ] `ag/axial_gradient.py`                                  (pnl, cvar, stability, latency).
* [ ] `ge/evaluator.py`: EMA                           + Hoeffding        n               ; **      **            \theta                   (                       ).
* [ ]                                                              :                                                           guard,                                                 \bar{AG}.

**DoD:**

* [ ] AG                                                         (`logs/ag_eval.jsonl`).
* [ ]                                        (n   30)     \bar{AG}                                              (                             /NaN).
* [ ]                                                 :                                          (      . S4).

**                  :**

* **Small-N       :**                                RuntimeWarning;                       UserWarning                   Hoeffding-            .
* **                   :**                                                   baseline.

---

###          S4. Proof Kernel (LTL + Ontological Checksum)

**        :** **                               **,                                                                                   checksum-gate.

**          :**

* [ ] LTL-               (safety/liveness): duplicate_entry, reduce_only, brackets,      .  .
* [ ] Ontological checksum (                                               ): H(S) = hash(update-tuple) mod P == c.
* [ ] Truth-Score (TS)    gate: freeze                           TS <   .

**DoD:**

* [ ]         -                                                                        proof_record    (ok/denied +               ).
* [ ]                           LTL                                                         , CA-FSM                                              .
* [ ] TS-                            safe-policy                            .

**                  :**

* **                           /                    LTL:**                                      ,           -                                                   .

---

###          S5.                                                    & DoD-              

**        :**                  **DoD-                  **                                                       CI.

**          :**

* [ ]               : freeze (`cfg_freeze_*`), SBOM (`sbom_*`), DoD-         (R2_DOD_*), acceptance snapshots, strict gate events, GO-flag.
* [ ] Run-ID                     DoD (                           ).
* [ ]                    wirehead-scan (`--fail-on any`), preflight, unit strict.

**DoD (                      `reports/`    `logs/`):**

* [ ] `reports/cfg_freeze_*.yaml/.sha256`, `reports/sbom_*`, `reports/R2_DOD_*.md`.
* [ ] `logs/hybrid/acceptance_summary_*.json`, `logs/hybrid/strict_gate_events.jsonl`.
* [ ] `reports/R2_FULL_PASS_OK_*.flag`       GO   .

**                  :**

* **                       path-        :**                   `pathlib`.
* **                                            :** `r2_cfg_guard` +    autofix                  .

---

###          S6. 72h Shadow (readiness)

**        :** **72             **                                     ,    **AG > 0** (                                          ), **TS       **, **                                           **, Acceptance PASS.

**          :**

* [ ]                    shadow                :                **                  **,                                                (                         ).
* [ ]                      heartbeat/lock, causal_events, ag_eval, proof_record.
* [ ]                                         acceptance      DoD.

**DoD:**

* [ ] `R2_72H_READY=YES` (               checker-            , exit 0/1).
* [ ] 0 CRITICAL                    ; TS                              ; LTL-                   = 0.
* [ ] Acceptance SUMMARY: READY.

**                  :**

* **                                  strict PRE-gate:**                                         CVaR/online,                                  runs/last   ,                     flaky                   (timeouts/            ).

---

###          S7. Staging     Live (                             )

**        :**                                                                   (CommandBridge)     staging;              **                   live**.

**          :**

* [ ]                                         whitelist (safe list)    rate-limit.
* [ ] Snapshots                              ; rollback                             SLO.

**DoD:**

* [ ] Staging PASS:                      TS    AG, LTL=0,                     =0.
* [ ] Live PASS:                                                                   .

**                  :**

* **                                                             :**                      _t,                                    , EMA                                   .

---

## 4)                             DoD (          )

|          |                                           |                                                                                                                            |
| ---- | ----------------------------- | ----------------------------------------------------------------------------------------------------- |
| S0   | Dev/CI           , strict warnings | Unit GREEN, `cfg_freeze_pre.*`, `preflight_status.json`, SBOM                                         |
| S1   |                                               | `logs/causal_events.jsonl`,                              ,                                                                           |
| S2   | CA-FSM                                    | 100+                  sandbox, 0                                                                                              |
| S3   | AG & Evaluator                | `logs/ag_eval.jsonl`,            \bar{AG},                                 (       LTL                 )                             |
| S4   | Proof Kernel                  | `logs/proof_record.jsonl`,                                                                                                         |
| S5   | DoD-                                 | `reports/R2_DOD_*.md`, `sbom_*`, `acceptance_*`, `strict_gate_events.jsonl`, `R2_FULL_PASS_OK_*.flag` |
| S6   | 72h Shadow                    | `R2_72H_READY=YES`, Acceptance READY                                                                  |
| S7   | Staging/Live                  | TS/AG                   , LTL=0, snapshots/rollback                                                            |

---

## 5)                                  (                                  )

### 5.1. `causal_events.jsonl` (           EventBridge)

```json
{"t":"2025-09-10T19:02:01Z","domain":"execution","event":"ORDER_FILLED","from":"OPEN","to":"OPEN","ctx":{"symbol":"BTCUSDT","qty":0.1},"m":{"pnl_delta":0.0032,"latency_ms":52}}
```

### 5.2.                (MetricBridge)

```json
{"pnl": 0.012, "cvar": 0.18, "latency_ms": 47, "drawdown": 0.06}
```

### 5.3.                (CommandBridge)

```json
{"domain":"execution","command":"rebalance","params":{"target_risk":0.7}}
```

**            :** idempotency key, rate-limit, dry-run/shadow                   .

---

## 6) Axial Gradient (AG)                                    

```
AG = w_p * norm(PnL) + w_c * (  _cvar - norm(CVaR))_+ + w_s * (1 - norm(Stability)) + w_l * (  _lat - norm(Latency))_+
```

*                       **PnL-                  ** (w_p                   ).
* **EMA**                              ; Hoeffding                 ,                                                          \theta.
*                       **                     **,                  .

---

## 7) CI/CD                                    

* **Unit (strict):** Deprecation/Runtime     error, pytest-asyncio                      (                   -warning).
* **Artifacts:** `reports/*`, `logs/hybrid/*`                                        CI.
* **Freeze/SBOM:**      preflight                               release candidate   .
* **Run-ID    DoD:**                                                     acceptance.

---

## 8)                                       

* **Windows path           :**              `pathlib`,                                                root/env.
* **Heavy deps:**    unit             /lazy;                                                        .
* **                                     :**   _t                       ,                            ,                                        K/      .
* **                                   :**         -A/B,                                            ,                           .

---

## 9)                           (                            )

1. **            B (               vFoundation):** S0   S4 (Bridges, CA-FSM, AG, Proof Kernel).
2. **72h Shadow    B:** S5   S6 (DoD, acceptance,                     ).
3. **                                         A:**                                 glue                           bridges; reuse Proof Kernel;                      DoD.
4. **                      A     Live:**                checklist.

---

## 10)                (                               )

```bash
# Unit strict (                )
pytest -q -W error::DeprecationWarning -W error::RuntimeWarning --maxfail=1

#                 
python tools/r2_hybrid_stage.py start --ensure-cfg --mode ab --out logs/hybrid/preflight_status.json

# DoD / Freeze / SBOM / Acceptance (                              )
python tools/r2_cfg_freeze.py --config cfg/r2.yaml --out reports/cfg_freeze_pre.yaml --hash-out reports/cfg_freeze_pre.sha256
python tools/r2_sbom.py --out-dir reports/
python tools/r2_dod_report.py --out reports/R2_DOD_$(date -u +%Y%m%dT%H%M%SZ).md

# Wirehead scan
python tools/wirehead_scan.py --fail-on any

# Readiness checker (              )
python tools/r2_readiness_check.py   #              R2_72H_READY=YES/NO                 0/1
```

---

## 11)                           72h (Definition of Ready)

* [ ] S0   S5 DoD                 ; acceptance READY; strict gates PASS.
* [ ] Proof Kernel                                                     ; checksum-gate                   .
* [ ]                      heartbeat/lock;                          ;                   CRITICAL.
* **              :**          `r2_readiness_check.py`     `R2_72H_READY=YES` **    ** acceptance READY,                              .

---

## 12)                                 Copilot                       (                                   )

1.                  `foundation/meta_fsm/adapters/{event,metric,command}_bridge.py` (                          ).
2.                             `emit_event()`                                             (execution/risk/data_provider).
3.                    `axial_gradient.py`    `evaluator.py` (EMA + Hoeffding;                         \theta            1   2       ).
4.                      `ca_fsm.py`    yaml-                               /      , **      **                    (                       ).
5.              Proof Kernel:                        LTL-           + checksum-gate;                  `proof_record.jsonl`.
6.                                       DoD/Freeze/SBOM/Acceptance,              run_id    DoD.
7.                  **72h shadow** (  hecker: `R2_72H_READY=YES`).
8.                                                                                A.

---

## 13)                 

* **          **                                                           LLA.
* **CA-FSM**                                                                                                 **                  **                                                 .
* **Proof Kernel**                                                ; **DoD-              **                                                             .
* **72h Shadow**                                                   staging/live.





---

#                         LLA     vFoundation    Olimp_v1 (        72h READY   )

## 0)                                         (              )

* **                                       :**       ,                              ,        **                         testnet**                                vFoundation (                                    ).                                                                             .
* **            :**                               **                            LLA** (                      /          /        )                                                            vFoundation.                                                                       .
* **                                 :** LLA                       **Meta-FSM / CA-FSM**,                                          (execution, risk, data_provider).                                   Bridges.

---

## 1) Sprint A     Bridges (                             )

###                                    

```
foundation/
  adapters/
    event_bridge.py
    metric_bridge.py
    command_bridge.py
  meta_fsm/
    ca_fsm.py            #                                             
  system/
    paths.py             #                                                        
logs/
  causal_events.jsonl
  ag_eval.jsonl
  proof_record.jsonl
```

###                    (              )

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
    # TODO:                                                    
    #                      PnL/CVaR/latency/volatility                              -              
    return {"pnl_delta": 0.0, "cvar": 0.0, "latency_ms": 0, "volatility_ratio": 0.0}
```

**command_bridge.py**

```python
ALLOW = {"execution": {"place_order","cancel_all"}, "risk": {"rebalance"}, "data_provider": {"refresh"}}

def send_command(domain: str, command: str, **params):
    if command not in ALLOW.get(domain, {}):
        return {"ok": False, "err": "denied"}
    # TODO:                                        (          /        )
    return {"ok": True, "info": {"domain": domain, "command": command, "params": params}}
```

###                                                

*                                  `execution`, `risk`, `data_provider`                      `emit_event(...)` (                                          ,           /                                  ).
*              smoke-            100+            (sandbox/testrun).

###               

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

* `logs/causal_events.jsonl`                    50               ,                              .
* Unit strict                 .

---

## 2) Sprint B     CA-FSM (            ,                          )

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
    guard: str     #                          "signal_confidence > 0.7"
    weight: float  #                            

class CAFSM:
    def __init__(self, transitions, start="IDLE"):
        self.s = start
        self.transitions = transitions

    def step(self, event:str, ctx:dict):
        cand = [t for t in self.transitions if t.from_state==self.s and t.event==event]
        if not cand: return self.s
        t = max(cand, key=lambda x: x.weight)  #                                   
        # TODO:              guard      ctx (                   eval/                          )
        self.s = t.to_state
        emit_event("meta_fsm","transition",{"from": t.from_state,"event": event,"to": t.to_state})
        return self.s

    def on_tick(self):
        m = collect_metrics()
        emit_event("meta_fsm","metrics",m)
        #                                                    
```

**config/ca_fsm.yaml** (              )

```yaml
transitions:
  - { from: IDLE, event: START, to: SCAN, guard: "True", weight: 0.8 }
  - { from: SCAN, event: SIGNAL, to: RISK_CHECK, guard: "signal_confidence > 0.7", weight: 0.8 }
  - { from: RISK_CHECK, event: PASS, to: EXECUTE, guard: "risk_score < 0.5", weight: 0.7 }
  - { from: EXECUTE, event: DONE, to: IDLE, guard: "True", weight: 1.0 }
```

**                               `run_r0.py` /                          :**

*                            `CAFSM`                                     .
*                                                                             `fsm.step(event, ctx)`.
*      timer/heartbeat     `fsm.on_tick()`.

### DoD (B)

* FSM                                                                   (IDLE   SCAN   RISK_CHECK   EXECUTE   IDLE),                                `causal_events.jsonl`.
*                        /                  .

---

## 3) Sprint C     Axial Gradient (PnL-                    ) + Evaluator (                       )

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

                   `eval_once()`                   FSM.

### DoD (C)

* `logs/ag_eval.jsonl`                    ; **ag**      NaN/inf;                                           (                  ~0                  ).
* Unit strict                 .

---

## 4) Sprint D     Proof Kernel (LTL                + checksum-gate)

**proof_kernel/ltl_invariants.yaml** (                                 )

```yaml
safety:
  - "G ! duplicate_entry"     #                                      submit
  - "G (OPEN -> F BRACKETS)"  #                                                                            
```

**proof_kernel/ltl_shield.py**                                   (                         ,                                             ),         :
**proof_kernel/ontological_checksum.py**

```python
def checksum_ok(proposal: dict, P=97, c=4):
    s = json_dumps_canon(proposal)  #                                    /          
    return (hash(s) % P) == c
```

                                        -            apply_guard_update   .

### DoD (D)

*                    safety                     denied       `proof_record.jsonl`.
*                                     (                              )        accepted   .

---

## 5) Sprint E                        LLA            (                                       )

                     **            **     ,                                                       :

* `tools/r2_hybrid_stage.py`, `tools/r2_readiness_check.py`, `tools/r2_cfg_freeze.py`, `tools/r2_sbom.py`, `tools/r2_dod_report.py`, `tools/r2_full_pass_gate.py`, `tools/r2_all_gates.py`, `tools/r2_cfg_guard.py`, `tools/cfg_patch_defaults.json`.
* `living_latent/r2/hybrid/ltl_shield.py`                                                                      PK (                   );                                         PK                   2               .
* (              ,               ) `pipeline.py`, `conf_gate.py`, `dro_gate.py`     **            **                                                                                                                                 .

              : **             hard-deps**    unit-          .                                          /                 `@pytest.mark.integration`                       /lazy-imports (                                   ).

### DoD (E)

*                     `tools/r2_hybrid_stage.py`     **OK**,                                   .
* Readiness check     `R2_72H_READY=YES`.

---

## 6) Sprint F     CI/Unit    strict    (                     baseline)

*                workflow    **strict warnings**    `pytest-asyncio`                   (ubuntu/windows    3.10/3.11).
*                   : `UNIT_TEST_LOG.txt`, freeze, sbom, DoD.

### DoD (F)

* Unit                **GREEN**;                       Actions.

---

## 7) Sprint G     72h Shadow

*                 **shadow-            ** (                        ,                         side-effects).
*                      heartbeat/lock, causal_events, ag_eval, proof_record;                    acceptance/DoD                        .

###                (              )

```bash
python tools/r2_hybrid_stage.py start --ensure-cfg --mode ab --out logs/hybrid/preflight_status.json
python tools/r2_readiness_check.py   #                  R2_72H_READY=YES
#                           shadow-           (       runner),           logs/hybrid/run_stdout.log
```

### DoD (G)

* `R2_72H_READY=YES`, Acceptance READY, 0 CRITICAL, LTL-                           .

---

##                                          

* **Windows         /   runs\runs/last   **                  `pathlib`    `foundation/system/paths.py`;                                   (                      ).
* **           PRE-            ** (                              CVaR/obs)        shadow                                                               /                                 ,        PRE                                                 .
* **                                      **              **                **;                                                                  AG,                                                                        Hoeffding-                .
* **                               **                   unit;                                                                        +       .

---

##                                    Sprint G

* LLA            **Meta-FSM / CA-FSM**                                       .
*    **                           ** (causal_events), **AG-            **    **Proof Kernel** (               safety).
* CI green,                                               ,    **                                 72h shadow**.

---

##                 :                          72h                                    

                                        Sprints A   F    `python tools/r2_readiness_check.py`                  `R2_72H_READY=YES`,              shadow-           (                              )                                    72              .

---



---

#                A                                                LLA    (                               )

           ,      **                                     **    LLA                         ,        LLA-                             r0-                                                  CA-FSM + 72h Shadow:

1. **tools/**

* `r2_hybrid_stage.py`                 /                                    (preflight, shadow, acceptance).
* `r2_readiness_check.py`                                        ,                                                     `R2_72H_READY=YES/NO`.
* `r2_cfg_guard.py` + `cfg_patch_defaults.json`                                            `cfg/r2.yaml`.
* `r2_cfg_freeze.py`     freeze                  (yaml + sha256).
* `r2_sbom.py`     SBOM/                                       .
* `r2_all_gates.py`, `r2_full_pass_gate.py`, `r2_dod_report.py`                            ,                   GO/NO-GO   , DoD-        .

2. **foundation/hybrid/**

* `stage_orchestrator.py`                           +                  +                   .
* `pi_bridge.py`               /                          (policy interface, rate/latency               ).
* `rate_limit.py`               -          /                              .
* `conf_gate.py`, `dro_gate.py`                                 /                            (                                                    ).

3. **foundation/proof_kernel/**

* `ltl_shield.py`     LTL-                  checksum-gate (                                                                  ).

4. **foundation/system/**

* `paths.py`                                                        (Windows-safe),                         `runs\runs/last`                             .

5. **cfg/**

* `r2.yaml`                                                       /             (                                                                  `r2_cfg_guard.py --autofix`).

6. **foundation/hybrid/r0_adapter.py** *(                                   )*
                              ,                              `r0_*.py`            3           : `r0_on_start/step/stop`.

> **                :**                               `foundation/*`                                                                          (                   `vfoundation/*`).                                                                        .

---

#                B                                                        (                            ,                            )

               **                                                           **.                                                     ;               ,                                              .

### 1)                                    

* **                 :**                                                                       acceptance     freeze/SBOM     DoD.
* **API:** `start(mode: str, out: Path)`, `simulate(ticks: int)`.
* **DoD:**                `logs/hybrid/preflight_status.json`, `acceptance_summary_*.json`, `strict_gate_events.jsonl`.

### 2) Readiness-checker

* **                 :**                                                                      `R2_72H_READY=YES/NO` (exit-code 0/1).
* **        :** `preflight_status.json`, `acceptance_summary_*.json`, freeze/sha, SBOM.
* **DoD:**                                                  ;                             CI.

### 3) Config-guard (+                 )

* **                 :**                   /                             `cfg/r2.yaml` (                        `hybrid.*`,               ,                        ).
* **DoD:**                                                             `r2.yaml`                                             .

### 4) Freeze/SBOM/DoD-                  

* **                   :**
  freeze                      snapshot                + sha256;
  sbom                                      ;
  dod                                                                                 GO/NO-GO   .
* **DoD:**                            `reports/` (`cfg_freeze_*.yaml/.sha256`, `sbom_*`, `R2_DOD_*.md`).

### 5) Stage-orchestrator core

* **                 :**                       (S0   Sn),               , heartbeat, file-locks, state-            ,                                           .
* **DoD:** `logs/hybrid/.heartbeat`, `stage_state.json`,                                                                    .

### 6) R0-adapter (            )

* **                 :**                           `r0_*.py`                                      3           :

  * `r0_on_start(ctx)`, `r0_on_step(ctx)`, `r0_on_stop(ctx)`
* **DoD:**          `step()` =                                   ;                                                                 (                           ).

### 7) Bridges (                               )

* **event_bridge:**          **causal events**    `logs/causal_events.jsonl`
  `emit_event(domain, event, payload)`
* **metric_bridge:**              PnL/CVaR/latency                  
  `collect_metrics() -> dict`
* **command_bridge:**                                                                  (whitelist + rate-limit)
  `send_command(domain, command, args) -> Result`
* **DoD:**       50 `causal_events`      smoke-          ; latency/CVaR              .

### 8) Proof-kernel

* **                 :** LTL-               + checksum-gate                                                                      /                .
* **API:** `ltl_accepts(trace|proposal) -> bool`, `checksum_ok(proposal) -> bool`.
* **DoD:**                                                              ; `logs/proof_record.jsonl`                              .

### 9) Policy-interface (PI-bridge)

* **                 :**                                                                      /                    rate-limit/latency-budget.
* **API:** `should_accept_candidate(key, delta, cost, clock) -> (bool, info)`.
* **DoD:**                                                                    ;          `policy_updates.jsonl`.

### 10) Rate-limit

* **                 :**           -          ,                                                                                         .
* **DoD:**                                      K                 /      ;                             .

### 11) CA-FSM (Meta-FSM                        )

* **                 :**               ,                                                              (`execution`, `risk`, `data_provider`)                              ;                                                     .
* **API:** `tick(obs)`, `transition(state, event) -> (next_state, action)`.
* **DoD:** smoke 100   500       i                      ; `causal_events.jsonl`                         .

### 12) Axial-gradient +                    (                    )

* **                 :**                                                           AG (PnL-                    ) +                                                  K              (**            **          Proof-kernel                 ).
* **DoD:** `ag_eval.jsonl`                         ;                      ,                 ,                          .

### 13) Paths helper

* **                 :**                                        (                      Windows): `get_logs_dir()`, `get_runs_dir()`, `ensure_dir()`.
* **DoD:**              `runs/runs\last`;                                          .

### 14) Config (`cfg/r2.yaml`)

* **                 :**                          ,               ,               ,                                .
* **DoD:**                             guard-              ;                                                                     .

---

##                                                    

1. **   r0**                      :

```python
def r0_on_start(ctx): ...
def r0_on_step(ctx):  ...
def r0_on_stop(ctx):  ...
```

2. **            **                                (                                             ):

```python
from foundation.hybrid.r0_adapter import R0Engine
e = R0Engine('r0_main'); e.start(); e.step(); e.stop()
```

3. **      **                                               A,         :

```bash
python tools/r2_cfg_guard.py cfg/r2.yaml --autofix --patch-file tools/cfg_patch_defaults.json
python tools/r2_hybrid_stage.py start --ensure-cfg --mode ab --out logs/hybrid/preflight_status.json
python tools/r2_readiness_check.py   #                       R2_72H_READY=YES (                               )
```


