# HARNESS BENCHMARK REPORT

## Benchmark Objective

Verify that the new PKG-5 proxy harness can run reproducible March backtests on the smallest honest proxy universe and export artifact-visible scoring telemetry.

## Commands Used

Baseline proxy:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONLEGACYWINDOWSSTDIO='utf-8'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
c:/Users/wekab/Music/Phenix/.venv/Scripts/python.exe scripts/diagnostics/run_research_proxy_backtest.py --label pkg5_eth_btc_baseline --trading-symbols ETHUSDT --context-symbols BTCUSDT --start 2024-03-01 --end 2024-03-31 --balance 1000 --fail-on-scoring-fallback
```

V1 proxy:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONLEGACYWINDOWSSTDIO='utf-8'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
c:/Users/wekab/Music/Phenix/.venv/Scripts/python.exe scripts/diagnostics/run_research_proxy_backtest.py --label pkg5_eth_btc_v1 --overlay-yaml config/overlays/march_candidate_v1_block_eth_trend_down.yaml --trading-symbols ETHUSDT --context-symbols BTCUSDT --start 2024-03-01 --end 2024-03-31 --balance 1000 --fail-on-scoring-fallback
```

## Results

| Label | Run ID | Overlay | Elapsed Seconds | ROI % | Max DD % | Trades | Sharpe | Fallbacks |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| pkg5_eth_btc_baseline | `20260314_170343` | none | 1367.893 | -30.3418 | 62.7875 | 180 | -0.3515 | 0 |
| pkg5_eth_btc_v1 | `20260314_172657` | `config/overlays/march_candidate_v1_block_eth_trend_down.yaml` | 995.142 | 5.1384 | 4.0810 | 18 | 1.7993 | 0 |

## Telemetry Verification

Baseline `20260314_170343`:

- quadratic selected: `17724`
- quadratic fallbacks: `0`
- fallback also failed: `0`
- engines observed: `quadratic_v1`

V1 `20260314_172657`:

- quadratic selected: `17723`
- quadratic fallbacks: `0`
- fallback also failed: `0`
- engines observed: `quadratic_v1`

## Benchmark Conclusions

1. The PKG-5 harness is operationally valid on the ETH+BTC proxy surface.
2. Both runs completed under strict-compatible proxy configuration without illegal overlay of SSOT-derived fields.
3. Both runs were artifact-proven fallback-free.
4. The benchmark still shows meaningful runtime cost, but it is now bounded and reproducible enough for a narrow next-package search.

## Artifact Outputs

Baseline:

- `reports/backtests/backtest_20260314_170343.json`
- `reports/backtests/backtest_20260314_170343.summary.json`
- `reports/backtests/PKG5_proxy_baseline_stdout.txt`

V1:

- `reports/backtests/backtest_20260314_172657.json`
- `reports/backtests/backtest_20260314_172657.summary.json`
- `reports/backtests/PKG5_proxy_v1_stdout.txt`