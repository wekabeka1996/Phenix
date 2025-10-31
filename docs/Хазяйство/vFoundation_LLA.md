# vFoundation ‚áÜ LLA Transition Roadmap (CA-FSM, Bridges, Proof Kernel) ‚ î v1.0

> ** ú µ Ç    ¥ æ ∫ É º µ Ω Ç  :**  ¥   Ç ∏  á ñ Ç ∫ µ,  Ç µ Ö Ω ñ á Ω æ  ∫ æ Ω ∫   µ Ç Ω µ  ±   á µ Ω Ω è    µ   µ Ö æ ¥ É  Ω        Ö ñ Ç µ ∫ Ç É   É vFoundation-CA  ∑ LLA  è ∫  æ   å æ ≤ æ ≥ æ  è ¥     (Meta-FSM ‚Üí CA-FSM ‚Üí  ¥ æ º µ Ω ∏).
>  ¢ É Ç  æ   ∏     Ω ñ:  Ü ñ ª å,    æ µ Ç     Ω ∏ π    ª   Ω, Definition of Done (DoD)  ¥ ª è  ∫ æ ∂ Ω æ ≥ æ  µ Ç     É,  Ç ∏   æ ≤ ñ    ∏ ∑ ∏ ∫ ∏/   ∫ ª   ¥ Ω æ â ñ  π      æ   æ ± ∏  ó Ö  ≤ ∏   ñ à µ Ω Ω è,      Ç µ Ñ   ∫ Ç ∏,  ∫ æ º   Ω ¥ ∏  Ç    á µ ∫- ª ∏   Ç ∏      ∏ π º   Ω Ω è.

---

## 0)  ö æ   æ Ç ∫ æ      æ  Ü ñ ª ñ

1. **LLA  è ∫ ‚ ú ¥ É à  ‚ ù    ∏   Ç µ º ∏:** LLA  ∫ µ   É î **Meta-FSM/CA-FSM**,  ∑ ± ∏     î  ñ Ω ¥ ∏ ∫   Ç æ   ∏  ∑  ¥ æ º µ Ω ñ ≤ (execution, risk, data_provider),    ª   Ω É î    æ   ª ñ ¥ æ ≤ Ω ñ   Ç å  ñ  ñ î       Ö ñ é    ∏ ≥ Ω   ª ñ ≤,    ¥     Ç É î    æ   æ ≥ ∏/ ≤   ≥ ∏    µ   µ Ö æ ¥ ñ ≤.
2. **Causal Adaptation:**  É   ñ    µ   µ Ö æ ¥ ∏ FSM  º   é Ç å **     ∏ á ∏ Ω Ω ∏ π    ª ñ ¥**  ñ  æ Ü ñ Ω é é Ç å   è **Axial Gradient** (AG),  è ∫ ∏ π  º ∏  ∫ æ Ω Ü µ Ω Ç   É î º æ  Ω   **+PnL** ( ∑  ±   ª   Ω   æ º CVaR/ ª   Ç µ Ω Ç Ω æ   Ç ñ/   Ç   ± ñ ª å Ω æ   Ç ñ).
3. **Bridges  è ∫  Ω µ   ≤ æ ≤      ∏   Ç µ º  :**    Ç   Ω ¥     Ç Ω ñ **EventBridge / MetricBridge / CommandBridge**  ¥   é Ç å      æ ∑ æ   ∏ π  ∫   Ω   ª  º ñ ∂ vFoundation  ñ LLA.
4. **Proof Kernel + LTL  ñ Ω ≤     ñ   Ω Ç ∏:**  Ñ æ   º   ª å Ω      µ   µ ≤ ñ   ∫  ,  â æ    ¥     Ç   Ü ñ ó  Ω µ    æ   É à É é Ç å  ñ Ω ≤     ñ   Ω Ç ∏  ± µ ∑   µ ∫ ∏/ ∂ ∏ ≤ É á æ   Ç ñ.
5. **72h Shadow readiness:**    µ   µ ¥  ± æ î º ‚ î 72  ≥ æ ¥ ∏ Ω ∏    Ç   ± ñ ª å Ω æ ≥ æ  Ç ñ ∫   Ω Ω è  ∫ æ Ω Ç É   É  ∑  ª æ ≥   º ∏, acceptance- ∑   ñ ∑   º ∏, freeze/SBOM  ñ GO- Ñ ª   ≥ æ º.

---

## 1)  ü æ Ç æ á Ω ∏ π  ∫ æ Ω Ç µ ∫   Ç ( É ∑   ≥   ª å Ω µ Ω Ω è  ∑  ≤   à ∏ Ö  ñ Ω   É Ç ñ ≤)

* ** † µ   æ ∑ ∏ Ç æ   ñ π A (   ∫ ª   ¥ Ω ñ à ∏ π, R2Hybrid  º   π ∂ µ PASS):**    æ ± æ á ñ  Ç µ   Ç ∏/CI,    ª µ  â µ  Ω µ º   î vFoundation;  î R2Hybrid  æ   ∫ µ   Ç     Ç æ  , DoD, strict gates.
* ** † µ   æ ∑ ∏ Ç æ   ñ π B (     æ   Ç ñ à ñ π,  ±   ∑ æ ≤ ∏ π vFoundation):**  ¥ æ º µ Ω ∏ (execution, risk, data_provider)  î,  Ñ æ   º   Ç ‚ ú ± µ ∑  º æ Ω æ ª ñ Ç É‚ ù,    ª æ ≤ Ω ∏ ∫ ∏/ ¥ æ º µ Ω ∏, **   ª µ  ∫ µ   É ≤   Ω Ω è  ¥ æ º µ Ω   º ∏  â µ  ∫ É ª å ≥   î**;      º µ  Ç É Ç  Ω   π     æ   Ç ñ à µ  à ≤ ∏ ¥ ∫ æ    æ   Ç   ≤ ∏ Ç ∏ LLA  è ∫ Meta-FSM/CA-FSM    æ ≤ µ   Ö  ¥ æ º µ Ω ñ ≤  á µ   µ ∑  º æ   Ç ∏.

** † µ ∫ æ º µ Ω ¥   Ü ñ è    Ç     Ç É:**
 ü æ á   Ç ∏  ∑ **B (     æ   Ç ñ à æ ≥ æ vFoundation)**  è ∫ ‚ ú   µ Ñ µ   µ Ω   Ω æ ó    ª   Ç Ñ æ   º ∏‚ ù ‚ î  Ç É Ç ** à ≤ ∏ ¥ à µ**    ñ ¥ Ω è Ç ∏ CA-FSM + Bridges + Proof Kernel  ñ  ¥ æ   è ≥ Ç ∏ **72h readiness**.  ü æ Ç ñ º    æ ≤ Ç æ   Ω æ  ≤ ∏ ∫ æ   ∏   Ç   Ç ∏  Ü µ π  ∫     ∫      É    ∫ ª   ¥ Ω ñ à æ º É A (R2Hybrid).

---

## 2)  ¶ ñ ª å æ ≤        Ö ñ Ç µ ∫ Ç É    

```
LLA (Meta-FSM/CA-FSM)
  ‚îú‚î  Axial Gradient (AG) [+PnL, -CVaR, +Stability, -Latency]
  ‚îú‚î  Causal Graph (event ‚Üí transition ‚Üí outcome)
  ‚îú‚î  Gradient Evaluator (online / Optuna-like tuner)
  ‚îú‚î  Proof Kernel (LTL Invariants + Ontological Checksum)
  ‚îî‚î  Adapters/Bridges
       ‚îú‚î  EventBridge     (foundation ‚Üí LLA causal_event)
       ‚îú‚î  MetricBridge    (foundation ‚Üí LLA metrics)
       ‚îî‚î  CommandBridge   (LLA ‚Üí foundation commands)

vFoundation
  ‚îú‚î  Domain: execution
  ‚îú‚î  Domain: risk
  ‚îî‚î  Domain: data_provider
```

** ö ª é á æ ≤ ñ  ≤ ª     Ç ∏ ≤ æ   Ç ñ:**

* ** ê ¥     Ç   Ü ñ ó          º µ Ç   ∏ ∑ æ ≤   Ω ñ:**  ∑ º ñ Ω é î º æ  Ω µ  ∫ æ ¥  ¥ æ º µ Ω ñ ≤,             º µ Ç   ∏  ≥ ≤     ¥ ñ ≤/ ≤   ≥    µ   µ Ö æ ¥ ñ ≤.
* ** ü æ ≤ Ω    Ç       æ ≤   Ω ñ   Ç å:**  ∫ æ ∂ Ω ∏ π    µ   µ Ö ñ ¥  º   î causal_event,  ∫ æ ∂ Ω µ    ñ à µ Ω Ω è      ∏ ≤‚ ô è ∑   Ω µ  ¥ æ AG.
* ** ë µ ∑   µ ∫    ∑ º ñ Ω:** LTL- º æ Ω ñ Ç æ    ± ª æ ∫ É î  Ω µ ± µ ∑   µ á Ω ñ  æ Ω æ ≤ ª µ Ω Ω è; checksum-gate  ¥   î  Ç   º   µ  - µ ≤ ñ ¥ µ Ω  .

---

## 3)  î æ   æ ∂ Ω è  ∫     Ç   ( µ Ç     ∏ ‚Üí DoD,    ∏ ∑ ∏ ∫ ∏  Ç    ≤ ∏   ñ à µ Ω Ω è)

>  í   ñ  µ Ç     ∏  Ω ∏ ∂ á µ ‚ î ** ñ Ω ∫   µ º µ Ω Ç   ª å Ω ñ**,  ∑ **     Ç µ Ñ   ∫ Ç   º ∏**  ñ ** ∫ æ º   Ω ¥   º ∏**,  è ∫ ñ  Ñ ñ ∫   É é Ç å    Ç   Ω.

###  ï Ç     S0.  Ü Ω Ñ       Ç   É ∫ Ç É   Ω ∏ π  ±   ∑ ∏   & Preflight

** ¶ ñ ª å:** ‚ ú á ∏   Ç ∏ π    Ç ñ ª‚ ù  ¥ ª è  ¥ µ ≤/CI,  æ ¥ Ω    ∫ æ º ± ñ Ω   Ü ñ è Python (3.11) +  º ñ Ω ñ º   ª å Ω ñ  ∑   ª µ ∂ Ω æ   Ç ñ, **warnings-as-errors** (Deprecation/Runtime).

** ö   æ ∫ ∏:**

* [ ]  ü µ   µ Ω µ   Ç ∏  ∫     ∫     LLA  É `foundation/meta_fsm/` ( ± µ ∑  ≤   ∂ ∫ ∏ Ö  ∑   ª µ ∂ Ω æ   Ç µ π: ‚ ú à ∏ º‚ ù  ∑   º ñ   Ç å numpy/scipy  É  é Ω ñ Ç- º   Ç   ∏ Ü ñ).
* [ ]  ó   ≤ µ   Ç ∏ `adapters/` (event/metric/command),  ± µ ∑    æ ± ñ á Ω ∏ Ö  µ Ñ µ ∫ Ç ñ ≤.
* [ ]  ü ñ ¥ ≥ æ Ç É ≤   Ç ∏ `pytest.ini` (asyncio_mode=auto, error::DeprecationWarning/RuntimeWarning).
* [ ]  î æ ¥   Ç ∏ dev- ∑   ª µ ∂ Ω æ   Ç ñ `requirements-dev.txt` (pytest, pytest-asyncio, pyyaml, jsonschema).

**DoD (     Ç µ Ñ   ∫ Ç ∏):**

* [ ] GREEN unit run: `pytest -q -W error::DeprecationWarning -W error::RuntimeWarning`.
* [ ] `reports/sbom_*`, `reports/cfg_freeze_pre.yaml, .sha256`.
* [ ] `logs/hybrid/preflight_status.json` (overall_pass: true).

** ¢ ∏   æ ≤ ñ    ∫ ª   ¥ Ω æ â ñ  Ç      ñ à µ Ω Ω è:**

* **Windows  à ª è Ö ∏ (`runs/runs\last`)** ‚Üí    Ç   Ω ¥     Ç ∏ ∑ É ≤   Ç ∏  á µ   µ ∑ `pathlib`,  ∂ æ ¥ Ω ∏ Ö  ∫ æ Ω ∫   Ç µ Ω   Ü ñ π    è ¥ ∫   º ∏.
* ** í   ∂ ∫ ñ  ∑   ª µ ∂ Ω æ   Ç ñ** ‚Üí  é Ω ñ Ç- º   Ç   ∏ Ü è  ∑ ‚ ú à ∏ º   º ∏‚ ù  Ç   lazy-imports.

---

###  ï Ç     S1. Bridges v1 ( º ∏ Ω ∏ º   ª å Ω ∏ π  ñ Ω Ç µ ≥     Ü ñ π Ω ∏ π  à    )

** ¶ ñ ª å:**    ñ ¥ ∫ ª é á ∏ Ç ∏  ≤ ∏ ∫ æ Ω   Ω ñ  ¥ æ º µ Ω ∏  ¥ æ LLA  á µ   µ ∑  Ç   ∏  º æ   Ç ∏.

** ö   æ ∫ ∏:**

* [ ] `adapters/event_bridge.py`: `emit_event(domain, event, payload)` ‚Üí    ∏ à µ JSONL  É `logs/causal_events.jsonl`.
* [ ] `adapters/metric_bridge.py`: `collect_metrics()` ‚Üí PnL, CVaR, latency, drawdown ( ∑  ¥ æ º µ Ω ñ ≤).
* [ ] `adapters/command_bridge.py`: `send_command(domain, command, **params)` ‚Üí  ¥ µ ª µ ≥ É î  ≤  ¥ æ º µ Ω ∏.

**DoD:**

* [ ]  ü æ ¥ ñ ó  ¥ æ º µ Ω ñ ≤    µ   ª å Ω æ  ∑‚ ô è ≤ ª è é Ç å   è  É `logs/causal_events.jsonl` (‚â• 50    æ ¥ ñ π  É smoke-     æ ≥ æ Ω ñ).
* [ ] `collect_metrics()`    æ ≤ µ   Ç   î  ≤   ª ñ ¥ Ω ñ  ∑ Ω   á µ Ω Ω è ( Ω µ `None`,  Ω µ `nan`).
* [ ]  ö æ º   Ω ¥ ∏  ∑ LLA  ≤ ∏ ∫ ª ∏ ∫   é Ç å  æ á ñ ∫ É ≤   Ω É    µ   ∫ Ü ñ é  ¥ æ º µ Ω ñ ≤ ( ñ ¥ µ º   æ Ç µ Ω Ç Ω ñ   Ç å + rate-limit).

** ° ∫ ª   ¥ Ω æ â ñ:**

* ** ù µ º   î  ∑ ≤‚ ô è ∑ ∫ É    ± æ    æ ¥ ñ ó  Ω µ    ∏ à É Ç å   è:**    µ   µ ≤ ñ   ∏ Ç ∏  ¥ æ ∑ ≤ æ ª ∏/ à ª è Ö ∏/     ∏ Ω Ö   æ Ω Ω ñ   Ç å,  ¥ æ ¥   Ç ∏    µ Ç     ó.
* ** ö æ º   Ω ¥ ∏  Ω µ ± µ ∑   µ á Ω ñ  É LIVE:**  ¥ æ ¥   Ç ∏ ‚ úshadow‚ ù          æ   µ Ü å ( ª æ ≥ É ≤   Ç ∏  ∑   º ñ   Ç å  ≤ ∏ ∫ æ Ω É ≤   Ç ∏).

---

###  ï Ç     S2. CA-FSM  ∫     ∫     ( ± µ ∑    ¥     Ç   Ü ñ π)

** ¶ ñ ª å:** **Meta-FSM**  ∫ µ   É î    æ   ª ñ ¥ æ ≤ Ω ñ   Ç é  ¥ ñ π  º ñ ∂  ¥ æ º µ Ω   º ∏; **CA-FSM**  ∑ ± µ   ñ ≥   î          º µ Ç   ∏  ≥ ≤     ¥ ñ ≤/ ≤   ≥; ** ± µ ∑**    ≤ Ç æ º   Ç ∏ á Ω ∏ Ö  æ Ω æ ≤ ª µ Ω å.

** ö   æ ∫ ∏:**

* [ ] `meta_fsm/ca_fsm.py`:  º æ ¥ µ ª å    Ç   Ω ñ ≤,    æ ¥ ñ π  ñ  ¥ µ ∫ ª       Ç ∏ ≤ Ω ñ  ≥ ≤     ¥ ∏ (yaml).
* [ ]  ö æ Ω Ç É   ‚ ú     æ   Ç µ   µ ∂ µ Ω Ω è ‚Üí    µ   µ Ö ñ ¥ ‚Üí  ∑     ∏    É causal_events‚ ù.
* [ ]  ü ª   Ω É ≤   ª å Ω ∏ ∫    æ   ª ñ ¥ æ ≤ Ω æ   Ç µ π:  ∑    ∑   º æ ≤ á É ≤   Ω Ω è º  Ñ ñ ∫   æ ≤   Ω ∏ π ( â æ ±    µ   µ ≤ ñ   ∏ Ç ∏  ±   ∑ æ ≤ ∏ π  Ü ∏ ∫ ª).

**DoD:**

* [ ]  î µ º æ Ω   Ç     Ü ñ è ‚ ú µ   ñ ∑ æ ¥ É‚ ù  ≤ ñ ¥ intent  ¥ æ  Ç µ   º ñ Ω   ª å Ω æ ≥ æ    Ç   Ω É (open‚Üímanage‚Üíclose).
* [ ] 0  ∫   ∏ Ç ∏ á Ω ∏ Ö    æ º ∏ ª æ ∫  É  ª æ ≥   Ö    ñ ¥  á        µ   ñ ó  ∑ ‚â•100  µ   ñ ∑ æ ¥ ñ ≤  É sandbox.

** ° ∫ ª   ¥ Ω æ â ñ:**

* ** ù µ   ∏ Ω Ö   æ Ω Ω ñ   Ç å    ∏ ≥ Ω   ª ñ ≤  ¥ æ º µ Ω ñ ≤:**  É   ñ call-backs  ¥ æ º µ Ω ñ ≤  æ ± ≥ æ   Ω É Ç ∏  É timeouts/guards;  ª æ ≥ ñ ∫ É ‚ úready‚ ù    Ç   Ω ¥     Ç ∏ ∑ É ≤   Ç ∏  á µ   µ ∑    ª æ ≤ Ω ∏ ∫ ∏- ñ Ω Ç µ   Ñ µ π   ∏.

---

###  ï Ç     S3. Axial Gradient (+PnL- Ü µ Ω Ç   ∏ á Ω  )  Ç   Gradient Evaluator

** ¶ ñ ª å:**  ≤ ± É ¥ É ≤   Ç ∏ **AG**  ñ ** æ Ü ñ Ω é ≤   á  ≥     ¥ ñ î Ω Ç  ** (EMA, Hoeffding-   æ   æ ≥ É ≤   Ω Ω è;  ± µ ∑   µ á Ω ∏ π  ± µ ∑ ≥     ¥ ñ î Ω Ç Ω ∏ π  Ç é Ω µ    Ω      µ   à ∏ π  á    ).

** ö   æ ∫ ∏:**

* [ ] `ag/axial_gradient.py`  ∑          º µ Ç     º ∏  ≤   ≥ (pnl, cvar, stability, latency).
* [ ] `ge/evaluator.py`: EMA  Ω   ¥  µ   ñ ∑ æ ¥   º ∏ + Hoeffding  ¥ ª è n  ≤ ∏ ± ñ   æ ∫; ** ± µ ∑**  ∑ º ñ Ω ∏ \theta  Ω      Ç     Ç ñ ( Ç ñ ª å ∫ ∏  æ ± ª ñ ∫).
* [ ]  ü æ Ç ñ º  É ≤ ñ º ∫ Ω É Ç ∏  ¥ ∏   ∫   µ Ç Ω ∏ π  Ç é Ω µ  :      æ ± Ω ñ ¬±Œ¥  ∑ º ñ Ω ∏    æ   æ ≥ É  ≤  æ ¥ Ω æ º É guard,      ∏ π º   î º æ  Ω       è º  ∑  ∫     â ∏ º \bar{AG}.

**DoD:**

* [ ] AG  ª æ ≥ É é Ç å   è  ¥ ª è  ∫ æ ∂ Ω æ ≥ æ  µ   ñ ∑ æ ¥ É (`logs/ag_eval.jsonl`).
* [ ]  î ª è    Ç   ± ñ ª å Ω æ ó    µ   ñ ó (n‚â•30) ‚ î \bar{AG}  º   î    ¥ µ ∫ ≤   Ç Ω ∏ π    æ ∑   æ ¥ ñ ª ( Ω µ  ≤   è  º        ≤ ¬±‚àû/NaN).
* [ ]  ë µ ∑   µ á Ω æ  É ≤ ñ º ∫ Ω µ Ω ∏ π  Ç é Ω µ  :  Ω µ    æ   É à É î  ñ Ω ≤     ñ   Ω Ç ∏ ( ¥ ∏ ≤. S4).

** ° ∫ ª   ¥ Ω æ â ñ:**

* **Small-N  à É º:**  Ω µ  µ   ∫   ª é ≤   Ç ∏  ¥ æ RuntimeWarning;  ∑   ª ∏ à ∏ Ç ∏  è ∫ UserWarning  ñ  Ç   ∏ º   Ç ∏ Hoeffding- Ñ ñ ª å Ç  .
* ** î   µ π Ñ  ±   ∑ ∏:**    µ   ñ æ ¥ ∏ á Ω æ    µ   µ     Ö æ ≤ É ≤   Ç ∏ baseline.

---

###  ï Ç     S4. Proof Kernel (LTL + Ontological Checksum)

** ¶ ñ ª å:** ** Ω ñ è ∫ æ ó    ¥     Ç   Ü ñ ó**,  è ∫ â æ    æ   É à É é Ç å   è  ñ Ω ≤     ñ   Ω Ç ∏    ± æ  Ω µ      æ π ¥ µ Ω æ checksum-gate.

** ö   æ ∫ ∏:**

* [ ] LTL- º æ Ω ñ Ç æ   (safety/liveness): duplicate_entry, reduce_only, brackets,  ñ  Ç. ¥.
* [ ] Ontological checksum ( Ω µ ∫   ∏   Ç æ ≥     Ñ ñ á Ω ∏ π  Ñ ñ ª å Ç  ): H(S) = hash(update-tuple) mod P == c.
* [ ] Truth-Score (TS)  ñ gate: freeze    ¥     Ç   Ü ñ π      ∏ TS < œÑ.

**DoD:**

* [ ]  ë É ¥ å- è ∫ µ  ∑     Ç æ   É ≤   Ω Ω è  æ Ω æ ≤ ª µ Ω Ω è  º   î  ∑     ∏   ‚ úproof_record‚ ù (ok/denied +      ∏ á ∏ Ω  ).
* [ ]  ü   ∏    æ   É à µ Ω Ω ñ LTL ‚ î  æ Ω æ ≤ ª µ Ω Ω è  Ω µ  ∑     Ç æ   æ ≤ É î Ç å   è, CA-FSM  ª ∏ à   î Ç å   è  ∫ æ Ω   ∏   Ç µ Ω Ç Ω æ é.
* [ ] TS- ≥ µ π Ç ∏ Ω ≥  ≤ º ∏ ∫   î safe-policy      ∏  ¥ µ ≥     ¥   Ü ñ ó.

** ° ∫ ª   ¥ Ω æ â ñ:**

* ** • ∏ ± Ω ñ    æ ∑ ∏ Ç ∏ ≤ ∏/ Ω µ ≥   Ç ∏ ≤ ∏  É LTL:**  ñ ∑ æ ª é ≤   Ç ∏    µ º   Ω Ç ∏ ∫ É,  Ç µ   Ç ∏-   Ü µ Ω     ñ ó  ¥ ª è  è ¥        µ   µ Ö æ ¥ ñ ≤.

---

###  ï Ç     S5.  Ü Ω Ç µ ≥     Ü ñ è  ∑  æ   ∫ µ   Ç     Ç æ   æ º & DoD- º   à ∏ Ω ∫  

** ¶ ñ ª å:**      ∏ ≤ µ   Ç ∏ **DoD-     Ç µ Ñ   ∫ Ç ∏**  É    Ç   Ω ¥     Ç Ω É  Ñ æ   º É  π  ∑   ª ∏ Ç ∏  ≤ CI.

** ö   æ ∫ ∏:**

* [ ]  ° ∫   ∏   Ç ∏: freeze (`cfg_freeze_*`), SBOM (`sbom_*`), DoD- ∑ ≤ ñ Ç (R2_DOD_*), acceptance snapshots, strict gate events, GO-flag.
* [ ] Run-ID  ñ Ω ∂ µ ∫ Ü ñ è  É DoD ( ¥ ª è  Ç       É ≤   Ω Ω è).
* [ ]  ü µ   µ ≤ ñ   ∫ ∏ wirehead-scan (`--fail-on any`), preflight, unit strict.

**DoD (     Ç µ Ñ   ∫ Ç ∏  É `reports/`  ñ `logs/`):**

* [ ] `reports/cfg_freeze_*.yaml/.sha256`, `reports/sbom_*`, `reports/R2_DOD_*.md`.
* [ ] `logs/hybrid/acceptance_summary_*.json`, `logs/hybrid/strict_gate_events.jsonl`.
* [ ] `reports/R2_FULL_PASS_OK_*.flag`  ∑ ‚ úGO‚ ù.

** ° ∫ ª   ¥ Ω æ â ñ:**

* ** ü ª   Ç Ñ æ   º µ Ω ñ path- ±   ≥ ∏:**  ≤   µ  á µ   µ ∑ `pathlib`.
* ** ö æ Ω Ñ ñ ≥ ∏    æ ∑‚ ô ó ∂ ¥ ∂   é Ç å   è:** `r2_cfg_guard` + ‚ úautofix‚ ù      æ Ñ ñ ª å.

---

###  ï Ç     S6. 72h Shadow (readiness)

** ¶ ñ ª å:** **72  ≥ æ ¥ ∏ Ω ∏**  ± µ ∑  ∫   ∏ Ç ∏ á Ω ∏ Ö  ∑ ± æ ó ≤,  ∑ **AG > 0** ( Ω    ≤ ∏ ±     Ω æ º É  ñ Ω Ç µ   ≤   ª ñ), **TS ‚â• œÑ**, ** ñ Ω ≤     ñ   Ω Ç ∏  ≤ ∏ ∫ æ Ω É é Ç å   è**, Acceptance PASS.

** ö   æ ∫ ∏:**

* [ ]  ó     É   ∫  ≤ ‚ úshadow‚ ù    µ ∂ ∏ º ñ:  ∫ æ º   Ω ¥ ∏ ** ª æ ≥ É é Ç å   è**,    ª µ  æ ± º µ ∂ µ Ω æ  ≤ ∏ ∫ æ Ω É é Ç å   è ( ª ∏ à µ  ± µ ∑   µ á Ω ñ).
* [ ]  ú æ Ω ñ Ç æ   ∏ Ω ≥ heartbeat/lock, causal_events, ag_eval, proof_record.
* [ ]  ü µ   ñ æ ¥ ∏ á Ω    ≥ µ Ω µ     Ü ñ è acceptance  Ç   DoD.

**DoD:**

* [ ] `R2_72H_READY=YES` ( ≤ ª     Ω ∏ π checker-   ∫   ∏   Ç, exit 0/1).
* [ ] 0 CRITICAL  É  ∂ É   Ω   ª   Ö; TS  Ω µ      ¥   î  Ω ∏ ∂ á µ œÑ; LTL-   æ   É à µ Ω Ω è = 0.
* [ ] Acceptance SUMMARY: READY.

** ° ∫ ª   ¥ Ω æ â ñ:**

* ** ü µ   µ ∑     É   ∫ ∏  á µ   µ ∑ strict PRE-gate:**  ¥   Ç ∏  Ç µ   Ç æ ≤ ñ  ¥   Ω ñ  ¥ ª è CVaR/online,  ≤ ∏       ≤ ∏ Ç ∏  à ª è Ö ∏ ‚ úruns/last‚ ù,  ∑ º µ Ω à ∏ Ç ∏ ‚ úflaky‚ ù  ∫ æ Ω Ç É   ∏ (timeouts/   µ Ç     ó).

---

###  ï Ç     S7. Staging ‚Üí Live ( ∫ µ   æ ≤   Ω ∏ π  ≤ ∏ Ö ñ ¥)

** ¶ ñ ª å:**  æ ± º µ ∂ µ Ω æ  ≤ ∫ ª é á ∏ Ç ∏  ≤ ∏ ∫ æ Ω   Ω Ω è  ∫ æ º   Ω ¥ (CommandBridge) ‚Üí staging;  ¥   ª ñ ‚ î ** ∫ µ   æ ≤   Ω ∏ π live**.

** ö   æ ∫ ∏:**

* [ ]  í º ∏ ∫   Ç ∏  ¥ ñ é  ∫ æ º   Ω ¥    æ whitelist (safe list)  ñ rate-limit.
* [ ] Snapshots    æ ª ñ Ç ∏ ∫  â æ ¥ µ Ω Ω æ; rollback      ∏  ¥ µ ≥     ¥   Ü ñ ó SLO.

**DoD:**

* [ ] Staging PASS:    Ç   ± ñ ª å Ω ∏ π TS  ñ AG, LTL=0,  ñ Ω Ü ∏ ¥ µ Ω Ç ñ ≤=0.
* [ ] Live PASS:  ∫ æ Ω Ç   æ ª å æ ≤   Ω µ    æ ∑ à ∏   µ Ω Ω è    µ   ∏ º µ Ç    .

** ° ∫ ª   ¥ Ω æ â ñ:**

* ** û   Ü ∏ ª è Ü ñ ó      ∏    ≥   µ   ∏ ≤ Ω æ º É  Ç é Ω µ   ñ:**    ¥     Ç ∏ ≤ Ω ñ Œ∑_t,  æ ± º µ ∂ µ Ω Ω è Œî  Ω    ∫   æ ∫, EMA  ∑  ± ñ ª å à æ é  ñ Ω µ   Ü ñ î é.

---

## 4)  Ñ ¥ ∏ Ω    Ç   ± ª ∏ á ∫   DoD ( æ ≥ ª è ¥)

|  ï Ç     |  © æ      º µ  ≥ æ Ç æ ≤ æ                |  û ± æ ≤‚ ô è ∑ ∫ æ ≤ ñ      Ç µ Ñ   ∫ Ç ∏                                                                                 |
| ---- | ----------------------------- | ----------------------------------------------------------------------------------------------------- |
| S0   | Dev/CI  ±   ∑ ∏  , strict warnings | Unit GREEN, `cfg_freeze_pre.*`, `preflight_status.json`, SBOM                                         |
| S1   |  ¢   ∏  º æ   Ç ∏        Ü é é Ç å            | `logs/causal_events.jsonl`,  ≤   ª ñ ¥ Ω ñ  º µ Ç   ∏ ∫ ∏,    µ   µ ≤ ñ   µ Ω ñ  ∫ æ º   Ω ¥ ∏                                       |
| S2   | CA-FSM  ± µ ∑    ¥     Ç   Ü ñ π          | 100+  µ   ñ ∑ æ ¥ ñ ≤ sandbox, 0  ∫   ∏ Ç ∏ á Ω ∏ Ö    æ º ∏ ª æ ∫                                                            |
| S3   | AG & Evaluator                | `logs/ag_eval.jsonl`,    µ   ñ ó \bar{AG},  É ≤ ñ º ∫ Ω µ Ω ∏ π  Ç é Ω µ   ( ± µ ∑ LTL    æ   É à µ Ω å)                             |
| S4   | Proof Kernel                  | `logs/proof_record.jsonl`,  ≤ ñ ¥ Ö ∏ ª µ Ω Ω è  Ω µ ± µ ∑   µ á Ω ∏ Ö  æ Ω æ ≤ ª µ Ω å                                            |
| S5   | DoD- º   à ∏ Ω ∫                     | `reports/R2_DOD_*.md`, `sbom_*`, `acceptance_*`, `strict_gate_events.jsonl`, `R2_FULL_PASS_OK_*.flag` |
| S6   | 72h Shadow                    | `R2_72H_READY=YES`, Acceptance READY                                                                  |
| S7   | Staging/Live                  | TS/AG    Ç   ± ñ ª å Ω ñ, LTL=0, snapshots/rollback                                                            |

---

## 5)  î   Ω ñ  Ç    ∫ æ Ω Ç     ∫ Ç ∏ ( º ñ Ω ñ º É º  ¥ ª è    Ç     Ç É)

### 5.1. `causal_events.jsonl` ( ≤ ∏ ≤ ñ ¥ EventBridge)

```json
{"t":"2025-09-10T19:02:01Z","domain":"execution","event":"ORDER_FILLED","from":"OPEN","to":"OPEN","ctx":{"symbol":"BTCUSDT","qty":0.1},"m":{"pnl_delta":0.0032,"latency_ms":52}}
```

### 5.2.  ú µ Ç   ∏ ∫ ∏ (MetricBridge)

```json
{"pnl": 0.012, "cvar": 0.18, "latency_ms": 47, "drawdown": 0.06}
```

### 5.3.  ö æ º   Ω ¥ ∏ (CommandBridge)

```json
{"domain":"execution","command":"rebalance","params":{"target_risk":0.7}}
```

** í ∏ º æ ≥ ∏:** idempotency key, rate-limit, dry-run/shadow          æ   µ Ü å.

---

## 6) Axial Gradient (AG) ‚ î    Ç     Ç æ ≤    Ñ æ   º É ª  

```
AG = w_p * norm(PnL) + w_c * (œÑ_cvar - norm(CVaR))_+ + w_s * (1 - norm(Stability)) + w_l * (œÑ_lat - norm(Latency))_+
```

*  ù      Ç     Ç ñ ‚ î **PnL- Ü µ Ω Ç   ∏ á Ω  ** (w_p  Ω   π ± ñ ª å à µ).
* **EMA**    æ ≤ µ   Ö  µ   ñ ∑ æ ¥ ñ ≤; Hoeffding  ≤ ∏ ∑ Ω   á   î,  á ∏  ¥ æ   Ç   Ç Ω å æ  ≤ ∏ ± ñ   æ ∫  ¥ ª è  ∑ º ñ Ω ∏ \theta.
*  ó º ñ Ω    ≤   ≥ ‚ î ** á µ   µ ∑  Ç é Ω µ  **,  Ω µ    É ∫   º ∏.

---

## 7) CI/CD  ñ    µ     æ ¥ É ∫ Ç ∏ ≤ Ω ñ   Ç å

* **Unit (strict):** Deprecation/Runtime ‚Üí error, pytest-asyncio    ñ ¥ ∫ ª é á µ Ω æ ( ± µ ∑  ∫ æ Ω Ñ ñ ≥-warning).
* **Artifacts:** `reports/*`, `logs/hybrid/*`  ∑   ≤ ∂ ¥ ∏  ≤   Ω Ç   ∂   Ç å   è  É CI.
* **Freeze/SBOM:**  Ω   preflight  Ç        ∏  ∫ æ ∂ Ω æ º É ‚ úrelease candidate‚ ù.
* **Run-ID  ≤ DoD:**  ¥ ª è  Ç       É ≤   Ω Ω è      Ç µ Ñ   ∫ Ç ñ ≤  ñ acceptance.

---

## 8)  † ∏ ∑ ∏ ∫ ∏  π  è ∫  ó Ö  ≥     è Ç å

* **Windows path  º ñ ∫   ∏:**  Ç ñ ª å ∫ ∏ `pathlib`,  É  Ç µ   Ç   Ö ‚ î  ∫ æ Ω Ç   æ ª å æ ≤   Ω ñ root/env.
* **Heavy deps:**  É unit ‚ î  à ∏ º ∏/lazy;  É  ñ Ω Ç µ ≥     Ü ñ ó ‚ î    µ   ª å Ω ñ      ∫ µ Ç ∏.
* **‚ ú ì æ π ¥   Ω Ω è‚ ù    æ ª ñ Ç ∏ ∫:** Œ∑_t  ∑ º µ Ω à É î Ç å   è,  ∫   æ ∫  æ ± º µ ∂ µ Ω ∏ π,  æ Ω æ ≤ ª µ Ω Ω è  Ω µ  á     Ç ñ à µ K/ ≥ æ ¥.
* ** • ∏ ± Ω    ∫   É ∑   ª å Ω ñ   Ç å:**  Ç µ   Ç-A/B,  ñ Ω   Ç   É º µ Ω Ç   ª å Ω ñ  ∑ º ñ Ω Ω ñ,    µ ≥ É ª è   ∏ ∑   Ü ñ è.

---

## 9)  ü ª   Ω  º ñ ≥     Ü ñ ó (   µ ∫ æ º µ Ω ¥ æ ≤   Ω ∏ π)

1. ** ë   ∑    ≤ B (     æ   Ç ∏ π vFoundation):** S0‚ÜíS4 (Bridges, CA-FSM, AG, Proof Kernel).
2. **72h Shadow  É B:** S5‚ÜíS6 (DoD, acceptance,  ≥ æ Ç æ ≤ Ω ñ   Ç å).
3. ** ü µ   µ Ω µ   µ Ω Ω è  ∫     ∫     É  ≤ A:**  ∑   º ñ Ω    ª æ ∫   ª å Ω ∏ Ö glue  Ω      Ç   Ω ¥     Ç Ω ñ bridges; reuse Proof Kernel;    Ç è ≥ É ≤   Ω Ω è DoD.
4. ** ° Ç µ π ¥ ∂ ∏ Ω ≥  É A ‚Üí Live:**  ∑  Ç ∏ º  ∂ µ checklist.

---

## 10)  ö æ º   Ω ¥ ∏ ( ∫ æ   ∏   Ω ñ    ñ ¥ ∫   ∑ ∫ ∏)

```bash
# Unit strict ( ª æ ∫   ª å Ω æ)
pytest -q -W error::DeprecationWarning -W error::RuntimeWarning --maxfail=1

#  ü   µ Ñ ª   π Ç
python tools/r2_hybrid_stage.py start --ensure-cfg --mode ab --out logs/hybrid/preflight_status.json

# DoD / Freeze / SBOM / Acceptance ( ¥ µ  Ü µ  î  É      æ î ∫ Ç ñ)
python tools/r2_cfg_freeze.py --config cfg/r2.yaml --out reports/cfg_freeze_pre.yaml --hash-out reports/cfg_freeze_pre.sha256
python tools/r2_sbom.py --out-dir reports/
python tools/r2_dod_report.py --out reports/R2_DOD_$(date -u +%Y%m%dT%H%M%SZ).md

# Wirehead scan
python tools/wirehead_scan.py --fail-on any

# Readiness checker ( ≤ ª     Ω ∏ π)
python tools/r2_readiness_check.py   #  ¥   É ∫ É î R2_72H_READY=YES/NO  ñ  ≤ ñ ¥ ¥   î 0/1
```

---

## 11)  ì æ Ç æ ≤ Ω ñ   Ç å  ¥ æ 72h (Definition of Ready)

* [ ] S0‚ ìS5 DoD  ≤ ∏ ∫ æ Ω   Ω ñ; acceptance READY; strict gates PASS.
* [ ] Proof Kernel  ± ª æ ∫ É î  Ω µ ± µ ∑   µ á Ω ñ    ¥     Ç   Ü ñ ó; checksum-gate  É ≤ ñ º ∫ Ω µ Ω æ.
* [ ]  ú æ Ω ñ Ç æ   ∏ Ω ≥ heartbeat/lock;    æ Ç   Ü ñ è  ª æ ≥ ñ ≤;    ª µ   Ç ∏  Ω   CRITICAL.
* ** § æ   º É ª  :**  ∫ æ ª ∏ `r2_readiness_check.py` ‚Üí `R2_72H_READY=YES` ** Ç  ** acceptance READY,  ¥ æ ∑ ≤ æ ª µ Ω æ    Ç     Ç.

---

## 12)  © æ    ≤ Ç æ º   Ç ∏ ∑ É î º æ Copilot‚ ô æ º    µ   à ∏ º ∏ ( æ   µ     Ü ñ π Ω ∏ π      ∏   æ ∫)

1.  ° Ç ≤ æ   ∏ Ç ∏ `foundation/meta_fsm/adapters/{event,metric,command}_bridge.py` (   ∫ µ ª µ Ç ∏  ∑  ≤ ∏ â µ).
2.  î æ ¥   Ç ∏  ≤ ∏ ∫ ª ∏ ∫ ∏ `emit_event()`  É  ∫ ª é á æ ≤ ñ  Ç æ á ∫ ∏  ¥ æ º µ Ω ñ ≤ (execution/risk/data_provider).
3.  ü æ   Ç   ≤ ∏ Ç ∏ `axial_gradient.py`  ñ `evaluator.py` (EMA + Hoeffding;  ± µ ∑  æ Ω æ ≤ ª µ Ω å \theta    µ   à ñ 1‚ ì2  ¥ Ω ñ).
4.  í     æ ≤   ¥ ∏ Ç ∏ `ca_fsm.py`  ∑ yaml- ∫ æ Ω Ñ ñ ≥ æ º  ≥ ≤     ¥ ñ ≤/ ≤   ≥, ** ± µ ∑**    ¥     Ç   Ü ñ π ( Ç ñ ª å ∫ ∏  ∑     ∏  ).
5.  î æ ¥   Ç ∏ Proof Kernel:  º ñ Ω ñ º   ª å Ω ∏ π LTL- Ω   ± ñ   + checksum-gate;  ª æ ≥ É ≤   Ç ∏ `proof_record.jsonl`.
6.  ù   ª   à Ç É ≤   Ç ∏    ∫   ∏   Ç ∏ DoD/Freeze/SBOM/Acceptance,  ¥ æ ¥   Ç ∏ run_id  É DoD.
7.  ü   æ ≤ µ   Ç ∏ **72h shadow** ( °hecker: `R2_72H_READY=YES`).
8.  ü µ   µ Ω µ   Ç ∏  ∫     ∫      É    ∫ ª   ¥ Ω ñ à ∏ π    µ   æ ∑ ∏ Ç æ   ñ π A.

---

## 13)  í ∏   Ω æ ≤ æ ∫

* ** ú æ   Ç ∏**    æ ± ª è Ç å  ¥ æ º µ Ω ∏ ‚ ú ≤ ∏ ¥ ∏ º ∏ º ∏‚ ù  ¥ ª è LLA.
* **CA-FSM**  Ω   ¥   î    ª     Ç ∏ á Ω ñ   Ç å    æ ≤ µ ¥ ñ Ω ∫ ∏  ± µ ∑  Ö   æ   É ‚ î    ¥     Ç É î º æ **         º µ Ç   ∏**    ñ ¥  ∫ æ Ω Ç   æ ª µ º  ñ Ω ≤     ñ   Ω Ç ñ ≤.
* **Proof Kernel**  ≥       Ω Ç É î  ∫ æ Ω   ∏   Ç µ Ω Ç Ω ñ   Ç å; **DoD- º   à ∏ Ω ∫  ** ‚ î  ≤ ñ ¥ Ç ≤ æ   é ≤   Ω ñ   Ç å  ñ  Ç       æ ≤ Ω ñ   Ç å.
* **72h Shadow** ‚ î  Ω   à    ª ñ Ω ñ è  æ ± æ   æ Ω ∏    µ   µ ¥ staging/live.





---

#  ü ª   Ω  ∑     É   ∫ É LLA ‚áÜ vFoundation  ≤ Olimp_v1 ( ¥ æ ‚ ú72h READY‚ ù)

## 0)  ° Ç     Ç µ ≥ ñ è  ñ Ω Ç µ ≥     Ü ñ ó (   ñ à µ Ω Ω è)

* ** ¶ ñ ª å æ ≤ ∏ π    µ   æ ∑ ∏ Ç æ   ñ π:**  Ç æ π,  â æ ‚ ú     æ   Ç ñ à ñ π‚ ù,    ª µ ** ≤ ∂ µ        Ü é î  Ω   testnet**  ñ    æ ± É ¥ æ ≤   Ω ∏ π  Ω   vFoundation ( ¥ æ º µ Ω ∏  ≤ ∂ µ  ≤ ∏ ¥ ñ ª µ Ω ñ).  ¶ µ  ¥     Ç å  Ω   π à ≤ ∏ ¥ à ∏ π        ∫ Ç ∏ á Ω ∏ π    µ ∑ É ª å Ç   Ç.
* ** ü ñ ¥ Ö ñ ¥:**    µ   µ Ω æ   ∏ º æ  ª ∏ à µ **   æ Ç   ñ ± Ω ñ  ≤ É ∑ ª ∏ LLA** ( æ   ∫ µ   Ç     Ü ñ è/ ≥ µ π Ç ∏/ à     ∏)  ñ  æ ¥     ∑ É  æ ± ≥ æ   Ç   î º æ  ≤    Ç   É ∫ Ç É   É vFoundation.  í   µ  ñ Ω à µ  ¥ æ   ∏   É î º æ  ª µ ≥ ∫ ∏ º ∏    ¥     Ç µ     º ∏.
* ** û   Ω æ ≤    É       ≤ ª ñ Ω Ω è:** LLA  ≤ ∏   Ç É     î  è ∫ **Meta-FSM / CA-FSM**, ‚ ú º æ ∑ æ ∫  Ω   ¥  ¥ æ º µ Ω   º ∏‚ ù (execution, risk, data_provider).  í µ   å    É Ö  ñ ¥ µ  á µ   µ ∑ Bridges.

---

## 1) Sprint A ‚ î Bridges ( Ω µ   ≤ æ ≤      ∏   Ç µ º  )

###  ° Ç ≤ æ   ∏ Ç ∏    Ç   É ∫ Ç É   É

```
foundation/
  adapters/
    event_bridge.py
    metric_bridge.py
    command_bridge.py
  meta_fsm/
    ca_fsm.py            #    æ ∫ ∏  º ñ Ω ñ º   ª å Ω ∏ π  ∫     ∫    
  system/
    paths.py             #  è ∫ â æ  Ω µ º   ‚ î  Ü µ Ω Ç     ª ñ ∑ É î º æ  Ç É Ç
logs/
  causal_events.jsonl
  ag_eval.jsonl
  proof_record.jsonl
```

###  ö æ Ω Ç     ∫ Ç ∏ ( º ñ Ω ñ º É º)

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
    # TODO:    ñ ¥ ∫ ª é á ∏ Ç ∏  ¥ æ  ≤   à ∏ Ö  ¥ æ º µ Ω ñ ≤
    #  ü æ ≤ µ   Ç   î º æ PnL/CVaR/latency/volatility  Ö æ á    ±  É ‚ ú   Ç   ±‚ ù- ≤ ∏ ≥ ª è ¥ ñ
    return {"pnl_delta": 0.0, "cvar": 0.0, "latency_ms": 0, "volatility_ratio": 0.0}
```

**command_bridge.py**

```python
ALLOW = {"execution": {"place_order","cancel_all"}, "risk": {"rebalance"}, "data_provider": {"refresh"}}

def send_command(domain: str, command: str, **params):
    if command not in ALLOW.get(domain, {}):
        return {"ok": False, "err": "denied"}
    # TODO:  ≤ ∏ ∫ ª ∏ ∫  ≤   à æ ≥ æ  ¥ æ º µ Ω É ( Ñ       ¥/   æ   Ç)
    return {"ok": True, "info": {"domain": domain, "command": command, "params": params}}
```

###  Ü Ω   Ç   É º µ Ω Ç É ≤   Ω Ω è  ¥ æ º µ Ω ñ ≤

*  £  ∫ ª é á æ ≤ ∏ Ö  Ç æ á ∫   Ö `execution`, `risk`, `data_provider`  ≤ ∏ ∫ ª ∏ ∫   î º æ `emit_event(...)` (   ñ   ª è  æ ±   æ ± ∫ ∏    ∏ ≥ Ω   ª ñ ≤,    µ   µ ¥/   ñ   ª è  ∫ ª é á æ ≤ ∏ Ö  ¥ ñ π).
*  õ µ ≥ ∫ ∏ π smoke- ª É    Ω   100+    æ ¥ ñ π (sandbox/testrun).

###  ö æ º   Ω ¥ ∏

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

* `logs/causal_events.jsonl`  º ñ   Ç ∏ Ç å ‚â• 50  ∑     ∏   ñ ≤,  Ñ æ   º   Ç  ≤   ª ñ ¥ Ω ∏ π.
* Unit strict ‚ î  ∑ µ ª µ Ω æ.

---

## 2) Sprint B ‚ î CA-FSM ( ∫     ∫    ,  ± µ ∑    ¥     Ç   Ü ñ π)

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
    guard: str     #  ≤ ∏     ∑  É    Ç ∏ ª ñ "signal_confidence > 0.7"
    weight: float  #    æ á   Ç ∫ æ ≤    ≤   ≥  

class CAFSM:
    def __init__(self, transitions, start="IDLE"):
        self.s = start
        self.transitions = transitions

    def step(self, event:str, ctx:dict):
        cand = [t for t in self.transitions if t.from_state==self.s and t.event==event]
        if not cand: return self.s
        t = max(cand, key=lambda x: x.weight)  #    æ ∫ ∏      æ   Ç ∏ π  ≤ ∏ ± ñ  
        # TODO:  æ Ü ñ Ω ∫   guard  ñ ∑ ctx ( ± µ ∑   µ á Ω ∏ π eval/ ñ Ω Ç µ       µ Ç   Ç æ  )
        self.s = t.to_state
        emit_event("meta_fsm","transition",{"from": t.from_state,"event": event,"to": t.to_state})
        return self.s

    def on_tick(self):
        m = collect_metrics()
        emit_event("meta_fsm","metrics",m)
        #    æ ∫ ∏  Ω µ  æ Ω æ ≤ ª é î º æ          º µ Ç   ∏
```

**config/ca_fsm.yaml** (     ∏ ∫ ª   ¥)

```yaml
transitions:
  - { from: IDLE, event: START, to: SCAN, guard: "True", weight: 0.8 }
  - { from: SCAN, event: SIGNAL, to: RISK_CHECK, guard: "signal_confidence > 0.7", weight: 0.8 }
  - { from: RISK_CHECK, event: PASS, to: EXECUTE, guard: "risk_score < 0.5", weight: 0.7 }
  - { from: EXECUTE, event: DONE, to: IDLE, guard: "True", weight: 1.0 }
```

** í ± É ¥ É ≤   Ω Ω è  É  ≤   à `run_r0.py` /  ≥ æ ª æ ≤ Ω ∏ π  Ü ∏ ∫ ª:**

*  Ü Ω ñ Ü ñ   ª ñ ∑ É î º æ `CAFSM`  ∑ ñ    Ç     Ç æ ≤ æ ≥ æ    Ç   Ω É.
*  ù    ∫ æ ∂ Ω ñ π    æ ¥ ñ ó  ≤ ñ ¥  ¥ æ º µ Ω ñ ≤ ‚ î  ≤ ∏ ∫ ª ∏ ∫   î º æ `fsm.step(event, ctx)`.
*  ù   timer/heartbeat ‚ î `fsm.on_tick()`.

### DoD (B)

* FSM ‚ ú Ö æ ¥ ∏ Ç å‚ ù    æ  º ñ Ω ñ º   ª å Ω æ º É    Ü µ Ω     ñ é (IDLE‚ÜíSCAN‚ÜíRISK_CHECK‚ÜíEXECUTE‚ÜíIDLE),    æ ¥ ñ ó    ∏ à É Ç å   è  É `causal_events.jsonl`.
*  ù µ º   î      ¥ ñ Ω å/ ± ª æ ∫ É ≤   Ω å.

---

## 3) Sprint C ‚ î Axial Gradient (PnL- Ü µ Ω Ç   ∏ á Ω ∏ π) + Evaluator ( ± µ ∑  æ Ω æ ≤ ª µ Ω å)

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

 í ∏ ∫ ª ∏ ∫   Ç ∏ `eval_once()`  É  Ç   π º µ   ñ FSM.

### DoD (C)

* `logs/ag_eval.jsonl`  º   î  ∑     ∏   ∏; **ag**  Ω µ NaN/inf;    æ ∑   æ ¥ ñ ª    µ   ª ñ   Ç ∏ á Ω ∏ π ( º æ ∂ µ  ± É Ç ∏ ~0  Ω      Ç     Ç ñ).
* Unit strict ‚ î  ∑ µ ª µ Ω æ.

---

## 4) Sprint D ‚ î Proof Kernel (LTL  º ñ Ω ñ º É º + checksum-gate)

**proof_kernel/ltl_invariants.yaml** ( º ñ Ω ñ º   ª å Ω ∏ π    Ç     Ç)

```yaml
safety:
  - "G ! duplicate_entry"     #  Ω ñ ∫ æ ª ∏  Ω µ    æ ¥ ≤ ñ π Ω ∏ π submit
  - "G (OPEN -> F BRACKETS)"  #  è ∫ â æ  ≤ ñ ¥ ∫   ∏ ª ∏ ‚ î  º   é Ç å  ∑‚ ô è ≤ ∏ Ç ∏   å  ±   µ ∫ µ Ç ∏
```

**proof_kernel/ltl_shield.py** ‚ î      æ   Ç ∏ π  º æ Ω ñ Ç æ   ( ª µ ≥ ∫ ñ        ≤ ∏ ª  ,  É Ω ñ Ç     Ω ñ    µ   µ ≤ ñ   ∫ ∏  Ç      ),    ª é  :
**proof_kernel/ontological_checksum.py**

```python
def checksum_ok(proposal: dict, P=97, c=4):
    s = json_dumps_canon(proposal)  #  ∫   Ω æ Ω ñ ∑ É ≤   Ç ∏  ∫ ª é á ñ/   è ¥ ∫ ∏
    return (hash(s) % P) == c
```

 ü ñ ¥ ∫ ª é á ∏ Ç ∏    µ   µ ¥  ± É ¥ å- è ∫ ∏ º ‚ úapply_guard_update‚ ù.

### DoD (D)

*  ü æ   É à µ Ω Ω è safety  Ç µ   Ç æ º ‚Üí ‚ údenied‚ ù  É `proof_record.jsonl`.
*  ö æ   µ ∫ Ç Ω ñ  æ Ω æ ≤ ª µ Ω Ω è ( ∫ æ ª ∏  ∑‚ ô è ≤ ª è Ç å   è) ‚Üí ‚ úaccepted‚ ù.

---

## 5) Sprint E ‚ î  ü ñ ¥ º ñ à   Ç ∏ LLA  ≤ É ∑ ª ∏ ( º ñ Ω ñ º   ª å Ω æ  Ω µ æ ± Ö ñ ¥ Ω µ)

 ü µ   µ Ω æ   ∏ º æ ** Ç ñ ª å ∫ ∏**  Ç µ,  â æ    µ   ª å Ω æ  ¥   î  Ü ñ Ω Ω ñ   Ç å  ∑       ∑:

* `tools/r2_hybrid_stage.py`, `tools/r2_readiness_check.py`, `tools/r2_cfg_freeze.py`, `tools/r2_sbom.py`, `tools/r2_dod_report.py`, `tools/r2_full_pass_gate.py`, `tools/r2_all_gates.py`, `tools/r2_cfg_guard.py`, `tools/cfg_patch_defaults.json`.
* `living_latent/r2/hybrid/ltl_shield.py` ‚Üí  è ∫  Ω   ¥ ± É ¥ æ ≤    Ω   ¥  Ω   à ∏ º  º ñ Ω ñ º   ª å Ω ∏ º PK ( è ∫ â æ  Ö æ á µ à);    ± æ  ∑   ª ∏ à   î º æ  Ω   à  º ñ Ω PK  Ω      µ   à ∏ Ö 2        ∏ Ω Ç ∏.
* ( û   Ü ñ π Ω æ,    ñ ∑ Ω ñ à µ) `pipeline.py`, `conf_gate.py`, `dro_gate.py` ‚ î ** Ç ñ ª å ∫ ∏**  è ∫ â æ    æ Ç   ñ ± µ Ω  ó Ö Ω ñ π  Ñ É Ω ∫ Ü ñ æ Ω   ª  ñ  º ∏  ≥ æ Ç æ ≤ ñ  ¥ æ  à ∏ º    ≤   ∂ ∫ ∏ Ö  ∑   ª µ ∂ Ω æ   Ç µ π.

 ü     ≤ ∏ ª æ: ** ∂ æ ¥ Ω ∏ Ö hard-deps**  É unit- Ü ∏ ∫ ª ñ.  í   µ  ≤   ∂ ∫ µ ‚ î  ∑    Ñ ª   ≥   º ∏/ º     ∫ µ   æ º `@pytest.mark.integration`  ñ  á µ   µ ∑  à ∏ º ∏/lazy-imports ( è ∫  º ∏    æ ± ∏ ª ∏      Ω ñ à µ).

### DoD (E)

*  ü   µ Ñ ª   π Ç  ∑ `tools/r2_hybrid_stage.py` ‚Üí **OK**,      Ç µ Ñ   ∫ Ç ∏  Ω    º ñ   Ü ñ.
* Readiness check ‚Üí `R2_72H_READY=YES`.

---

## 6) Sprint F ‚ î CI/Unit ‚ ústrict‚ ù (   Ç   ± ñ ª å Ω ∏ π baseline)

*  î æ ¥   î º æ workflow  ∑ **strict warnings**  ñ `pytest-asyncio`  É  º   Ç   ∏ Ü ñ (ubuntu/windows √ó 3.10/3.11).
*  ê   Ç µ Ñ   ∫ Ç ∏: `UNIT_TEST_LOG.txt`, freeze, sbom, DoD.

### DoD (F)

* Unit  º   Ç   ∏ Ü è **GREEN**;      Ç µ Ñ   ∫ Ç ∏  ≤ Actions.

---

## 7) Sprint G ‚ î 72h Shadow

*  ó     É   ∫  É **shadow-   µ ∂ ∏ º ñ** ( ∫ æ º   Ω ¥ ∏  ≤  ª æ ≥,  ± µ ∑    µ   ª å Ω ∏ Ö side-effects).
*  ú æ Ω ñ Ç æ   ∏ º æ heartbeat/lock, causal_events, ag_eval, proof_record;  ≥ µ Ω µ   É î º æ acceptance/DoD  ∑      æ ∑ ∫ ª   ¥ æ º.

###  ö æ º   Ω ¥ ∏ (     ∏ ∫ ª   ¥)

```bash
python tools/r2_hybrid_stage.py start --ensure-cfg --mode ab --out logs/hybrid/preflight_status.json
python tools/r2_readiness_check.py   #  æ á ñ ∫ É î º æ R2_72H_READY=YES
#  ¥   ª ñ ‚ î  ∑     É   ∫ shadow- Ü ∏ ∫ ª   ( ≤   à runner),  ª æ ≥  É logs/hybrid/run_stdout.log
```

### DoD (G)

* `R2_72H_READY=YES`, Acceptance READY, 0 CRITICAL, LTL-   æ   É à µ Ω å  Ω µ º   î.

---

##  † ∏ ∑ ∏ ∫ ∏  Ç    è ∫  ∑   ∫   ∏ ≤   Ç ∏

* **Windows    É Ç ∏/‚ úruns\runs/last‚ ù** ‚Üí  Ç ñ ª å ∫ ∏ `pathlib`  É `foundation/system/paths.py`;  æ ∫   µ º ñ  Ç µ   Ç ∏  Ω    Ü µ ( º ∏  ó Ö  ¥ æ ¥   º æ).
* ** § ª   ∫ ∏ PRE- ≥ µ π Ç ñ ≤** (   æ   æ ∂ Ω ñ  º µ Ç   ∏ ∫ ∏ CVaR/obs) ‚Üí  É shadow    Ç ≤ æ   é î º æ  º ñ Ω ñ º   ª å Ω ñ ‚ ú   Ω     à æ Ç ∏‚ ù/   É   æ ≥   Ç Ω ñ  º µ Ç   ∏ ∫ ∏,  â æ ± PRE  Ω µ      ¥   ≤  ≤ ñ ¥    É   Ç æ ≥ æ  ≤ Ö æ ¥ É.
* ** û   Ü ∏ ª è Ü ñ ó      ∏  Ç é Ω µ   ñ** ‚Üí    æ ∫ ∏ ** ≤ ∏ º ∫ Ω É Ç æ**;      æ á   Ç ∫ É  ∑ ± ∏     î º æ      ∏ á ∏ Ω Ω ∏ π    ª ñ ¥  ñ AG,  ª ∏ à µ    æ Ç ñ º  ≤ º ∏ ∫   î º æ  Ω    æ ¥ Ω æ º É    æ   æ ∑ ñ  ∑ Hoeffding-   æ   æ ≥   º ∏.
* ** í   ∂ ∫ ñ  ∑   ª µ ∂ Ω æ   Ç ñ** ‚Üí  ≥ µ Ç å  ñ ∑ unit;  ≤   µ  ≤   ∂ ∫ µ ‚ î  ∑    ñ Ω Ç µ ≥     Ü ñ π Ω ∏ º  º     ∫ µ   æ º +  à ∏ º.

---

##  © æ  æ Ç   ∏ º   î º æ    ñ   ª è Sprint G

* LLA  ∫ µ   É î **Meta-FSM / CA-FSM**    æ ≤ µ   Ö  ≤   à ∏ Ö  ¥ æ º µ Ω ñ ≤.
*  Ñ **     ∏ á ∏ Ω Ω ∏ π    ª ñ ¥** (causal_events), **AG- æ Ü ñ Ω ∫  **  ñ **Proof Kernel** ( º ñ Ω ñ º É º safety).
* CI green,  ±   ∑ æ ≤ ñ    µ ª ñ ∑ Ω ñ      Ç µ Ñ   ∫ Ç ∏,  ñ **   ∏   Ç µ º    ≥ æ Ç æ ≤    ¥ æ 72h shadow**.

---

##  § ñ Ω   ª å Ω µ:  ∫ æ º   Ω ¥    ¥ ª è ‚ ú72h  ≥ æ Ç æ ≤ ñ  ¥ æ  ∑     É   ∫ É‚ ù

 ü ñ   ª è  Ç æ ≥ æ  è ∫      æ π ¥ µ à Sprints A‚ ìF  ñ `python tools/r2_readiness_check.py`  ≤ ∏ ¥   É ∫ É î `R2_72H_READY=YES`,  ∑     É   ∫ shadow- Ü ∏ ∫ ª É ( É  ≤   à æ º É      Ω Ω µ   ñ)  ≤ ≤   ∂   î º æ    Ç     Ç æ º ‚ ú72  ≥ æ ¥ ∏ Ω‚ ù.

---



---

#  í ê † Ü ê ù ¢ A ‚ î ‚ ú ≤ ñ ∑ å º ∏  ≥ æ Ç æ ≤ ñ  Ñ   π ª ∏  ∑ LLA‚ ù ( º ñ Ω ñ º   ª å Ω ∏ π    æ   Ç)

 û Ü µ  Ç µ,  â æ ** ¥ æ   Ç   Ç Ω å æ    µ   µ Ω µ   Ç ∏**  ∑ LLA  ≤  Ç ≤ ñ π      æ î ∫ Ç,  â æ ± LLA- à      Ω   ∫   ∏ ≤  Ç ≤ ñ π r0- æ   ∫ µ   Ç     Ç æ    ñ  º ∏  ∑     É   Ç ∏ ª ∏ CA-FSM + 72h Shadow:

1. **tools/**

* `r2_hybrid_stage.py` ‚ î  ∑     É   ∫/ æ   ∫ µ   Ç     Ç æ      Ç   ¥ ñ π (preflight, shadow, acceptance).
* `r2_readiness_check.py` ‚ î  ñ Ω Ç µ ≥   æ ≤   Ω ∏ π  á µ ∫ µ  ,  è ∫ ∏ π  ¥   î  æ ¥ Ω æ ∑ Ω   á Ω ∏ π          æ   `R2_72H_READY=YES/NO`.
* `r2_cfg_guard.py` + `cfg_patch_defaults.json` ‚ î    ≤ Ç æ     Ç á  ñ  ≤   ª ñ ¥   Ü ñ è `cfg/r2.yaml`.
* `r2_cfg_freeze.py` ‚ î freeze  ∫ æ Ω Ñ ñ ≥ ñ ≤ (yaml + sha256).
* `r2_sbom.py` ‚ î SBOM/ ñ Ω ≤ µ Ω Ç      ∑   ª µ ∂ Ω æ   Ç µ π.
* `r2_all_gates.py`, `r2_full_pass_gate.py`, `r2_dod_report.py` ‚ î    Ç   æ ≥ ñ  ≥ µ π Ç ∏,    ñ à µ Ω Ω è ‚ úGO/NO-GO‚ ù, DoD- ∑ ≤ ñ Ç.

2. **foundation/hybrid/**

* `stage_orchestrator.py` ‚ î  Ü ∏ ∫ ª    Ç   ¥ ñ π +  Ç   π º ñ Ω ≥ ∏ +      Ç µ Ñ   ∫ Ç ∏.
* `pi_bridge.py` ‚ î  ª ñ º ñ Ç/ ± é ¥ ∂ µ Ç    ñ à µ Ω å (policy interface, rate/latency  ± é ¥ ∂ µ Ç ∏).
* `rate_limit.py` ‚ î  Ç æ ∫ µ Ω- ±   ∫ µ Ç/ ¥   æ   µ ª å  ¥ ª è  ∑ º ñ Ω.
* `conf_gate.py`, `dro_gate.py` ‚ î  ∫ æ Ω Ñ ñ ≥ É     Ü ñ π Ω ñ/   æ ±     Ç Ω ñ  ≥ µ π Ç ∏ ( ¥ µ Ç µ ∫ Ç É é Ç å  Ω µ ± µ ∑   µ á Ω ñ  ∑ º ñ Ω ∏).

3. **foundation/proof_kernel/**

* `ltl_shield.py` ‚ î LTL- º æ Ω ñ Ç æ    ñ checksum-gate ( ± ª æ ∫ É ≤   Ω Ω è ‚ ú Ω µ ± µ ∑   µ á Ω ∏ Ö‚ ù  æ Ω æ ≤ ª µ Ω å).

4. **foundation/system/**

* `paths.py` ‚ î  î ¥ ∏ Ω ∏ π  Ω æ   º   ª ñ ∑   Ç æ    à ª è Ö ñ ≤ (Windows-safe),  â æ ±      ∏ ±     Ç ∏ `runs\runs/last`  ñ    æ ¥ ñ ± Ω ñ  Ñ µ π ª ∏.

5. **cfg/**

* `r2.yaml` ‚ î  ±   ∑ æ ≤    ∫ æ Ω Ñ ñ ≥ É     Ü ñ è    Ç   ¥ ñ π/ ≥ µ π Ç ñ ≤ ( ≤ ñ ¥     ∑ É    ñ   ª è  ∫ æ   ñ é ≤   Ω Ω è      æ ≥   Ω è î à `r2_cfg_guard.py --autofix`).

6. **foundation/hybrid/r0_adapter.py** *( Ω æ ≤ ∏ π  É  Ç ≤ æ î º É    µ   æ)*
    Ç æ Ω ∫ ∏ π    ¥     Ç µ  ,  â æ    Ç     Ç É î  Ç ≤ ñ π `r0_*.py`  á µ   µ ∑ 3  ≥   á ∫ ∏: `r0_on_start/step/stop`.

> ** ü   ∏ º ñ Ç ∫  :**  Ω   ∑ ≤ ∏  ∫   Ç   ª æ ≥ ñ ≤ `foundation/*`  º æ ∂ µ à    µ   µ π º µ Ω É ≤   Ç ∏    ñ ¥    ≤ æ é    Ç   É ∫ Ç É   É ( Ω       ∏ ∫ ª   ¥ `vfoundation/*`).  ì æ ª æ ≤ Ω µ ‚ î  ∑ ± µ   µ ≥ Ç ∏  Ñ É Ω ∫ Ü ñ æ Ω   ª å Ω ñ    æ ª ñ.

---

#  í ê † Ü ê ù ¢ B ‚ î ‚ ú â æ  Ü ñ  Ñ   π ª ∏  º   é Ç å    æ ± ∏ Ç ∏‚ ù ( è ∫ â æ    ∏ à µ à    ≤ æ ó,  ± µ ∑  ∫ æ   ñ é ≤   Ω Ω è)

 ù ∏ ∂ á µ ‚ î ** æ ± æ ≤‚ ô è ∑ ∫ æ ≤ ñ  º æ ¥ É ª ñ  Ç    ó Ö Ω è    æ ª å**.  ú æ ∂ µ à  Ω   ∑ ≤   Ç ∏  ó Ö  è ∫  ∑   ≤ ≥ æ ¥ Ω æ;  ≤   ∂ ª ∏ ≤ æ,  â æ ±  ≤ ∏ ∫ æ Ω É ≤   ª ∏  Ü ñ  ∑   ¥   á ñ.

### 1)  û   ∫ µ   Ç     Ç æ      Ç   ¥ ñ π

* ** © æ    æ ± ∏ Ç å:**  ∑     É   ∫   î      µ Ñ ª   π Ç ‚Üí  Ç ñ Ω å æ ≤ ∏ π    µ ∂ ∏ º ‚Üí acceptance ‚Üí freeze/SBOM ‚Üí DoD.
* **API:** `start(mode: str, out: Path)`, `simulate(ticks: int)`.
* **DoD:**    Ç ≤ æ   é î `logs/hybrid/preflight_status.json`, `acceptance_summary_*.json`, `strict_gate_events.jsonl`.

### 2) Readiness-checker

* ** © æ    æ ± ∏ Ç å:**  á ∏ Ç   î      Ç µ Ñ   ∫ Ç ∏  Ç    ¥   É ∫ É î  æ ¥ Ω æ ∑ Ω   á Ω æ `R2_72H_READY=YES/NO` (exit-code 0/1).
* ** í Ö ñ ¥:** `preflight_status.json`, `acceptance_summary_*.json`, freeze/sha, SBOM.
* **DoD:**  æ ¥ Ω    ∫ æ º   Ω ¥    ¥   î  ≤ ñ ¥   æ ≤ ñ ¥ å;  ñ Ω Ç µ ≥   É î Ç å   è  ≤ CI.

### 3) Config-guard (+    ≤ Ç æ     Ç á)

* ** © æ    æ ± ∏ Ç å:**  ≤   ª ñ ¥   Ç æ  /   ≤ Ç æ   æ   æ ≤ Ω é ≤   á `cfg/r2.yaml` ( ¥ æ ¥   î    µ ∫ Ü ñ é `hybrid.*`,  ¥ µ Ñ æ ª Ç ∏,  á     æ ≤ ñ  ≤ ñ ∫ Ω  ).
* **DoD:**    ñ   ª è  ∑     É   ∫ É ‚ î  ∑   ≤ ∂ ¥ ∏  ≤   ª ñ ¥ Ω ∏ π `r2.yaml`  ± µ ∑    É á Ω æ ≥ æ    µ ¥   ≥ É ≤   Ω Ω è.

### 4) Freeze/SBOM/DoD-   µ   æ   Ç µ   ∏

* ** © æ    æ ± ª è Ç å:**
  freeze ‚ î  ∑ ± µ   ñ ≥   î snapshot  ∫ æ Ω Ñ ñ ≥   + sha256;
  sbom ‚ î  ∑ Ω ñ º   î  ∑   ª µ ∂ Ω æ   Ç ñ;
  dod ‚ î    æ ± ∏ Ç å  ∫ æ   æ Ç ∫ ∏ π  ∑ ≤ ñ Ç ‚ ú â æ  ≤ ∏ ∫ æ Ω   Ω æ  ñ  á æ º É GO/NO-GO‚ ù.
* **DoD:**  Ω   è ≤ Ω ñ  Ñ   π ª ∏  É `reports/` (`cfg_freeze_*.yaml/.sha256`, `sbom_*`, `R2_DOD_*.md`).

### 5) Stage-orchestrator core

* ** © æ    æ ± ∏ Ç å:**  Ü ∏ ∫ ª    Ç   ¥ ñ π (S0‚ ¶Sn),  Ç   π º µ   ∏, heartbeat, file-locks, state- º   à ∏ Ω  ,  ª æ ≥ ñ ∫      æ ≤ Ç æ   Ω ∏ Ö        æ ±.
* **DoD:** `logs/hybrid/.heartbeat`, `stage_state.json`,  ∫ æ   µ ∫ Ç Ω µ  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è    ñ   ª è    µ   Ç     Ç É.

### 6) R0-adapter ( ¥ ≤ ∏ ≥ É Ω)

* ** © æ    æ ± ∏ Ç å:**  ∑     É   ∫   î  Ç ≤ ñ π `r0_*.py`  è ∫    ñ ¥   ∏   Ç µ º É  á µ   µ ∑ 3  ≥   á ∫ ∏:

  * `r0_on_start(ctx)`, `r0_on_step(ctx)`, `r0_on_stop(ctx)`
* **DoD:**  æ ¥ ∏ Ω `step()` =  æ ¥ ∏ Ω ¬´ Ç ñ ∫¬ª    ∏   Ç µ º ∏;  µ Ω ¥ ∂ ñ Ω  Ω µ      ¥   î      ∏    æ º ∏ ª Ü ñ  ¥ æ º µ Ω É ( ñ ∑ æ ª é î  ≤ ∏ Ω è Ç ∫ ∏).

### 7) Bridges ( Ç ≤ æ è ‚ ú ñ ∑ é º ñ Ω ∫  ‚ ù)

* **event_bridge:**    ∏ à µ **causal events**  É `logs/causal_events.jsonl`
  `emit_event(domain, event, payload)`
* **metric_bridge:**  ∑ ± ∏     î PnL/CVaR/latency  ∑  ¥ æ º µ Ω ñ ≤
  `collect_metrics() -> dict`
* **command_bridge:**  ± µ ∑   µ á Ω µ  ≤ ∏ ∫ æ Ω   Ω Ω è  ∫ æ º   Ω ¥  É  ¥ æ º µ Ω ∏ (whitelist + rate-limit)
  `send_command(domain, command, args) -> Result`
* **DoD:**  î ‚â•50 `causal_events`  ∑   smoke-   µ   ñ é; latency/CVaR  Ω µ  Ω É ª ñ.

### 8) Proof-kernel

* ** © æ    æ ± ∏ Ç å:** LTL- º æ Ω ñ Ç æ   + checksum-gate  ¥ ª è  ± ª æ ∫ É ≤   Ω Ω è  Ω µ ± µ ∑   µ á Ω ∏ Ö    µ   µ Ö æ ¥ ñ ≤/     ¥ µ π Ç ñ ≤.
* **API:** `ltl_accepts(trace|proposal) -> bool`, `checksum_ok(proposal) -> bool`.
* **DoD:**      ∏    æ   É à µ Ω Ω ñ ‚ î    æ ¥ ñ è  ± ª æ ∫ É î Ç å   è; `logs/proof_record.jsonl`  º ñ   Ç ∏ Ç å      ∏ á ∏ Ω É.

### 9) Policy-interface (PI-bridge)

* ** © æ    æ ± ∏ Ç å:**  î ¥ ∏ Ω ∏ π  ñ Ω Ç µ   Ñ µ π    ∫ µ   É ≤   Ω Ω è    æ ª ñ Ç ∏ ∫ æ é/   æ   æ ≥   º ∏  ∑ rate-limit/latency-budget.
* **API:** `should_accept_candidate(key, delta, cost, clock) -> (bool, info)`.
* **DoD:**  á     Ç æ Ç    ∑ º ñ Ω  ñ  ± é ¥ ∂ µ Ç  Ω µ    æ   É à É é Ç å   è;  ª æ ≥ ∏ `policy_updates.jsonl`.

### 10) Rate-limit

* ** © æ    æ ± ∏ Ç å:**  Ç æ ∫ µ Ω- ±   ∫ µ Ç,  â æ  ¥   æ   µ ª ∏ Ç å  ∑ º ñ Ω ∏          º µ Ç   ñ ≤  Ç    á     Ç æ Ç É  ∫ æ º   Ω ¥.
* **DoD:**  Ω ñ ∫ æ ª ∏  Ω µ    µ   µ ≤ ∏ â É î K  æ Ω æ ≤ ª µ Ω å/ ≥ æ ¥;  º µ Ç   ∏ ∫ ∏  ≤  ª æ ≥   Ö.

### 11) CA-FSM (Meta-FSM  Ω   ¥  ¥ æ º µ Ω   º ∏)

* ** © æ    æ ± ∏ Ç å:**  ≤ ∏   ñ à É î,  É  è ∫ æ º É    æ   è ¥ ∫ É  ≤ ∏ ∫ ª ∏ ∫   Ç ∏  ¥ æ º µ Ω ∏ (`execution`, `risk`, `data_provider`)  ñ  è ∫ ñ  ¥ ñ ó    æ ± ∏ Ç ∏;      æ á   Ç ∫ É    æ ª ñ Ç ∏ ∫    Ñ ñ ∫   æ ≤   Ω  .
* **API:** `tick(obs)`, `transition(state, event) -> (next_state, action)`.
* **DoD:** smoke 100‚ ì500  Ç ñ ∫i ≤  ± µ ∑      ¥ ñ Ω å; `causal_events.jsonl`  Ω     æ ≤ Ω é î Ç å   è.

### 12) Axial-gradient +    ¥     Ç   Ü ñ ó ( º ñ Ω ñ º   ª å Ω æ)

* ** © æ    æ ± ∏ Ç å:**    µ   µ Ç ≤ æ   é î  º µ Ç   ∏ ∫ ∏  É    ∫   ª è   Ω ∏ π AG (PnL- Ü µ Ω Ç   ∏ á Ω ∏ π) +  ª µ ≥ ∫ ñ  ∑ º ñ Ω ∏    æ   æ ≥ ñ ≤      ∑  Ω   K  ∫   æ ∫ ñ ≤ (** Ç ñ ª å ∫ ∏**  è ∫ â æ Proof-kernel  ¥ æ ∑ ≤ æ ª ∏ ≤).
* **DoD:** `ag_eval.jsonl`  ∑     æ ≤ Ω é î Ç å   è;  ∑ º ñ Ω ∏    ñ ¥ ∫ ñ,  º   ª µ Ω å ∫ ñ,  ± µ ∑  æ   Ü ∏ ª è Ü ñ π.

### 13) Paths helper

* ** © æ    æ ± ∏ Ç å:**  Ω æ   º   ª ñ ∑ É î  ≤   ñ  à ª è Ö ∏ ( æ   æ ± ª ∏ ≤ æ  Ω   Windows): `get_logs_dir()`, `get_runs_dir()`, `ensure_dir()`.
* **DoD:**  ∂ æ ¥ Ω ∏ Ö `runs/runs\last`;  ≤   µ    ñ ¥  î ¥ ∏ Ω ∏ º  ∫ æ   µ Ω µ º.

### 14) Config (`cfg/r2.yaml`)

* ** © æ    æ ± ∏ Ç å:**  æ   ∏   É î    Ç   ¥ ñ ó,  ± é ¥ ∂ µ Ç ∏,  á     Ç æ Ç ∏,  Ç æ á ∫ ∏  ñ Ω Ç µ ≥     Ü ñ ó.
* **DoD:**  ≤   ª ñ ¥ Ω ∏ π    ñ   ª è guard-   ∫   ∏   Ç  ;  æ   ∫ µ   Ç     Ç æ    Ω µ      æ   ∏ Ç å    É á Ω ∏ Ö        ≤ æ ∫.

---

##  © æ ±    Ç     Ç É ≤   Ç ∏      æ   Ç æ  ∑       ∑

1. ** £ r0**  ¥ æ ¥   π  ≥   á ∫ ∏:

```python
def r0_on_start(ctx): ...
def r0_on_step(ctx):  ...
def r0_on_stop(ctx):  ...
```

2. ** ° Ç ≤ æ   ∏**    ¥     Ç µ    ñ  ±   ∏ ¥ ∂ ñ ( Ω   ≤ ñ Ç å  ∑ ñ    Ç É ±   º ∏  º µ Ç   ∏ ∫):

```python
from foundation.hybrid.r0_adapter import R0Engine
e = R0Engine('r0_main'); e.start(); e.step(); e.stop()
```

3. ** ê ± æ**    ∫ æ   ñ é π  Ñ   π ª ∏  ∑  í     ñ   Ω Ç   A,  ¥   ª ñ:

```bash
python tools/r2_cfg_guard.py cfg/r2.yaml --autofix --patch-file tools/cfg_patch_defaults.json
python tools/r2_hybrid_stage.py start --ensure-cfg --mode ab --out logs/hybrid/preflight_status.json
python tools/r2_readiness_check.py   #  º   î  ≤ ∏ ≤ µ   Ç ∏ R2_72H_READY=YES ( ∫ æ ª ∏  ≤   µ  Ω    º ñ   Ü ñ)
```


