 ó ê î ê ù ò ï:  ≠ ∫     æ   Ç ∏   æ ≤   Ç å  ≥ ∏ ±   ∏ ¥ Ω ã µ  Ñ ª   ≥ ∏/     ∏ á ∏ Ω ã  ≤ /metrics  ∏ statdump (additive-only).

1) apps/reference/bootstrap/preflight.py
   - check_hybrid_coherence(config)  É ∂ µ  µ   Ç å ‚Üí  ≤ µ   Ω ∏    Ç   É ∫ Ç É   É {ok:bool, reasons:[...]}
   -  ° æ Ö     Ω è π last_check_ts  ∏ last_result  ≤    µ µ   Ç   (singleton/state).

2)  ≠ ∫     æ   Ç:
   - apps/reference/api/metrics.py ( ∏ ª ∏  ≥ ¥ µ  º µ Ç   ∏ ∫ ∏):  ¥ æ ±   ≤ ∏ Ç å gauge
     aurora_hybrid_coherent{mode="hybrid_live_testnet"} = 0|1
     aurora_hybrid_incoherent_reasons_total{reason="<slug>"} = counter
   - apps/reference/api/statdump.py:  ¥ æ ±   ≤ ∏ Ç å      ∑ ¥ µ ª "hybrid": {ok, reasons, risk_portfolio_source, execution_mode}

3)  ¢ µ   Ç ã:
   - tests/integration/test_hybrid_metrics_export.py
      ü   æ ≤ µ   ∫  ,  á Ç æ incoherent ‚Üí gauge=0, reasons counter  ∏ Ω ∫   µ º µ Ω Ç ∏   É µ Ç   è; coherent ‚Üí gauge=1.
