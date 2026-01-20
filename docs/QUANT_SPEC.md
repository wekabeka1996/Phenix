# Quant Spec (SSOT)

This document is the **mathematical single source of truth** for scoring, gating, and execution arithmetic, extracted from the live reference implementation.

Code sources:
- Alpha scoring: `apps/reference/domains/decision_making/signal_score_v2.py`
- Daily drawdown gate: `apps/reference/domains/risk_management/daily_gate.py`
- Quantity normalization: `apps/reference/domains/execution_position/qty_normalizer.py`
- Margin-first sizing: `apps/reference/domains/decision_making/sizing_margin_first.py`
- Indicators: `apps/reference/domains/feature_engineering/indicators.py`

## Notation

- Feature name index: $i \in \mathcal{F}$
- Raw feature value: $x_i$
- Neutral offset: $n_i$
- Weight: $w_i$
- Active set for scoring: $\mathcal{A}$ (defined in Chapter 1)

---

## Chapter 1: Alpha Scoring Algebra (SignalScoreV2)

### Config contract: neutral offsets

For every configured weighted feature with non-zero weight, a neutral must exist:
$$
\forall i:\; (w_i \neq 0) \Rightarrow (i \in \texttt{neutrals})
$$
(`SignalScoreV2.validate_config`)

### Active set $\mathcal{A}$ (what actually enters the sum)

In `SignalScoreV2.calculate_score`, a feature $i$ participates in **both** numerator and denominator **iff**:
1) $w_i \neq 0$  
2) feature exists in `features` (otherwise it is skipped)  
3) `readiness.get(i, False) == True` (missing readiness key is treated as **not ready**)  
4) `neutrals[i]` exists at runtime (missing neutral triggers **defer**)  
5) value conversions succeed (conversion error triggers **defer**)

Define:
$$
\mathcal{A} = \{ i \;|\; w_i \neq 0 \land i \in \texttt{features} \land \texttt{readiness}_i = \text{True} \land i \in \texttt{neutrals} \land \text{convertible}(x_i)\}
$$

### Score raw sum and weight normalization

The per-feature centered value is:
$$
f_i = x_i - n_i
$$

Raw score and absolute-weight normalizer:
$$
\text{score}_{raw} = \sum_{i \in \mathcal{A}} w_i \cdot (x_i - n_i)
$$
$$
w_{abs} = \sum_{i \in \mathcal{A}} |w_i|
$$

Normalized score:
$$
\text{score}_{norm} = \frac{\text{score}_{raw}}{w_{abs}}
$$

This matches the “weight normalization” form:
$$
\frac{\sum w_i \cdot f_i}{\sum |w_i|}
$$
with $f_i = x_i - n_i$.

### Clamp mechanism (Safety Clip)

Final output score is clamped to $[-1, 1]$:
$$
\text{score} = \max(-1,\; \min(1,\; \text{score}_{norm}))
$$

### Fail-closed / deferral semantics

`calculate_score` returns `deferred=True` and forces:
$$
\text{score} = 0,\;\text{score}_{raw} = 0,\;w_{abs} = 0
$$
when **any** of the following are observed during iteration:
- Any **essential feature** is missing (`feat not in features`) → deferred
- Any **essential feature** is not ready (`readiness.get(feat, False) == False`) → deferred
- Any participating weighted feature has missing neutral config at runtime → deferred
- Any participating weighted feature fails Decimal conversion / computation → deferred

Non-essential missing/not-ready weighted features are **excluded** from both sums (they do not contribute to $\text{score}_{raw}$ or $w_{abs}$).

---

## Chapter 2: Risk Mechanics (Daily Loss / Drawdown Gate)

Source: `DailyRiskState.can_open` in `apps/reference/domains/risk_management/daily_gate.py`.

### State variables

- $E_{open}$ = `equity_open_usd` (reference equity snapshot)
- $E_{now}$ = `equity_now_usd` (current equity, updated from portfolio)

Fail-closed baseline: if either equity value is $\le 0$, opening is blocked.

### Drawdown percentage (exact implementation)

The code computes a **positive drawdown percent on equity drop**:
$$
DD_{pct} = \left(1 - \frac{E_{now}}{E_{open}}\right)\cdot 100
$$

Gate condition:
$$
\text{BLOCK opens if } DD_{pct} \ge \texttt{max\_drawdown\_pct}
$$

### Reset logic (when $E_{open}$ updates)

`DailyRiskState` uses a configured `reset_time_utc = (h, m)`:

1) **Initialization anchor (first run only)**  
If $E_{open} \le 0$, $E_{now} > 0$, and `last_reset_date is None`, then:
$$
E_{open} \leftarrow E_{now}
$$

2) **Daily reset (after reset time, when date rolls)**  
If `last_reset_date != now.date()` and current time is past `reset_time_utc`, then:
$$
E_{open} \leftarrow E_{now}
$$
and `last_reset_date` becomes `now.date()`.

3) **Persistence / amnesia protection**  
`reference_equity` and `last_reset_date` are persisted to `data/risk_gate_state.json` (path configurable via `AURORA_RISK_GATE_STATE_PATH`). On load, if the stored date does not match the computed active trading date, the state resets to fail-closed baseline.

---

## Chapter 3: Execution Arithmetic (Quantity Normalization)

Source: `normalize_qty` in `apps/reference/domains/execution_position/qty_normalizer.py`.

### Rounding (LOT_SIZE step)

Given raw quantity $Q_{raw}$ and step size $S$ (must be $S>0$), the implementation computes:
$$
k = \left\lfloor \frac{Q_{raw}}{S} \right\rfloor
$$
$$
Q_{rounded} = k \cdot S
$$

(Code uses Decimal division then `.quantize(1, ROUND_DOWN)` to implement the floor to integer.)

### Fail-closed checks (no bump-ups)

1) Zero/negative after rounding:
$$
Q_{rounded} \le 0 \Rightarrow \text{reject (NRR-QTY-ROUNDED-TO-ZERO)}
$$

2) Minimum quantity:
$$
Q_{rounded} < Q_{min} \Rightarrow \text{reject (NRR-QTY-BELOW-MIN\_QTY)}
$$

3) Minimum notional (when configured):
$$
N = Q_{rounded}\cdot P
$$
$$
N < N_{min} \Rightarrow \text{reject (NRR-NOTIONAL-BELOW-MIN)}
$$

---

## Chapter 4: Leverage & Sizing (Margin-First Sizing)

Primary sizing math source: `apps/reference/domains/decision_making/sizing_margin_first.py`.

### Margin-first notional targeting

Inputs:
- Account equity $E$ (`equity`)
- Margin fraction $m \in (0,1]$ (`margin_pct`)
- Leverage $L \in \mathbb{Z}, L \ge 1$ (`leverage`)
- Fee buffer $b$ (`fee_buffer`, default 0.001)

Safe equity (buffer applied before sizing):
$$
E_{safe} = E \cdot (1 - b)
$$

Margin allocated:
$$
M = E_{safe}\cdot m
$$

Notional target:
$$
N_{target} = M \cdot L
$$

Optional cap:
$$
N_{target} \leftarrow \min(N_{target},\; N_{cap})
$$

### Quantity computation (with step rounding)

Given price $P>0$ and step size $S>0$:
$$
Q_{raw} = \frac{N_{target}}{P}
$$
$$
Q_{rounded} = \left\lfloor \frac{Q_{raw}}{S} \right\rfloor \cdot S
$$

### Exchange constraint validation

`validate_exchange_constraints` rejects if:
- $Q \le 0$
- $Q < Q_{min}$ when $Q_{min} > 0$
- $Q\cdot P < N_{min}$ when $N_{min} > 0$

### Leverage verification (execution safety, not sizing math)

Leverage/margin-mode verification is performed by `LeverageService` (`apps/reference/domains/execution_position/leverage_service.py`):
- Reads `actual_leverage` and `actual_margin_mode` from exchange.
- Rejects if they differ from expected (fail-closed on adapter errors).

### Risk score note (current state)

In the current reference code, **risk score gates trading eligibility** (e.g., reject if `risk_score > max_risk_score`) but **does not mathematically scale** $m$ or $N_{target}$ inside `sizing_margin_first.py`.

---

## Chapter 5: Indicator Math (Feature Engineering)

Source: `apps/reference/domains/feature_engineering/indicators.py`.

### Simple Moving Average (SMA)

For window size $W$ and values $v_{t-W+1}, \dots, v_t$:
$$
\text{SMA}_t = \frac{1}{W}\sum_{j=t-W+1}^{t} v_j
$$

### Standard Deviation (population, windowed)

With mean $\mu$ over the same window:
$$
\sigma_t = \sqrt{\frac{1}{W}\sum_{j=t-W+1}^{t} (v_j - \mu)^2}
$$

### Bollinger Bands

Let $k$ be `num_std`:
$$
\text{mid} = \text{SMA}
$$
$$
\text{upper} = \text{mid} + k\sigma,\quad \text{lower} = \text{mid} - k\sigma
$$
Width (as fraction of mid):
$$
\text{width} = \begin{cases}
\frac{\text{upper}-\text{lower}}{\text{mid}}, & \text{mid}\neq 0 \\
0, & \text{mid}=0
\end{cases}
$$
Percent-B (with price = `current_price` else last close):
$$
\%B = \begin{cases}
\frac{\text{price}-\text{lower}}{\text{upper}-\text{lower}}, & \text{upper}\neq \text{lower} \\
0.5, & \text{upper}= \text{lower}
\end{cases}
$$

### Average True Range (ATR)

For each bar $i$ (needs previous close $C_{i-1}$):
$$
TR_i = \max\left(H_i - L_i,\; |H_i - C_{i-1}|,\; |L_i - C_{i-1}|\right)
$$
ATR over window $W$:
$$
\text{ATR} = \frac{1}{W}\sum TR_i
$$

### Relative Strength Index (RSI)

Compute close-to-close changes $\Delta C_j = C_j - C_{j-1}$ over last $W$ changes:
$$
\text{avg\_gain} = \frac{1}{W}\sum \max(\Delta C_j, 0),\quad
\text{avg\_loss} = \frac{1}{W}\sum \max(-\Delta C_j, 0)
$$
If `avg_loss == 0`, RSI returns 100. Otherwise:
$$
RS = \frac{\text{avg\_gain}}{\text{avg\_loss}},\quad
RSI = 100 - \frac{100}{1+RS}
$$

