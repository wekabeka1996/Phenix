## Backtest components

- `apps/reference/alpha_discovery/backtest_engine.py` (lines 1-200) instantiates the `AlphaModelRegistry`, runs each model over historical OHLCV+features data, simulates trades, and produces `BacktestResult` objects with `win_rate`, `sharpe_ratio`, `profit_factor`, etc. No resolver or runtime hook feeds these metrics into production. | IMPLEMENTED_ACTIVE (standalone backtest) |
- `apps/reference/alpha_discovery/example_backtest.py` demonstrates backtest usage by reading CSV feature files, running `BacktestEngine.backtest_model`, and printing the `BacktestResult`. It remains isolated from `alpha_search` ensemble weight logic. | DOC_ONLY |

## Model-level performance tracking

- `BacktestEngine._calculate_metrics` (lines 200-380) records PnL, Sharpe, max drawdown, win/loss counts, and stores them inside `BacktestResult`. These per-model summaries live only inside the backtest run and are not persisted to shared storage or exposed to other domains. | IMPLEMENTED_ACTIVE (non-integrated) |
- There is no central repository or state within `alpha_search` that caches PnL/sharpe histories for live inference; the only runtime cache remains `EnsembleModel.model_performance` which holds confidence values (see `apps/reference/domains/alpha_search/ensemble.py:243-265`). | GAP |

## Link to ensemble weights (чи відсутній)

- `apps/reference/domains/alpha_search/ensemble.py` computes weights purely from the mean and variance of `model_performance` confidences; no `BacktestResult` fields (Sharpe, PnL) are ever imported or referenced during runtime weight updates. | GAP |
- No code path resolves `BacktestResult` objects or their fields in `alpha_search`. The `example_backtest.py` artifacts are never invoked by DecisionMaking or the ensemble, so there is no live pipeline that would map historical PnL into ensemble weights or `model_performance`. | GAP |

## STATUS & gaps

| mechanism | file:line | description | STATUS |
| --- | --- | --- | --- |
| Backtest engine | `apps/reference/alpha_discovery/backtest_engine.py:1-200` | Runs per-model simulations, calculates win rate/sharpe/profit factors, and returns `BacktestResult`. | IMPLEMENTED_ACTIVE (offline only) |
| Backtest reporting | `apps/reference/alpha_discovery/example_backtest.py` | Example script that prints the `BacktestResult`. | DOC_ONLY |
| Ensemble weight cache | `apps/reference/domains/alpha_search/ensemble.py:243-334` | Uses cached confidence history to recompute weights; no link to backtest metrics. | GAP |
| Performance persistence | `apps/reference/alpha_discovery/backtest_engine.py:200-380` | Calculates metrics but does not store them in a shared store or emit events for runtime domains. | GAP |
| Integration missing | entire repo | No resolver/event pipelines ingest `BacktestResult` data or deploy `regime_multipliers` derived from Sharpe/PnL backtests; thus ensemble weighting remains disconnected from recorded historical PnL. | GAP |
