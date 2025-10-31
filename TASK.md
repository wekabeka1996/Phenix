              :                                                           /                  /metrics    statdump (additive-only).

1) apps/reference/bootstrap/preflight.py
   - check_hybrid_coherence(config)                                                   {ok:bool, reasons:[...]}
   -                  last_check_ts    last_result                 (singleton/state).

2)               :
   - apps/reference/api/metrics.py (                            ):                  gauge
     aurora_hybrid_coherent{mode="hybrid_live_testnet"} = 0|1
     aurora_hybrid_incoherent_reasons_total{reason="<slug>"} = counter
   - apps/reference/api/statdump.py:                               "hybrid": {ok, reasons, risk_portfolio_source, execution_mode}

3)           :
   - tests/integration/test_hybrid_metrics_export.py
                     ,        incoherent     gauge=0, reasons counter                                 ; coherent     gauge=1.
