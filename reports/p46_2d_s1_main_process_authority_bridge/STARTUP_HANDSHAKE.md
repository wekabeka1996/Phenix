# Startup Handshake

The compatibility query proves more than port reachability:

```yaml
runtime_id: validated
environment: binance_futures_testnet
runtime_generation: validated and retained
supported_query_schema_versions: p46.authority-query.v1
read_model_available: explicit
dry_run_available: explicit
```

Wrong runtime, wrong environment, invalid schema, wrong correlation, or changed generation fails closed. A changed generation clears the retained generation and requires a new handshake.
