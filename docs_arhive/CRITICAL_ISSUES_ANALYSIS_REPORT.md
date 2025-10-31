# Critical Issues Analysis Report

## Introduction

This report provides a detailed analysis of critical issues discovered during the investigation of project logs. The analysis focuses on understanding the root causes of the problems within the codebase.

---

## 1. State Contamination in `DecisionMaking`

**Problem:** Critical data blending ("state contamination") between different trading instruments in the `DecisionMaking` component. The system makes trading decisions for one asset (e.g., BTCUSDT) using risk parameters or market data from another asset (e.g., ETHUSDT).

**Root Cause Analysis:**
The investigation of `apps/reference/domains/decision_making/decision_making.py` confirms that the `DecisionMaking` class uses instance-wide variables `self.latest_features`, `self.latest_risk`, and `self.latest_portfolio` to store the most recent data received from different event streams.

- `on_features()` overwrites `self.latest_features`.
- `on_risk()` overwrites `self.latest_risk`.

These handlers are triggered by events that are symbol-specific. However, the internal state is not segregated by symbol. When `_try_make_decision()` is triggered, it uses whatever data is present in these variables, regardless of which symbol it belongs to. This creates a race condition where a `RISK_ASSESSMENT` event for `BTCUSDT` can be immediately followed by a `FEATURES_CALCULATED` event for `ETHUSDT`, leading `_try_make_decision` to incorrectly combine `ETHUSDT` features with `BTCUSDT` risk data.

**Recommendation:**
Refactor the internal state of `DecisionMaking` to be a dictionary keyed by symbol. For example:
```python
self.state_by_symbol = {
    # "BTCUSDT": {"features": ..., "risk": ..., "portfolio": ...},
    # "ETHUSDT": {"features": ..., "risk": ..., "portfolio": ...}
}
```
Each event handler should update the state for its specific symbol, and `_try_make_decision` should be called with a symbol context to ensure data consistency.

---

## 2. Significant Delay in Event Emission

**Problem:** A significant delay (over 800 ms) was observed between the approval of a trade intent and the actual emission of the `EVT:TRADE_INTENT_PROPOSED` event. This latency means the system acts on stale data.

**Root Cause Analysis:**
The code in `_try_make_decision()` in `decision_making.py` performs several operations after the decision to trade is logically made and logged, but before the event is emitted. These operations include:
1.  Constructing a detailed `why_payload`.
2.  Generating a unique `intent_id` via hashing.
3.  Assembling the final `trade_intent_payload`.
4.  Calling `self.fsm.emit()`.

While individually small, the aggregate time taken for these steps, potentially combined with other factors like system load, logging I/O, or inefficient object creation, can introduce noticeable latency. An 800ms delay is critical in high-frequency trading and can lead to significant slippage.

**Recommendation:**
The event emission should happen as soon as the decision is made. The generation of auxiliary data (like `why_payload` or `intent_id`) should be optimized or, if possible, handled asynchronously if it's not part of the critical path for order execution. The principle should be to emit the event first and handle secondary logging or processing afterwards.

---

## 3. Zero Quantity Order Calculation

**Problem:** The logic for calculating order quantity for high-priced assets (like BTC) results in zero-quantity orders, leading to the rejection of potentially profitable trades.

**Root Cause Analysis:**
The issue lies in the position sizing logic within `_try_make_decision`. The code uses the formula `(qty_raw // lot_step) * lot_step` to adjust the quantity to the required lot size. The `//` operator in Python performs floor division.

For a high-priced asset, the raw calculated quantity (`qty_raw`) can be very small (e.g., `0.000787`). If the `lot_step` is `0.001`, the expression `0.000787 // 0.001` evaluates to `0.0`. Multiplying this by `lot_step` results in a final quantity of `0.0`, which is then correctly rejected for being below the minimum order size. This is a flaw in the rounding logic.

**Recommendation:**
The use of standard floating-point arithmetic for financial calculations is discouraged. The `decimal` module should be used for all price and quantity calculations to ensure precision. The rounding logic should be corrected to use proper rounding functions that respect the `lot_step`, for example, using `Decimal.quantize`.

Corrected Logic Example:
```python
from decimal import Decimal, ROUND_DOWN

lot_step = Decimal("0.001")
calculated_qty = (Decimal(str(qty_raw))).quantize(lot_step, rounding=ROUND_DOWN)
```

---

## 4. Incorrect Event Filtering in `feature_engineering`

**Problem:** The `feature_engineering` component filters out `trade` events, which prevents the correct calculation of the Trade Flow Imbalance (TFI) indicator.

**Root Cause Analysis:**
The `on_market_tick` function in `apps/reference/domains/feature_engineering/feature_engineering.py` contains the following logic:
```python
data_type = payload.get("data_type", "")
if data_type == "trade":
    self.logger.debug("Skipping trade event - using only bookTicker for features")
    # ...
    return
```
This explicitly ignores all incoming trade data. The TFI is a measure of the imbalance between buy and sell volume from actual trades. By filtering these events, the TFI calculation is always based on zero or stale volume data, rendering it useless and corrupting the `signal_score` in the `DecisionMaking` component.

**Recommendation:**
The filter must be removed or modified. The `feature_engineering` component should process both `bookTicker` (for order book features like OBI) and `trade` (for trade-based features like TFI) events. The logic should be updated to aggregate trade volumes and correctly calculate TFI based on the flow of actual trades.

---

## 5. "Blind Spot" and Inefficient Decision Triggers

**Problem:** The `DecisionMaking` component initiates the decision-making process (`_try_make_decision`) upon every single incoming event (`features`, `risk`, `portfolio`), even if the other required data points are stale or not yet present.

**Root Cause Analysis:**
The investigation of `apps/reference/domains/decision_making/decision_making.py` confirms this behavior. Each event handler unconditionally triggers a full decision cycle:
- The `on_features` method calls `self._try_make_decision()` on line **116**.
- The `on_risk` method calls `self._try_make_decision()` on line **137**.
- The `on_portfolio` method calls `self._try_make_decision()` on line **158**.

While the guard clause at the beginning of `_try_make_decision` (lines **230-239**) prevents a decision from being made with incomplete data, this "trigger-on-every-event" approach is highly inefficient. It leads to a large number of redundant, useless processing cycles that consume CPU resources. More critically, it exacerbates the risk of state contamination described in Issue #1, as it constantly creates opportunities for data from different symbols to be partially updated and incorrectly evaluated together.

**Recommendation:**
Refactor the triggering mechanism. Instead of calling `_try_make_decision` from every handler, the handlers should only update the symbol-specific state. A single, more intelligent trigger point should be used. For instance, `_try_make_decision` should only be called from the `on_features` handler, as features are typically the most frequent update and represent the "last piece" of the puzzle needed to make a timely decision. This would ensure that a decision cycle for a symbol is only initiated when fresh market data is available and all other data points (`risk`, `portfolio`) are ready.

---

## 6. Continuous Intent Generation for Open Positions

**Problem:** The system repeatedly generates new trade intents even after a position for a specific symbol is already open. This results in a constant stream of rejections due to the position accumulation protection logic (`POSITION_ACCUMULATION_BLOCKED`).

**Root Cause Analysis:**
The core of the issue lies in the stateless nature of the decision cycle within `apps/reference/domains/decision_making/decision_making.py`. The logic to prevent position accumulation (lines **368-407**) works correctly by blocking new trades in the same direction. However, the component fails to manage its state appropriately after this rejection.

Specifically, after a trade intent is rejected for any reason (including `POSITION_ACCUMULATION_BLOCKED`), the method `self.clear_internal_state()` is called (e.g., on line **406**). This method erases the `self.latest_features` and `self.latest_risk` data. As a result, the component immediately becomes ready to process the next market tick from scratch, re-evaluating the same market conditions and arriving at the same (rejected) conclusion. It lacks a state to signify "a position is open for this symbol, so stop evaluating entry signals and wait for an exit signal."

**Recommendation:**
Implement a more robust state management system within `DecisionMaking`. Instead of clearing the state after every rejection, the component should maintain the state of open positions. When a position is confirmed to be open for a symbol, the decision logic for that symbol should explicitly switch from evaluating "entry" signals to evaluating "exit" or "reversal" signals. This prevents the generation of redundant entry intents and reduces noise in the logs, allowing the system to focus only on valid, actionable opportunities.

. " ü æ ∑ ∏ Ü ñ ó-     ∏ ≤ ∏ ¥ ∏"  á µ   µ ∑  ñ ≥ Ω æ   É ≤   Ω Ω è  á     Ç ∫ æ ≤ ∏ Ö  ≤ ∏ ∫ æ Ω   Ω å
 ü   æ ± ª µ º  : CloseFlowFSM,  ≤ ñ ¥   æ ≤ ñ ¥   ª å Ω ∏ π  ∑      ≤ Ç æ º   Ç ∏ á Ω µ  ∑   ∫   ∏ Ç Ç è    æ ∑ ∏ Ü ñ π  ∑    á     æ º,    ∫ Ç ∏ ≤ É î Ç å   è  Ç ñ ª å ∫ ∏      ∏  æ Ç   ∏ º   Ω Ω ñ    æ ¥ ñ ó FILL  ñ    æ ≤ Ω ñ   Ç é  ñ ≥ Ω æ   É î PARTIAL_FILL.
 õ æ ∫   Ü ñ è:  §   π ª: fsm_close.py,  ö ª    : CloseFlowFSM,  § É Ω ∫ Ü ñ è: handle,  † è ¥ ∫ ∏: ~60-63.
 ù     ª ñ ¥ æ ∫:  Ø ∫ â æ    æ ∑ ∏ Ü ñ è  ≤ ñ ¥ ∫   ∏ ≤   î Ç å   è  á µ   µ ∑  æ ¥ Ω µ    ± æ  ∫ ñ ª å ∫    á     Ç ∫ æ ≤ ∏ Ö  ≤ ∏ ∫ æ Ω   Ω å ( â æ  î  Ω æ   º   ª å Ω ∏ º    ∏ Ω ∫ æ ≤ ∏ º    Ü µ Ω     ñ î º), CloseFlowFSM  ¥ ª è  Ω µ ó  Ω ñ ∫ æ ª ∏  Ω µ    ∫ Ç ∏ ≤ É î Ç å   è.  í    µ ∑ É ª å Ç   Ç ñ,  Ç   π º µ   max_hold_sec  Ω µ  ∑     É   ∫   î Ç å   è,  ñ    ∏   Ç µ º   " Ω µ  ∑ Ω   î"      æ  ñ   Ω É ≤   Ω Ω è  Ü ñ î ó    æ ∑ ∏ Ü ñ ó  ∑  Ç æ á ∫ ∏  ∑ æ   É  É       ≤ ª ñ Ω Ω è  ó ó  ∂ ∏ Ç Ç î ≤ ∏ º  Ü ∏ ∫ ª æ º.  ¢   ∫      æ ∑ ∏ Ü ñ è  ∑   ª ∏ à   î Ç å   è  ≤ ñ ¥ ∫   ∏ Ç æ é  Ω    ± ñ   ∂ ñ  ± µ ∑  ± É ¥ å- è ∫ æ ≥ æ  ∫ æ Ω Ç   æ ª é,  â æ  Ω µ º ∏ Ω É á µ      ∏ ∑ ≤ µ ¥ µ  ¥ æ  ∑ ± ∏ Ç ∫ ñ ≤      ∏  Ω µ       ∏ è Ç ª ∏ ≤ æ º É    É   ñ    ∏ Ω ∫ É.
8. " ° ª ñ      ∑ æ Ω  "  ≤  É       ≤ ª ñ Ω Ω ñ    ∏ ∑ ∏ ∫ æ º  ≤ ñ ¥     ∑ É    ñ   ª è  ≤ ñ ¥ ∫   ∏ Ç Ç è    æ ∑ ∏ Ü ñ ó
 ü   æ ± ª µ º  : ManageFlowFSM,  è ∫ ∏ π  ≤ ñ ¥   æ ≤ ñ ¥   î  ∑    É       ≤ ª ñ Ω Ω è    ∏ ∑ ∏ ∫ æ º  ≤ ñ ¥ ∫   ∏ Ç æ ó    æ ∑ ∏ Ü ñ ó ( Ç   µ π ª ñ Ω ≥-   Ç æ   ∏,    µ   µ ≤ µ ¥ µ Ω Ω è  ≤  ± µ ∑ ∑ ± ∏ Ç æ ∫),    æ á ∏ Ω   î  ∑     Ç æ   æ ≤ É ≤   Ç ∏    ≤ æ ó        ≤ ∏ ª    Ω µ  ≤  º æ º µ Ω Ç  ≤ ñ ¥ ∫   ∏ Ç Ç è    æ ∑ ∏ Ü ñ ó (FILL    ± æ PARTIAL_FILL),     Ç ñ ª å ∫ ∏    ñ   ª è  æ Ç   ∏ º   Ω Ω è  Ω     Ç É   Ω æ ó    æ ¥ ñ ó  æ Ω æ ≤ ª µ Ω Ω è    ∏ Ω ∫ æ ≤ ∏ Ö  ¥   Ω ∏ Ö (UPD).
 õ æ ∫   Ü ñ è:  §   π ª: fsm_manage.py,  ö ª    : ManageFlowFSM,  § É Ω ∫ Ü ñ è: handle,  † è ¥ ∫ ∏: ~80-86.
 ù     ª ñ ¥ æ ∫:  ° Ç ≤ æ   é î Ç å   è  ∫   ∏ Ç ∏ á Ω ∏ π      æ º ñ ∂ æ ∫  á     É,      æ Ç è ≥ æ º  è ∫ æ ≥ æ    æ ∑ ∏ Ü ñ è  î    ±   æ ª é Ç Ω æ  Ω µ ∑   Ö ∏ â µ Ω æ é.  Ø ∫ â æ  ≤ ñ ¥     ∑ É    ñ   ª è  ≤ Ö æ ¥ É  ≤    ∏ Ω æ ∫  ≤ ñ ¥ ± É ¥ µ Ç å   è    ñ ∑ ∫ ∏ π  Ü ñ Ω æ ≤ ∏ π    É Ö      æ Ç ∏    æ ∑ ∏ Ü ñ ó,    ∏   Ç µ º    Ω µ  ≤ ñ ¥   µ   ≥ É î,  æ   ∫ ñ ª å ∫ ∏  ó ó  ª æ ≥ ñ ∫    É       ≤ ª ñ Ω Ω è    ∏ ∑ ∏ ∫ æ º  â µ  Ω µ    ∫ Ç ∏ ≤ Ω  .  ¶ µ  ≥       Ω Ç É î  æ Ç   ∏ º   Ω Ω è  º   ∫   ∏ º   ª å Ω æ ≥ æ  ∑ ± ∏ Ç ∫ É  ≤    ∏ Ç É   Ü ñ è Ö        Ç æ ≤ æ ó  ≤ æ ª   Ç ∏ ª å Ω æ   Ç ñ.
9.  í ñ ¥   É Ç Ω ñ   Ç å  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è    Ç   Ω É FSM  É       ≤ ª ñ Ω Ω è    æ ∑ ∏ Ü ñ è º ∏    ñ   ª è    µ   µ ∑     É   ∫ É
 ü   æ ± ª µ º  :  ú µ Ö   Ω ñ ∑ º  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è    ñ   ª è  ∑ ± æ é (Disaster Recovery)  ∫ æ   µ ∫ Ç Ω æ  ∑   ≤   Ω Ç   ∂ É î    Ç   Ω    æ ∑ ∏ Ü ñ π  É PositionTracking  ∑ ñ  ∑ Ω ñ º ∫  ,    ª µ  Ω µ  ≤ ñ ¥ Ω æ ≤ ª é î  ≤ Ω É Ç   ñ à Ω ñ    Ç   Ω ∏ FSM- º   à ∏ Ω ManageFlowFSM  Ç   CloseFlowFSM.
 õ æ ∫   Ü ñ è:  §   π ª ∏: main.py ( ª æ ≥ ñ ∫    ∑     É   ∫ É), fsm_manage.py, fsm_close.py ( ñ Ω ñ Ü ñ   ª ñ ∑   Ü ñ è    Ç   Ω ñ ≤).
 ù     ª ñ ¥ æ ∫:  ü ñ   ª è    µ   µ ∑     É   ∫ É    ∏   Ç µ º ∏,  Ω        Ö É Ω ∫ É  º æ ∂ É Ç å  ± É Ç ∏  ≤ ñ ¥ ∫   ∏ Ç ñ    æ ∑ ∏ Ü ñ ó,      æ  è ∫ ñ PositionTracking  ∑ Ω   î.  û ¥ Ω   ∫, ManageFlowFSM  ñ CloseFlowFSM  ∑     É   ∫   é Ç å   è  É    ≤ æ î º É    æ á   Ç ∫ æ ≤ æ º É    Ç   Ω ñ FLAT.  í æ Ω ∏  Ω µ "     º' è Ç   é Ç å",  â æ    æ Ç   ñ ± Ω æ  É       ≤ ª è Ç ∏  Ü ∏ º ∏  ≤ ñ ¥ Ω æ ≤ ª µ Ω ∏ º ∏    æ ∑ ∏ Ü ñ è º ∏.  Ø ∫  Ω     ª ñ ¥ æ ∫,  ¥ ª è  ≤   ñ Ö    ∫ Ç ∏ ≤ Ω ∏ Ö  Ω    º æ º µ Ω Ç  ∑ ± æ é  É ≥ æ ¥    æ ≤ Ω ñ   Ç é  ≤ ∏ º ∏ ∫   î Ç å   è  É       ≤ ª ñ Ω Ω è    ∏ ∑ ∏ ∫ æ º:  Ω µ        Ü é é Ç å  Ω ñ    Ç æ  - ª æ   ∏,  Ω ñ  Ç µ π ∫-     æ Ñ ñ Ç ∏,  Ω ñ  ∑   ∫   ∏ Ç Ç è  ∑    á     æ º.  ¶ µ    µ   µ Ç ≤ æ   é î  ≤   ñ    ∫ Ç ∏ ≤ Ω ñ    æ ∑ ∏ Ü ñ ó  Ω    Ω µ ∫ µ   æ ≤   Ω ñ,  â æ  î      è º æ é  ∑   ≥   æ ∑ æ é  ¥ ª è  ∫     ñ Ç   ª É.

 ü   æ ± ª µ º  :  ù µ ± µ ∑   µ á Ω    ñ Ω ñ Ü ñ   ª ñ ∑   Ü ñ è  Ç æ   ≥ æ ≤ æ ≥ æ    ª µ á   (leverage).  ° ∏   Ç µ º    Ω µ  º   î  º µ Ö   Ω ñ ∑ º É    ñ ¥ Ç ≤ µ   ¥ ∂ µ Ω Ω è,  â æ    æ Ç   ñ ± Ω µ    ª µ á µ  ± É ª æ  É     ñ à Ω æ  ≤   Ç   Ω æ ≤ ª µ Ω æ    µ   µ ¥    æ á   Ç ∫ æ º  Ç æ   ≥ ñ ≤ ª ñ,  ñ      æ ¥ æ ≤ ∂ É î    æ ± æ Ç É  ∑    æ Ç µ Ω Ü ñ π Ω æ  Ω µ ≤ ñ   Ω ∏ º ∏          º µ Ç     º ∏.
 õ æ ∫   Ü ñ è:  §   π ª: binance_execution_adapter.py,  § É Ω ∫ Ü ñ è: initialize_margin_settings,  † è ¥ ∫ ∏: ~109-114.
 ù     ª ñ ¥ æ ∫:  Ø ∫ â æ  ≤ ∏ ∫ ª ∏ ∫ API  ¥ ª è  ≤   Ç   Ω æ ≤ ª µ Ω Ω è    ª µ á   (_set_leverage)  ∑   ∑ Ω   î  Ω µ ≤ ¥   á ñ  ∑  ± É ¥ å- è ∫ æ ó      ∏ á ∏ Ω ∏ ( æ ∫   ñ º    æ º ∏ ª ∫ ∏ -4046),    ∏   Ç µ º        æ ¥ æ ≤ ∂ ∏ Ç å    æ ± æ Ç É,    ª µ  ∫ æ º   æ Ω µ Ω Ç DecisionMaking  ± É ¥ µ    æ ∑     Ö æ ≤ É ≤   Ç ∏    æ ∑ º ñ      æ ∑ ∏ Ü ñ ó,  ≤ ∏ Ö æ ¥ è á ∏  ∑    ª µ á  ,  ≤ ∫   ∑   Ω æ ≥ æ  ≤  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó.  † µ   ª å Ω µ    ª µ á µ  Ω    ± ñ   ∂ ñ  º æ ∂ µ  ± É Ç ∏  ñ Ω à ∏ º ( Ω       ∏ ∫ ª   ¥,    Ç   Ω ¥     Ç Ω ∏ º 20 Ö).  ¶ µ      ∏ ∑ ≤ µ ¥ µ  ¥ æ  ≤ ñ ¥ ∫   ∏ Ç Ç è    æ ∑ ∏ Ü ñ ó,  â æ  ≤      ∑ ∏    µ   µ ≤ ∏ â É î    æ ∑     Ö æ ≤   Ω ∏ π    ∏ ∑ ∏ ∫,  ñ  ±   ≥   Ç æ     ∑ æ ≤ æ  ∑ ± ñ ª å à ∏ Ç å  ñ º æ ≤ ñ   Ω ñ   Ç å  ª ñ ∫ ≤ ñ ¥   Ü ñ ó.
 õ   Ω Ü é ≥:
 ü ñ ¥  á      ∑     É   ∫ É initialize_margin_settings  Ω   º   ≥   î Ç å   è  ≤   Ç   Ω æ ≤ ∏ Ç ∏    ª µ á µ 5x  ¥ ª è BTCUSDT.
API Binance    æ ≤ µ   Ç   î  Ç ∏ º á     æ ≤ É    æ º ∏ ª ∫ É ( Ω       ∏ ∫ ª   ¥, 502 Bad Gateway),  è ∫    Ω µ  æ ±   æ ± ª è î Ç å   è      µ Ü ∏ Ñ ñ á Ω æ.  í ∏ ∫ ª ∏ ∫   î Ç å   è logger.error  ñ  Ü ∏ ∫ ª      æ ¥ æ ≤ ∂ É î Ç å   è  ¥ ª è  ñ Ω à ∏ Ö  ñ Ω   Ç   É º µ Ω Ç ñ ≤.
 † µ   ª å Ω µ    ª µ á µ  Ω    ± ñ   ∂ ñ  ¥ ª è BTCUSDT  ∑   ª ∏ à   î Ç å   è 20x.
DecisionMaking  æ Ç   ∏ º É î    ∏ ≥ Ω   ª  ñ    æ ∑     Ö æ ≤ É î    æ ∑ º ñ      æ ∑ ∏ Ü ñ ó,      ∏   É   ∫   é á ∏,  â æ    ª µ á µ  ¥ æ   ñ ≤ Ω é î 5x.
BinanceExecutionAdapter  É     ñ à Ω æ  ≤ ñ ¥ ∫   ∏ ≤   î    æ ∑ ∏ Ü ñ é.  ß µ   µ ∑  Ñ   ∫ Ç ∏ á Ω µ    ª µ á µ 20 Ö,  Ü è    æ ∑ ∏ Ü ñ è  ≤ ∏ è ≤ ª è î Ç å   è  ≤ 4      ∑ ∏  ± ñ ª å à æ é,  Ω ñ ∂    ª   Ω É ≤   ª æ   è,  â æ  ≤ µ ¥ µ  ¥ æ  ∫   Ç     Ç   æ Ñ ñ á Ω ∏ Ö  ∑ ± ∏ Ç ∫ ñ ≤      ∏  Ω   π º µ Ω à æ º É  Ω µ       ∏ è Ç ª ∏ ≤ æ º É    É   ñ  Ü ñ Ω ∏.
 ü   æ ± ª µ º  :  í ∏ ∫ æ   ∏   Ç   Ω Ω è    æ Ç µ Ω Ü ñ π Ω æ  ∑     Ç     ñ ª ∏ Ö  ¥   Ω ∏ Ö      æ  ∫     ñ Ç   ª  ¥ ª è      ∏ π Ω è Ç Ç è  Ç æ   ≥ æ ≤ ∏ Ö    ñ à µ Ω å.
 õ æ ∫   Ü ñ è:  §   π ª: account_connector.py,  ö ª    : AccountConnector,  † è ¥ æ ∫: ~58 (self.update_interval = 30).
 ù     ª ñ ¥ æ ∫:  î   Ω ñ      æ  ±   ª   Ω        Ö É Ω ∫ É  Ç    ≤ ñ ¥ ∫   ∏ Ç ñ    æ ∑ ∏ Ü ñ ó  æ Ω æ ≤ ª é é Ç å   è  ª ∏ à µ      ∑  Ω   30    µ ∫ É Ω ¥.  £    µ   ñ æ ¥ ∏  ≤ ∏   æ ∫ æ ó  ≤ æ ª   Ç ∏ ª å Ω æ   Ç ñ    ± æ    ∫ Ç ∏ ≤ Ω æ ó  Ç æ   ≥ ñ ≤ ª ñ, DecisionMaking  º æ ∂ µ      æ Ç è ≥ æ º  º   π ∂ µ 30    µ ∫ É Ω ¥      ∏ π º   Ç ∏  Ω æ ≤ ñ    ñ à µ Ω Ω è,  ±   ∑ É é á ∏   å  Ω    Ω µ   ∫ Ç É   ª å Ω æ º É  ∑ Ω   á µ Ω Ω ñ equity.  Ø ∫ â æ  ∑    Ü µ π  á      ≤ ñ ¥ ± É ≤   è  ∑ ± ∏ Ç æ ∫,    ∏   Ç µ º    ± É ¥ µ    æ ∑     Ö æ ≤ É ≤   Ç ∏  Ω   ¥ º ñ   Ω æ  ≤ µ ª ∏ ∫ ñ    æ ∑ ∏ Ü ñ ó,  â æ      ∏   ∫ æ   ∏ Ç å  ≤ Ç     Ç ∏ ( µ Ñ µ ∫ Ç "   Ω ñ ≥ æ ≤ æ ó  ∫ É ª ñ").
 ü   æ ± ª µ º  :  ü æ Ç µ Ω Ü ñ π Ω µ  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è  ∑     Ç     ñ ª æ ó  Ü ñ Ω ∏      ∏    æ ∑     Ö É Ω ∫ É  ∫ ñ ª å ∫ æ   Ç ñ (qty).
 õ æ ∫   Ü ñ è:  §   π ª: decision_making.py,  § É Ω ∫ Ü ñ è: _try_make_decision,  † è ¥ ∫ ∏: ~525-531.
 ù     ª ñ ¥ æ ∫:  õ æ ≥ ñ ∫      æ ∑     Ö É Ω ∫ É price_ref  º   î  ∑         Ω ∏ π  ≤     ñ   Ω Ç  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è self.latest_portfolio['last_price'].  û ¥ Ω   ∫,  Ω µ º   î  ∂ æ ¥ Ω æ ó    µ   µ ≤ ñ   ∫ ∏,  Ω     ∫ ñ ª å ∫ ∏ "   Ç     æ é"  î  Ü è  Ü ñ Ω  .  Ø ∫ â æ    æ Ç ñ ∫    ∏ Ω ∫ æ ≤ ∏ Ö  ¥   Ω ∏ Ö (feature_engineering)    µ   µ   ≤ µ Ç å   è,       æ Ç ñ ∫  ¥   Ω ∏ Ö    æ   Ç Ñ µ ª è (position_tracking)      æ ¥ æ ≤ ∂ ∏ Ç å  Ω   ¥ Ö æ ¥ ∏ Ç ∏,    ∏   Ç µ º    º æ ∂ µ    æ ∑     Ö É ≤   Ç ∏  ∫ ñ ª å ∫ ñ   Ç å  ¥ ª è  Ω æ ≤ æ ó  É ≥ æ ¥ ∏,  ≤ ∏ ∫ æ   ∏   Ç æ ≤ É é á ∏  Ü ñ Ω É  ≥ æ ¥ ∏ á Ω æ ó  ¥   ≤ Ω æ   Ç ñ.  ¶ µ      ∏ ∑ ≤ µ ¥ µ  ¥ æ  ≤ ñ ¥ ∫   ∏ Ç Ç è    æ ∑ ∏ Ü ñ ó  ∑    ±   æ ª é Ç Ω æ  Ω µ ≤ ñ   Ω ∏ º  æ ±   è ≥ æ º  ñ  º ∏ Ç Ç î ≤ æ ≥ æ  ∑ ± ∏ Ç ∫ É.
 ü   æ ± ª µ º  :  í ñ ¥   É Ç Ω ñ   Ç å  º µ Ö   Ω ñ ∑ º É "   ≤     ñ π Ω æ ó  ∑ É   ∏ Ω ∫ ∏"      ∏  ∫   ∏ Ç ∏ á Ω ∏ Ö    æ º ∏ ª ∫   Ö API.
 õ æ ∫   Ü ñ è:  §   π ª: account_connector.py,  § É Ω ∫ Ü ñ è: _get_account_info,  † è ¥ ∫ ∏: ~154-156.  §   π ª: binance_execution_adapter.py,  § É Ω ∫ Ü ñ è: _place_binance_order,  † è ¥ ∫ ∏: ~428-430.
 ù     ª ñ ¥ æ ∫:  ü   ∏  æ Ç   ∏ º   Ω Ω ñ  ∫   ∏ Ç ∏ á Ω ∏ Ö    æ º ∏ ª æ ∫  ≤ ñ ¥ API Binance ( Ω       ∏ ∫ ª   ¥,    æ º ∏ ª ∫      ≤ Ç µ Ω Ç ∏ Ñ ñ ∫   Ü ñ ó 401    ± æ    æ º ∏ ª ∫    ¥ æ   Ç É   É 403),  ∫ æ º   æ Ω µ Ω Ç ∏  ª ∏ à µ  ª æ ≥ É é Ç å    æ º ∏ ª ∫ É  ñ      æ ¥ æ ≤ ∂ É é Ç å    æ ± æ Ç É  ≤  à Ç   Ç Ω æ º É    µ ∂ ∏ º ñ.  ° ∏   Ç µ º    Ω µ    µ   µ Ö æ ¥ ∏ Ç å  ≤  ± µ ∑   µ á Ω ∏ π    Ç   Ω ( Ω       ∏ ∫ ª   ¥, " Ç ñ ª å ∫ ∏  ∑   ∫   ∏ Ç Ç è"    ± æ    æ ≤ Ω    ∑ É   ∏ Ω ∫  ).  ¶ µ    Ç ≤ æ   é î    ∏ ∑ ∏ ∫,  â æ DecisionMaking,  Ω µ  æ Ç   ∏ º É é á ∏  æ Ω æ ≤ ª µ Ω å      æ    µ   ª å Ω ∏ π    Ç   Ω      Ö É Ω ∫ É,      æ ¥ æ ≤ ∂ ∏ Ç å  ≥ µ Ω µ   É ≤   Ç ∏  Ç æ   ≥ æ ≤ ñ  Ω   º ñ   ∏,  è ∫ ñ  ± É ¥ É Ç å    ± æ  ≤ ñ ¥ Ö ∏ ª è Ç ∏   è,    ± æ ( ≤  ≥ ñ   à æ º É  ≤ ∏     ¥ ∫ É)  ≤ ∏ ∫ æ Ω É ≤   Ç ∏   è  ∑  Ω µ   µ   µ ¥ ±   á É ≤   Ω ∏ º ∏  Ω     ª ñ ¥ ∫   º ∏,  è ∫ â æ      æ ± ª µ º    ∑ API  Ç ∏ º á     æ ≤  .  ¶ µ      ∏ ∑ ≤ æ ¥ ∏ Ç å  ¥ æ    æ ∑   ∏ Ω Ö   æ Ω ñ ∑   Ü ñ ó    Ç   Ω É  Ç      æ Ç µ Ω Ü ñ π Ω ∏ Ö  ∑ ± ∏ Ç ∫ ñ ≤.

 ê Ω   ª ñ ∑  Ω µ  î  ≤ ∏ á µ     Ω ∏ º.  ü æ ≥ ª ∏ ± ª µ Ω µ  ¥ æ   ª ñ ¥ ∂ µ Ω Ω è  ≤ ∏ è ≤ ∏ ª æ  ¥ æ ¥   Ç ∫ æ ≤ ñ      Ö ñ Ç µ ∫ Ç É   Ω ñ  ¥ µ Ñ µ ∫ Ç ∏,  â æ    Ç ≤ æ   é é Ç å    µ   π æ ∑ Ω ñ  Ñ ñ Ω   Ω   æ ≤ ñ    ∏ ∑ ∏ ∫ ∏.

 ü   æ ¥ æ ≤ ∂ É é  ∑ ≤ ñ Ç.

10.  í ñ ¥   É Ç Ω ñ   Ç å    æ   Ç Ñ µ ª å Ω æ ≥ æ  É       ≤ ª ñ Ω Ω è    ∏ ∑ ∏ ∫   º ∏ (Portfolio-Level Risk Management)

 ü   æ ± ª µ º  :  ö æ º   æ Ω µ Ω Ç RiskManagement        Ü é î  ≤ ∏ ∫ ª é á Ω æ  Ω      ñ ≤ Ω ñ  æ ∫   µ º æ ≥ æ  Ç æ   ≥ æ ≤ æ ≥ æ  ñ Ω   Ç   É º µ Ω Ç É (symbol).  ü æ ≤ Ω ñ   Ç é  ≤ ñ ¥   É Ç Ω è  ª æ ≥ ñ ∫  ,  è ∫    ±  æ Ü ñ Ω é ≤   ª      É ∫ É   Ω ∏ π    ∏ ∑ ∏ ∫    æ  ≤   å æ º É    æ   Ç Ñ µ ª é.

 õ æ ∫   Ü ñ è:  §   π ª: risk_management.py,  ö ª    : RiskManagement.

 ù     ª ñ ¥ æ ∫:  ° ∏   Ç µ º    º æ ∂ µ  æ ¥ Ω æ á     Ω æ  ≥ µ Ω µ   É ≤   Ç ∏    ∏ ≥ Ω   ª ∏  Ω    ≤ ñ ¥ ∫   ∏ Ç Ç è    æ ∑ ∏ Ü ñ π    æ  ∫ ñ ª å ∫ æ Ö  ≤ ∏   æ ∫ æ ∫ æ   µ ª å æ ≤   Ω ∏ Ö    ∫ Ç ∏ ≤   Ö ( Ω       ∏ ∫ ª   ¥, BTC  Ç   ETH),  Ω µ  É   ≤ ñ ¥ æ º ª é é á ∏,  â æ    É ∫ É   Ω ∏ π    ∏ ∑ ∏ ∫    µ   µ ≤ ∏ â É î  ≤   ñ  ¥ æ   É   Ç ∏ º ñ  º µ ∂ ñ.  í ñ ¥   É Ç Ω ñ   Ç å  ª ñ º ñ Ç ñ ≤  Ω    ¥ µ Ω Ω É      æ     ¥ ∫ É (daily drawdown limit)    ± æ    É ∫ É   Ω µ  ∫   µ ¥ ∏ Ç Ω µ    ª µ á µ  æ ∑ Ω   á   î,  â æ    µ   ñ è  ∑ ± ∏ Ç ∫ æ ≤ ∏ Ö  É ≥ æ ¥  Ω µ  ∑ É   ∏ Ω ∏ Ç å    ∏   Ç µ º É,  ñ  ≤ æ Ω        æ ¥ æ ≤ ∂ É ≤   Ç ∏ º µ  Ç æ   ≥ É ≤   Ç ∏  ¥ æ    æ ≤ Ω æ ó  ª ñ ∫ ≤ ñ ¥   Ü ñ ó      Ö É Ω ∫ É.

11.  Ü ª é ∑ ñ è  ñ ¥ µ º   æ Ç µ Ω Ç Ω æ   Ç ñ:  í ñ ¥   É Ç Ω ñ   Ç å  º µ Ö   Ω ñ ∑ º É  ∑     æ ± ñ ≥   Ω Ω è  ¥ É ± ª é ≤   Ω Ω é  æ   ¥ µ   ñ ≤

 ü   æ ± ª µ º  :  • æ á    ≤  ∫ æ ¥ ñ    µ   µ ¥   î Ç å   è idempotent_key,  Ω µ  ñ   Ω É î  ∂ æ ¥ Ω æ ≥ æ  ∫ æ º   æ Ω µ Ω Ç  ,  è ∫ ∏ π  ± ∏  ≤ ñ ¥   Ç µ ∂ É ≤   ≤  ≤ ∏ ∫ æ   ∏   Ç   Ω ñ  ∫ ª é á ñ  Ç    ∑     æ ± ñ ≥   ≤    æ ≤ Ç æ   Ω ñ π  ≤ ñ ¥       ≤ Ü ñ  æ   ¥ µ    .

 õ æ ∫   Ü ñ è:  §   π ª: fsm_open.py,  § É Ω ∫ Ü ñ è: handle.  §   π ª: binance_execution_adapter.py,  § É Ω ∫ Ü ñ è: place_order.

 ù     ª ñ ¥ æ ∫:  ü   ∏  ∑ ± æ ó    ± æ    µ   µ ∑     É   ∫ É    ∏   Ç µ º ∏    ñ   ª è  ≤ ñ ¥       ≤ ∫ ∏  æ   ¥ µ    ,    ª µ  ¥ æ  æ Ç   ∏ º   Ω Ω è    ñ ¥ Ç ≤ µ   ¥ ∂ µ Ω Ω è  ≤ ñ ¥  ± ñ   ∂ ñ,    ∏   Ç µ º          æ ± É î  ≤ ñ ¥       ≤ ∏ Ç ∏  Ç æ π      º ∏ π  æ   ¥ µ    â µ      ∑.  ¶ µ      ∏ ∑ ≤ µ ¥ µ  ¥ æ  ≤ ñ ¥ ∫   ∏ Ç Ç è    æ ¥ ≤ ñ π Ω æ ó    æ ∑ ∏ Ü ñ ó,  â æ    æ ¥ ≤ æ é î    ∏ ∑ ∏ ∫  ñ  î  Ω µ ∫ æ Ω Ç   æ ª å æ ≤   Ω æ é  ¥ ñ î é.

 õ   Ω Ü é ≥:

 ° ∏   Ç µ º    ≥ µ Ω µ   É î CMD:OPEN  ∑  É Ω ñ ∫   ª å Ω ∏ º idempotent_key.

BinanceExecutionAdapter  É     ñ à Ω æ  ≤ ñ ¥       ≤ ª è î  æ   ¥ µ    Ω    ± ñ   ∂ É.

 ° ∏   Ç µ º      µ   µ ∑   ≤   Ω Ç   ∂ É î Ç å   è  ¥ æ  Ç æ ≥ æ,  è ∫ AccountObserver    ± æ  ñ Ω à ∏ π  º µ Ö   Ω ñ ∑ º    ñ ¥ Ç ≤ µ   ¥ ∏ Ç å  ≤ ∏ ∫ æ Ω   Ω Ω è  æ   ¥ µ    .

 ü ñ   ª è    µ   µ ∑     É   ∫ É,  ª æ ≥ ñ ∫    ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è ( è ∫ â æ  ≤ æ Ω    ñ   Ω É î)  º æ ∂ µ    æ ≤ Ç æ   Ω æ  ñ Ω ñ Ü ñ é ≤   Ç ∏  Ç æ π      º ∏ π CMD:OPEN.

 û   ∫ ñ ª å ∫ ∏  Ω ñ ¥ µ  Ω µ  ≤ µ ¥ µ Ç å   è  æ ± ª ñ ∫  ≤ ñ ¥       ≤ ª µ Ω ∏ Ö idempotent_key, BinanceExecutionAdapter  ≤ ñ ¥       ≤ ª è î  ¥   É ≥ ∏ π,  ñ ¥ µ Ω Ç ∏ á Ω ∏ π  æ   ¥ µ  ,  â æ      ∏ ∑ ≤ æ ¥ ∏ Ç å  ¥ æ    æ ¥ ≤ æ î Ω Ω è    æ ∑ ∏ Ü ñ ó  Ç      ∏ ∑ ∏ ∫ É.

12. " í ∏   è á ñ"  æ   ¥ µ   ∏  á µ   µ ∑  Ω µ   µ   ª ñ ∑ æ ≤   Ω É  ª æ ≥ ñ ∫ É    ∫     É ≤   Ω Ω è

 ü   æ ± ª µ º  :  ° ∏   Ç µ º    ≤ ∏ ∫ æ   ∏   Ç æ ≤ É î  æ   ¥ µ   ∏  Ç ∏   É GTC ("Good-Till-Cancel"),  â æ    µ   µ ¥ ±   á   î  ó Ö  ñ   Ω É ≤   Ω Ω è  ¥ æ  ≤ ∏ ∫ æ Ω   Ω Ω è    ± æ    ∫     É ≤   Ω Ω è.  û ¥ Ω   ∫  Ñ É Ω ∫ Ü ñ è cancel_order  ≤    ¥     Ç µ   ñ  î  ª ∏ à µ  ∑   ≥ ª É à ∫ æ é (placeholder).

 õ æ ∫   Ü ñ è:  §   π ª: binance_execution_adapter.py,  § É Ω ∫ Ü ñ è: cancel_order,  † è ¥ ∫ ∏: ~334-342.

 ù     ª ñ ¥ æ ∫:  Ø ∫ â æ    ∏   Ç µ º    ≤ ñ ¥       ≤ ª è î  ª ñ º ñ Ç Ω ∏ π  æ   ¥ µ    ñ    ∏ Ω ∫ æ ≤    Ü ñ Ω    π ¥ µ  ≤  ñ Ω à æ º É  Ω       è º ∫ É,  Ü µ π  æ   ¥ µ    ∑   ª ∏ à   î Ç å   è    ∫ Ç ∏ ≤ Ω ∏ º  Ω    ± ñ   ∂ ñ  Ω µ ≤ ∏ ∑ Ω   á µ Ω ∏ π  á    .  Ø ∫ â æ    ñ ∑ Ω ñ à µ    ∏   Ç µ º    ≤ ∏   ñ à ∏ Ç å  É ≤ ñ π Ç ∏  ≤    æ ∑ ∏ Ü ñ é  ≤      æ Ç ∏ ª µ ∂ Ω æ º É  Ω       è º ∫ É,  Ü µ π    Ç     ∏ π, " ∑   ± É Ç ∏ π"  æ   ¥ µ    º æ ∂ µ  ± É Ç ∏  Ω µ     æ ¥ ñ ≤   Ω æ  ≤ ∏ ∫ æ Ω   Ω ∏ π  ∑    ≤ ∫     π  Ω µ ≤ ∏ ≥ ñ ¥ Ω æ é  Ü ñ Ω æ é,  â æ      ∏ ∑ ≤ µ ¥ µ  ¥ æ  º ∏ Ç Ç î ≤ æ ≥ æ  ∑ ± ∏ Ç ∫ É.  ¶ µ    Ç ≤ æ   é î  Ω        Ö É Ω ∫ É  º ñ Ω ∏  É   æ ≤ ñ ª å Ω µ Ω æ ó  ¥ ñ ó.

13.  ì µ Ω µ     Ü ñ è  Ö ∏ ± Ω ∏ Ö    ∏ ≥ Ω   ª ñ ≤  á µ   µ ∑    æ ∑   ∏ ≤ ∏  ≤    ∏ Ω ∫ æ ≤ ∏ Ö  ¥   Ω ∏ Ö

 ü   æ ± ª µ º  :  ö æ º   æ Ω µ Ω Ç feature_engineering    æ ∑     Ö æ ≤ É î  ∑ º ñ Ω É  Ü ñ Ω ∏ (delta_price)  è ∫      æ   Ç É    ñ ∑ Ω ∏ Ü é  º ñ ∂    æ Ç æ á Ω ∏ º  Ç      æ   µ   µ ¥ Ω ñ º  Ç ñ ∫ æ º.  í ñ ¥   É Ç Ω è  ± É ¥ å- è ∫      µ   µ ≤ ñ   ∫    á     æ ≤ æ ≥ æ  ñ Ω Ç µ   ≤   ª É (timestamp)  º ñ ∂  Ü ∏ º ∏  Ç ñ ∫   º ∏.

 õ æ ∫   Ü ñ è:  §   π ª: feature_engineering.py,  § É Ω ∫ Ü ñ è: _calculate_features_with_history,  † è ¥ ∫ ∏: ~206-213.

 ù     ª ñ ¥ æ ∫:  £  ≤ ∏     ¥ ∫ É  ∫ æ   æ Ç ∫ æ á     Ω æ ≥ æ  ∑ ± æ é  ∑' î ¥ Ω   Ω Ω è  ∑ WebSocket ( Ω   ≤ ñ Ç å  Ω    ∫ ñ ª å ∫      µ ∫ É Ω ¥),    µ   à ∏ π  Ç ñ ∫    ñ   ª è  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è  ∑' î ¥ Ω   Ω Ω è  ± É ¥ µ    æ   ñ ≤ Ω é ≤   Ç ∏   è  ∑  æ   Ç   Ω Ω ñ º  Ç ñ ∫ æ º  ¥ æ  ∑ ± æ é.  ¶ µ    Ç ≤ æ   ∏ Ç å  à Ç É á Ω ∏ π,  ≤ µ ª ∏ á µ ∑ Ω ∏ π delta_price,  è ∫ ∏ π  Ω µ  ≤ ñ ¥ æ ±     ∂   î    µ   ª å Ω É    ∏ Ω ∫ æ ≤ É  ¥ ∏ Ω   º ñ ∫ É.  û   ∫ ñ ª å ∫ ∏ delta_price  ≤ ∏ ∫ æ   ∏   Ç æ ≤ É î Ç å   è  ≤ RiskManagement  ¥ ª è  æ Ü ñ Ω ∫ ∏    ∏ ∑ ∏ ∫ É,  Ü µ  º æ ∂ µ      ∏ ∑ ≤ µ   Ç ∏  ¥ æ    æ º ∏ ª ∫ æ ≤ æ ≥ æ  ± ª æ ∫ É ≤   Ω Ω è  Ç æ   ≥ ñ ≤ ª ñ (is_trading_allowed = false)  Ω    ≤ æ ª   Ç ∏ ª å Ω æ º É,    ª µ  ∑ ¥ æ   æ ≤ æ º É    ∏ Ω ∫ É,    ± æ,  Ω   ≤     ∫ ∏,  ¥ æ  ñ ≥ Ω æ   É ≤   Ω Ω è    µ   ª å Ω æ ≥ æ    ∏ ∑ ∏ ∫ É.  ¶ µ        ∏ á ∏ Ω è î    ± æ  ≤ Ç     Ç É  º æ ∂ ª ∏ ≤ æ   Ç µ π,    ± æ  Ω µ   ¥ µ ∫ ≤   Ç Ω É  æ Ü ñ Ω ∫ É    ∏ ∑ ∏ ∫ É.
14.  ü   ∏ π Ω è Ç Ç è    ñ à µ Ω å  Ω    æ   Ω æ ≤ ñ  ∑     Ç     ñ ª æ ≥ æ    Ç   Ω É    æ   Ç Ñ µ ª è ("Stale State")
 ü   æ ± ª µ º  :  ö æ º   æ Ω µ Ω Ç DecisionMaking  Ω µ  æ á ∏ â É î  ¥   Ω ñ      æ    æ   Ç Ñ µ ª å (self.latest_portfolio)    ñ   ª è      ∏ π Ω è Ç Ç è    ± æ  ≤ ñ ¥ Ö ∏ ª µ Ω Ω è  Ç æ   ≥ æ ≤ æ ≥ æ    ñ à µ Ω Ω è.  ¶ µ    Ç ≤ æ   é î  Ç   ∏ ≤   ª É "   ª ñ   É  ∑ æ Ω É",      æ Ç è ≥ æ º  è ∫ æ ó    ∏   Ç µ º        æ ¥ æ ≤ ∂ É î      ∏ π º   Ç ∏    ñ à µ Ω Ω è,  ±   ∑ É é á ∏   å  Ω    Ω µ   ∫ Ç É   ª å Ω ñ π  ñ Ω Ñ æ   º   Ü ñ ó      æ  ≤ ª     Ω ñ    æ ∑ ∏ Ü ñ ó  Ç    ∫     ñ Ç   ª.
 õ æ ∫   Ü ñ è:  §   π ª: decision_making.py,  § É Ω ∫ Ü ñ è: clear_internal_state,  † è ¥ ∫ ∏: ~448-456.  ö æ º µ Ω Ç      É  ∫ æ ¥ ñ      è º æ  ≤ ∫   ∑ É î: Note: latest_portfolio is NOT cleared here as it should persist.
 ù     ª ñ ¥ æ ∫:  ¶ µ π  ¥ µ Ñ µ ∫ Ç  º   î  ¥ ≤      É π Ω ñ ≤ Ω ñ  Ω     ª ñ ¥ ∫ ∏:
 í Ç     Ç        ∏ ± É Ç ∫ æ ≤ ∏ Ö  É ≥ æ ¥:  Ø ∫ â æ    æ ∑ ∏ Ü ñ è  ∑   ∫   ∏ ≤   î Ç å   è ( ≤   É á Ω É    ± æ  ñ Ω à ∏ º  º µ Ö   Ω ñ ∑ º æ º), DecisionMaking  Ω µ  ¥ ñ ∑ Ω   î Ç å   è      æ  Ü µ  ¥ æ  Ω     Ç É   Ω æ ≥ æ  æ Ω æ ≤ ª µ Ω Ω è  ≤ ñ ¥ AccountConnector ( è ∫ µ  ≤ ñ ¥ ± É ≤   î Ç å   è      ∑  Ω   30    µ ∫ É Ω ¥).  ü   æ Ç è ≥ æ º  Ü å æ ≥ æ  á     É  ≤ ñ Ω  ± É ¥ µ      æ ¥ æ ≤ ∂ É ≤   Ç ∏  ≤ ñ ¥ Ö ∏ ª è Ç ∏  Ω æ ≤ ñ  ≤   ª ñ ¥ Ω ñ    ∏ ≥ Ω   ª ∏  Ω    ≤ Ö ñ ¥    æ  Ü å æ º É  ∂  ñ Ω   Ç   É º µ Ω Ç É,    æ   ∏ ª   é á ∏   å  Ω   POSITION_ACCUMULATION_BLOCKED,  Ö æ á    Ω           ≤ ¥ ñ    æ ∑ ∏ Ü ñ ó  ≤ ∂ µ  Ω µ º   î.
 ù µ ∫ æ Ω Ç   æ ª å æ ≤   Ω µ  Ω   ∫ æ   ∏ á µ Ω Ω è    ∏ ∑ ∏ ∫ É:  Ø ∫ â æ    ∏   Ç µ º    ∑   ∑ Ω   ª    ∑ ± ∏ Ç ∫ É ( Ω       ∏ ∫ ª   ¥,  á µ   µ ∑  á     Ç ∫ æ ≤ ∏ π    Ç æ  - ª æ  ), DecisionMaking  ± É ¥ µ      æ ¥ æ ≤ ∂ É ≤   Ç ∏    æ ∑     Ö æ ≤ É ≤   Ç ∏    æ ∑ º ñ    Ω æ ≤ ∏ Ö    æ ∑ ∏ Ü ñ π  Ω    æ   Ω æ ≤ ñ    Ç     æ ≥ æ,  ± ñ ª å à æ ≥ æ  ∑ Ω   á µ Ω Ω è  ∫     ñ Ç   ª É (equity),  ¥ æ ∫ ∏  Ω µ      ∏ π ¥ µ  Ω     Ç É   Ω µ  æ Ω æ ≤ ª µ Ω Ω è.  ¶ µ    ∏   Ç µ º   Ç ∏ á Ω æ      ∏ ∑ ≤ æ ¥ ∏ Ç å  ¥ æ  ≤ ñ ¥ ∫   ∏ Ç Ç è    æ ∑ ∏ Ü ñ π  ∑  Ω   ¥ º ñ   Ω ∏ º    ∏ ∑ ∏ ∫ æ º.
 õ   Ω Ü é ≥ ( í Ç     Ç    º æ ∂ ª ∏ ≤ æ   Ç ñ):
 ° ∏   Ç µ º    º   î  ≤ ñ ¥ ∫   ∏ Ç É    æ ∑ ∏ Ü ñ é long BTCUSDT. DecisionMaking  ∑ ± µ   ñ ≥   î  Ü µ π    Ç   Ω  É self.latest_portfolio.
 ¢   µ π ¥ µ    ≤   É á Ω É  ∑   ∫   ∏ ≤   î  Ü é    æ ∑ ∏ Ü ñ é  Ω    ± ñ   ∂ ñ.
 ß µ   µ ∑ 2    µ ∫ É Ω ¥ ∏ DecisionMaking  æ Ç   ∏ º É î  Ω æ ≤ ∏ π    ∏ ª å Ω ∏ π    ∏ ≥ Ω   ª  Ω   long BTCUSDT.
 § É Ω ∫ Ü ñ è _try_make_decision    µ   µ ≤ ñ   è î self.latest_portfolio ( è ∫ ∏ π  â µ  Ω µ  æ Ω æ ≤ ∏ ≤   è)  ñ  ±   á ∏ Ç å,  â æ    æ ∑ ∏ Ü ñ è  Ω ñ ± ∏ Ç æ  ñ   Ω É î.
 ° ∏ ≥ Ω   ª  ≤ ñ ¥ Ö ∏ ª è î Ç å   è  ∑      ∏ á ∏ Ω æ é POSITION_ACCUMULATION_BLOCKED.
 ß µ   µ ∑ 28    µ ∫ É Ω ¥  Ω   ¥ Ö æ ¥ ∏ Ç å  æ Ω æ ≤ ª µ Ω Ω è  ≤ ñ ¥ AccountConnector, self.latest_portfolio  æ Ω æ ≤ ª é î Ç å   è,    ª µ        ∏ è Ç ª ∏ ≤ ∏ π  º æ º µ Ω Ç  ¥ ª è  ≤ Ö æ ¥ É  ≤ ∂ µ  ≤ Ç     á µ Ω æ.
 ¶ µ π  ∑ ≤ ñ Ç  ∑   ≤ µ   à É î    Ω   ª ñ ∑  ∫   ∏ Ç ∏ á Ω ∏ Ö    æ º ∏ ª æ ∫.  í ∏ è ≤ ª µ Ω ñ      æ ± ª µ º ∏  æ Ö æ   ª é é Ç å  ¥ µ Ñ µ ∫ Ç ∏  ≤  ª æ ≥ ñ Ü ñ,    Ç   Ω ∏  ≥ æ Ω ∏ Ç ≤ ∏,      Ö ñ Ç µ ∫ Ç É   Ω ñ  Ω µ ¥ æ ª ñ ∫ ∏  Ç    Ω µ   ¥ µ ∫ ≤   Ç Ω µ  É       ≤ ª ñ Ω Ω è    Ç   Ω æ º,  ∫ æ ∂ µ Ω  ∑  è ∫ ∏ Ö  º æ ∂ µ      ∏ ∑ ≤ µ   Ç ∏  ¥ æ  ∑ Ω   á Ω ∏ Ö  Ñ ñ Ω   Ω   æ ≤ ∏ Ö  ≤ Ç     Ç.