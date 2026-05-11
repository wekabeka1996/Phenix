# PKG6 SANITY REPLAY REPORT

## Scope

No candidate set survived Phase 6, so sanity replay was run for the v1 anchor only.

March main-window anchor reference remained `20260314_172657`.

Additional sanity windows were executed on the same hardened ETH+BTC proxy surface with fail-closed fallback rejection enabled.

## Windows

### March main window

- Run: `20260314_172657`
- Range: `2024-03-01 -> 2024-03-31`
- ROI: `+5.1384%`
- Max DD: `4.08%`
- Trades: `18`
- Quadratic fallbacks: `0`

### January sanity window

- Run: `20260314_215848`
- Range: `2024-01-15 -> 2024-01-22`
- ROI: `-3.5425%`
- Max DD: `3.56%`
- Trades: `2`
- Quadratic fallbacks: `0`

### February sanity window

- Run: `20260314_220436`
- Range: `2024-02-12 -> 2024-02-19`
- ROI: `+1.4970%`
- Max DD: `0.00%`
- Trades: `2`
- Quadratic fallbacks: `0`

## Interpretation

The v1 anchor remains fallback-clean across all three observed windows on the hardened proxy harness.

However, the Jan/Feb sanity windows are low-sample observations only:

- both windows produced just `2` trades,
- January was negative,
- February was positive,
- neither window is strong enough to upgrade the March anchor into cross-period truth.

## Conclusion

Sanity replay does not invalidate the v1 anchor.

It also does not create a new winner. Cross-window evidence remains limited and must not be presented as full-universe or production-grade validation.