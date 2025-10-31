ЗАДАНИЕ: Эк� портировать гибридные флаги/причины в /metrics и statdump (additive-only).

1) apps/reference/bootstrap/preflight.py
   - check_hybrid_coherence(config) уже е� ть → верни � труктуру {ok:bool, reasons:[...]}
   - Сохраняй last_check_ts и last_result в рее� тр (singleton/state).

2) Эк� порт:
   - apps/reference/api/metrics.py (или где метрики): добавить gauge
     aurora_hybrid_coherent{mode="hybrid_live_testnet"} = 0|1
     aurora_hybrid_incoherent_reasons_total{reason="<slug>"} = counter
   - apps/reference/api/statdump.py: добавить раздел "hybrid": {ok, reasons, risk_portfolio_source, execution_mode}

3) Те� ты:
   - tests/integration/test_hybrid_metrics_export.py
     Проверка, что incoherent → gauge=0, reasons counter инкрементирует� я; coherent → gauge=1.
