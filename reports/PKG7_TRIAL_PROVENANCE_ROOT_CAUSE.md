# PKG-7 Root Cause Report

## Executive Summary

PKG-6 did not prove that March search trials were runtime-identical. It only proved that the old artifact path reported them as identical.

The exact failure was a provenance/materialization defect:

- requested ETH overlay deltas were applied in memory;
- the old report snapshot/hash path did not include that effective ETH strategy slice;
- saved bundle YAMLs reflected on-disk config files, not overlay-materialized effective config.

## Exact Finding

The old report hash path in `backtest_engine/reporting.py` hashed a narrow snapshot containing:

- `config_files`
- a reduced `resolved_config`
- only the `BTCUSDT` asset slice under `strategies.aurora.assets`
- `regime.yaml`

That path omitted the ETH slice where PKG-6 searched `macro_resid`, `tfi`, and `signal_threshold`.

## Ruled-Out Explanations

- Not overlay overwrite: `ConfigLoader` applies `optuna_overlay` last.
- Not proven dead params: live probe showed requested ETH values changing in the loaded config.
- Not honest candidate convergence evidence: the artifact path itself collapsed distinct requests before they could be audited.

## Probe Evidence

- anchor values: `macro_resid=0.25`, `tfi=0.093`, `signal_threshold=0.008`
- distinct values: `macro_resid=0.31`, `tfi=0.14`, `signal_threshold=0.0095`
- old snapshot hash for both paths: `a593200968fdb4b1c3330c42e27fde50e73bd6da8426eece5cd41aa51b7a2dd1`
- resolved asset keys in the old snapshot: `BTCUSDT` only

## Conclusion

PKG-6 ambiguity was caused by missing effective-config materialization in artifacts. PKG-7 therefore hardens provenance first and defers any renewed search claim to the next package.