# SEMA_ATOM_POC_04_COUNTERFACTUAL_POLICY_IMPACT_SIMULATION_REPORT

## Verdict
COUNTERFACTUAL_NEGATIVE

## Scope
- Read-only counterfactual policy-impact simulation over POC_03B-admitted contexts only.
- No live logic, YAML policy, gates, enforcement, or Aurora runtime journal writes.

## Inputs Read
- C:\Users\user\Music\Phenix\SEMA_ATOM_POC_03B_CANDIDATE_MANIFEST.json
- C:\Users\user\Music\Phenix\aurora_real_logs_v02.saf.jsonl
- C:\Users\user\Music\Phenix\SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT.md
- C:\Users\user\Music\Phenix\SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT.md

## Candidate Manifest Summary
- READY_FOR_COUNTERFACTUAL_SIM count: 1
- PROMISING_LOW_SUPPORT count: 5
- REJECTED_FALSE_POSITIVE count: 3
- INCONCLUSIVE_LOW_POWER count: 27
- CONFIRMED_BUT_UNSTABLE count: 1
- UNKNOWN count: 0

## Simulated Contexts
- BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50
  verdict=POLICY_TOO_STRICT_CANDIDATE validation_atom_count=11
  policy_too_strict_count=8 policy_protected_count=3
  conservative_net_impact_bps=-91.919223

## Skipped Contexts
- ETHUSDT|SELL|aurora|LOW_VOLATILITY|0.25..0.50 bucket_excluded_from_simulation
- BNBUSDT|BUY|aurora|MEAN_REVERSION|0.00..0.25 bucket_excluded_from_simulation
- BNBUSDT|BUY|aurora|MEAN_REVERSION|0.25..0.50 bucket_excluded_from_simulation
- BNBUSDT|BUY|aurora|TREND_UP|0.00..0.25 bucket_excluded_from_simulation
- BNBUSDT|BUY|aurora|TREND_UP|0.25..0.50 bucket_excluded_from_simulation
- BNBUSDT|SELL|aurora|MEAN_REVERSION|0.00..0.25 bucket_excluded_from_simulation
- BNBUSDT|SELL|aurora|MEAN_REVERSION|0.25..0.50 bucket_excluded_from_simulation
- BNBUSDT|SELL|aurora|TREND_DOWN|0.00..0.25 bucket_excluded_from_simulation
- BNBUSDT|SELL|aurora|TREND_DOWN|0.25..0.50 bucket_excluded_from_simulation
- BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.00..0.25 bucket_excluded_from_simulation
- BTCUSDT|BUY|aurora|MEAN_REVERSION|0.00..0.25 bucket_excluded_from_simulation
- BTCUSDT|BUY|aurora|TREND_UP|0.00..0.25 bucket_excluded_from_simulation
- BTCUSDT|BUY|aurora|TREND_UP|0.25..0.50 bucket_excluded_from_simulation
- BTCUSDT|SELL|aurora|LOW_VOLATILITY|0.50..0.75 bucket_excluded_from_simulation
- BTCUSDT|SELL|aurora|LOW_VOLATILITY|0.75..1.00 bucket_excluded_from_simulation
- BTCUSDT|SELL|aurora|MEAN_REVERSION|0.00..0.25 bucket_excluded_from_simulation
- BTCUSDT|SELL|aurora|TREND_DOWN|0.25..0.50 bucket_excluded_from_simulation
- ETHUSDT|BUY|aurora|LOW_VOLATILITY|0.00..0.25 bucket_excluded_from_simulation
- ETHUSDT|BUY|aurora|LOW_VOLATILITY|0.50..0.75 bucket_excluded_from_simulation
- ETHUSDT|BUY|aurora|LOW_VOLATILITY|0.75..1.00 bucket_excluded_from_simulation
- ETHUSDT|BUY|aurora|TREND_UP|0.00..0.25 bucket_excluded_from_simulation
- XRPUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50 bucket_excluded_from_simulation
- XRPUSDT|BUY|aurora|MEAN_REVERSION|0.25..0.50 bucket_excluded_from_simulation
- XRPUSDT|BUY|aurora|TREND_UP|0.25..0.50 bucket_excluded_from_simulation
- XRPUSDT|SELL|aurora|LOW_VOLATILITY|0.00..0.25 bucket_excluded_from_simulation
- XRPUSDT|SELL|aurora|MEAN_REVERSION|0.00..0.25 bucket_excluded_from_simulation
- XRPUSDT|SELL|aurora|MEAN_REVERSION|0.25..0.50 bucket_excluded_from_simulation
- XRPUSDT|SELL|aurora|MEAN_REVERSION|0.50..0.75 bucket_excluded_from_simulation
- BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.50..0.75 bucket_excluded_from_simulation
- ETHUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50 bucket_excluded_from_simulation
- ETHUSDT|SELL|aurora|LOW_VOLATILITY|0.00..0.25 bucket_excluded_from_simulation
- ETHUSDT|SELL|aurora|TREND_DOWN|0.00..0.25 bucket_excluded_from_simulation
- XRPUSDT|SELL|aurora|LOW_VOLATILITY|0.25..0.50 bucket_excluded_from_simulation
- BTCUSDT|SELL|aurora|LOW_VOLATILITY|0.25..0.50 bucket_excluded_from_simulation
- BTCUSDT|SELL|aurora|MEAN_REVERSION|0.25..0.50 bucket_excluded_from_simulation
- ETHUSDT|SELL|aurora|LOW_VOLATILITY|0.50..0.75 bucket_excluded_from_simulation

## Counterfactual Method
- Reconstruct validation-window atoms per context by replaying the same chronological split logic used in POC_03.
- For `POLICY_TOO_STRICT_CANDIDATE`, treat `POLICY_TOO_STRICT` rows as opportunity candidates and `POLICY_PROTECTED` rows as avoided-loss candidates.
- Use `outcome_snapshot.post_move_bps` at T+30m as the counterfactual move proxy.
- Apply conservative asymmetry: opportunity gains are discounted by a 0.50 fill factor; added loss risk is kept at 1.00.
- Subtract a 10.0 bps fee/slippage buffer and a 2.0 bps execution haircut per hypothetical trade.

## Opportunity Gain Estimate
- aggregate conservative opportunity_gain_bps: 90.212982
- BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50: raw=180.425965 conservative=90.212982

## Added Loss Risk Estimate
- aggregate conservative added_loss_risk_bps: 50.132205
- BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50: raw=50.132205 conservative=50.132205

## Fee/Slippage Assumptions
- default fee_slippage_buffer_bps_per_trade: 10.0
- aggregate fee_slippage_buffer_bps: 110.0
- conservative opportunity fill factor: 0.5
- conservative risk fill factor: 1.0
- execution haircut bps per trade: 2.0

## Conservative Net Impact
- aggregate conservative net impact bps: -91.919223
- BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50: -91.919223

## Sensitivity Bands
- BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50
  pessimistic: opportunity_gain_bps=45.106491 added_loss_risk_bps=50.132205 fee_slippage_buffer_bps=110.0 execution_haircut_bps=33.0 net_impact_bps=-148.025714
  conservative: opportunity_gain_bps=90.212982 added_loss_risk_bps=50.132205 fee_slippage_buffer_bps=110.0 execution_haircut_bps=22.0 net_impact_bps=-91.919223
  optimistic: opportunity_gain_bps=135.319474 added_loss_risk_bps=37.599154 fee_slippage_buffer_bps=110.0 execution_haircut_bps=11.0 net_impact_bps=-23.27968

## Residual Risks
- BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50: Rejected intents are not guaranteed to have filled if policy had been relaxed.
- BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50: Recorder forward moves do not prove exchange fill quality or queue position.
- BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50: Counterfactual scoring uses post-move bps as a proxy for realized economics, not a full execution replay.

## Recommendation
- Do not advance this context to a relaxation shadow package without new evidence.

