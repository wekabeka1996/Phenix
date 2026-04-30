# R7F Peak-Giveback Verified Gap List

- Exact remaining gap: the verified slice never exposes usable economics for peak-giveback math, so quiet-by-market cannot be proven from live values.
- Category: observability gap, not a correctness regression.
- Why it matters: without non-null mark_price, unrealized_pnl_usdt, or current_edge_usd, the runtime cannot be shown to have stayed below the 25 USD arm threshold or below the 50 percent giveback trigger from economic evidence alone.
- Smallest safe next step: continue runtime observation on a later verified slice until at least one lifecycle emits usable economics, then re-run the same proof pattern without changing thresholds or Sidecar logic.
- Separate continuity note: the BNB tail still falls into no_active_lifecycle after flat-state closure, but that is outside the scope of this package and should be investigated separately only if continuity semantics need to change.
