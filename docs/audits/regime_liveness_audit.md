# Regime Liveness Forensic Audit

## Executive Summary
A narrow forensic audit was conducted on the pre-fix runtime logs (`arhie_pre_fix`) to determine the liveness of the `basis-regime` input path for `ETHUSDT`, `SOLUSDT`, and `BTCUSDT`. 

The findings conclusively show that the **input path remained fully alive and operational** throughout the entire logged period (up to `08:50` and beyond). The [RegimeDetector](file:///c:/Users/user/Music/Phenix/apps/reference/domains/regime_detector/regime_detector.py#37-905) continuously received `FEATURES_CALCULATED` with `tf_sec=300`. The absence of new regime logs was not due to a hanging input path or a dead detector, but rather because the symbols remained stably inside the `LOW_VOLATILITY` regime, meaning no state transition was triggered.

## Scope and Evidence Sources
- **Logs:** `logs/arhie_pre_fix/` (`domain_regime_detector.log`, `domain_feature_engineering.log`, `event_chain.log`).
- **Code:** `apps/reference/domains/regime_detector/regime_detector.py`
- **Focus:** `ETHUSDT`, `SOLUSDT`, `BTCUSDT` (Aurora symbols) compared against non-aurora reference symbols (`DOGEUSDT`, `XRPUSDT`, `BNBUSDT`, `1000PEPEUSDT`).

---

## 1. Last Regime Transition Table
The last recorded `Regime updated` logs for the target symbols in `domain_regime_detector.log`:

| Symbol | Last Transition TS | Prev Regime | New Regime | Raw Regime | Confidence | Model |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **ETHUSDT** | 2026-03-18 00:00:04 | UNCERTAIN | LOW_VOLATILITY | LOW_VOLATILITY | 0.7006 | volatility_v2 |
| **SOLUSDT** | 2026-03-18 00:04:59 | UNCERTAIN | LOW_VOLATILITY | LOW_VOLATILITY | 0.4806 | volatility_v2 |
| **BTCUSDT** | 2026-03-18 01:10:04 | UNCERTAIN | LOW_VOLATILITY | LOW_VOLATILITY | 0.3751 | volatility_v2 |

---

## 2. Basis Input Liveness After Last Transition
For `ETHUSDT`, `SOLUSDT`, and `BTCUSDT`:

- **BAR_CLOSED seen?**: Yes.
- **FEATURES_CALCULATED tf_sec=300 seen?**: Yes. Both `BAR` and `FEATURES` logs are continuously present in the latest rotation of `domain_feature_engineering.log`.
- **Until when?**: Traced successfully up to timestamp `2026-03-18 08:50:04` (the end of the logs).
- **Detector input evidence**: `event_chain.log` proves these events were received and routed properly. The logs show `Event received` and `Event emitted` correctly synced to the 5-minute boundaries for these symbols.
- **Gaps?**: No significant gaps found that would indicate a hang or frozen state in the FE pipeline.

---

## 3. Comparison With Non-Aurora Symbols
While ETH, SOL, and BTC remained quiet after `01:10`, the other symbols displayed significant volatility and frequent regime shifts, proving the detector and the global pipeline were functioning correctly:
- **DOGEUSDT**: Multiple transitions starting `04:45` (TREND_UP), `05:05` (LOW_VOLATILITY), `05:50` (TREND_UP), `06:35` (UNCERTAIN), up to `07:45` (LOW_VOLATILITY).
- **XRPUSDT**: Transitions at `06:20` (UNCERTAIN), `06:40` (MEAN_REVERSION), `06:55` (LOW_VOLATILITY).
- **BNBUSDT**: Transitioned to MEAN_REVERSION at `08:05`.
- **1000PEPEUSDT**: Transitions ranging from UNCERTAIN to TREND_UP up to `06:25`.

---

## 4. Detector Behavior Interpretation
Per the code in `apps/reference/domains/regime_detector/regime_detector.py`:
- **When it logs transitions:** `domain_regime_detector.log` only writes to file upon an actual state change (`if changed:` condition line ~798).
- **When it is silent:** The detector emits `EVT:REGIME_DETECTED` with `changed=False` on *every* basis bar heartbeat (to maintain liveness logic). However, it deliberately suppresses `logger.info("Regime updated...")` logs to avoid hot-path database spam during long stretches of stable regimes.
- **When it indicates a broken path:** If the FE domain stopped emitting `tf_sec=300` features, the detector would emit UNCERTAIN and log data quality issues (`stale_features`). This did not occur for ETH/SOL/BTC.

---

## 5. Per-Symbol Verdict

- **ETHUSDT**: `STABLE REGIME / NO TRANSITION`
- **SOLUSDT**: `STABLE REGIME / NO TRANSITION`
- **BTCUSDT**: `STABLE REGIME / NO TRANSITION`

The path wasn't dead, missing, or filtered; the market features simply did not cross the thresholds required by `volatility_v2` or `sma_trend_v1` to break out of `LOW_VOLATILITY`.

---

## 6. Global vs Per-Symbol Regime Conclusion
The Regime Detector is explicitly **per-symbol** in runtime.
Based on the code in `regime_detector.py`:
- All feature buffers (`_price_buf`, `_atr_buf`) and hysteresis tracking containers (`_hysteresis_stable`, `_stable_confidence`) are implemented as `defaultdict` or `Dict[str, Any]` mapped exclusively by `symbol`.
- There is no shared internal global state affecting regime evaluations across the symbols. The difference between aurora symbols and non-aurora symbols stems entirely from their distinct individual market feature metrics at those specific times.

---

## 7. Ranked Findings
1. The Regime Detector's input path for Aurora symbols was perfectly healthy and actively recalculating every 5 minutes.
2. The lack of regime transition logs for Aurora symbols was a correct and expected consequence of the `LOW_VOLATILITY` regime remaining stable for a prolonged period.
3. The `RegimeDetector` successfully emits internal heartbeats (`EVT:REGIME_DETECTED` with `changed=False`), confirming it didn't hang or crash.

---

## 8. Open Questions
*None. The evidence strongly proves no input path disruption.*

---

## 9. Recommended Next Pack
Investigate if the parameter thresholds for `LOW_VOLATILITY` (inside `regime.yaml`) are too broad/forgiving for `ETHUSDT`/`SOLUSDT`/`BTCUSDT`, potentially causing them to be artificially "trapped" in a calm regime while the actual market might warrant a trend or uncertain classification.
