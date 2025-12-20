# TASK24A — RegimeDetector Forensic Audit (P0/P1)

Scope: `apps/reference/domains/regime_detector/regime_detector.py`

## Findings (P0)

### P0 — Config access mixes typed object + dict fallbacks (silent degrade + magic defaults)

- **File/line:** `apps/reference/domains/regime_detector/regime_detector.py:193-236`
- **What breaks:** the detector tries multiple paths (`hasattr`, `isinstance(dict)`, `.get(...)`) and falls back to hardcoded values:
  - `threshold_multiplier_val = 2.0` default
  - `low_vol_multiplier_val = 0.5` default
- **Impact:** missing/incorrect config can silently change regime outcomes instead of failing closed.

### P0 — Mean reversion threshold silently defaults to `0.005` (magic)

- **File/line:** `apps/reference/domains/regime_detector/regime_detector.py:304-329`
- **What breaks:** missing/invalid MR config uses hardcoded `"0.005"` fallback.
- **Impact:** can silently enable/disable MEAN_REVERSION classification.

### P0 — ATR is approximated “close-to-close” without explicit opt-in and without OHLC checks

- **File/line:** `apps/reference/domains/regime_detector/regime_detector.py:166-183`
- **What breaks:** volatility TR is computed as `abs(price - prev_price)` (close-to-close), not True Range based on OHLC; no explicit `allow_close_to_close_atr` gate exists in code/config.
- **Impact:** volatility regimes become data-dependent guesses; missing OHLC silently degrades volatility model.

## Findings (P1)

### P1 — Data-quality metrics are absent (silent drops, no counters)

- **Symptoms:** staleness/missing fields/invalid dt are handled by implicit defaults and “UNCERTAIN” paths with no structured metric such as `data_quality_drop_total{reason}`.
- **Impact:** operator cannot observe data-quality related regime degradation.

### P1 — Magic multipliers appear in confidence shaping logic

- **File/line:** `apps/reference/domains/regime_detector/regime_detector.py:244-285` uses hardcoded `Decimal("2.0")` and `Decimal("3.0")` as default confidence multipliers when config not present.
- **Impact:** confidence behavior is not SSOT and is not fully config-driven.

## Summary (“what breaks / why”)

- RegimeDetector currently mixes config access patterns (object/dict) and uses fallback magic thresholds/multipliers.
- ATR/volatility logic silently degrades when OHLC is absent by using close-to-close TR without explicit opt-in.
- There are no data-quality/staleness metrics, so degradation is not observable.

