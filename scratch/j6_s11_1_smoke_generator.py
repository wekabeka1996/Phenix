import os
import json
import logging
from pathlib import Path

from apps.reference.domains.alpha_search.backtest_plugin import AlphaSearchBacktestPlugin
from apps.reference.domains.alpha_search.backtest_plugin import AlphaSearchBacktestPlugin, FeatureCacheEntry
from apps.reference.domains.alpha_search.config_models import AlphaSearchConfig, ProviderConfig, JudgeExpertProviderConfig
from apps.reference.domains.alpha_search.judge.config_models import JudgeCortexConfig, JudgeShadowLogConfig, ShadowPlanConfig, VerdictConfig, JudgeExpertsConfig, SignalWeightsExpertConfig, ConfidenceLadderTier, ChamberConfig
from vfoundation.core.protocol import Message

# Setup logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("apps.reference.domains.alpha_search").setLevel(logging.DEBUG)

class DummyBus:
    def emit(self, event_name, payload, **kwargs):
        pass

def main():
    smoke_dir = Path("reports/judge_shadow_sim/j6_s11_1_smoke")
    smoke_dir.mkdir(parents=True, exist_ok=True)
    
    # Clean previous
    for f in smoke_dir.glob("*.jsonl"):
        f.unlink()

    # 1. Config
    judge_cfg = JudgeCortexConfig(
        mode="shadow",
        chamber=ChamberConfig(entry_enabled=True, lifecycle_enabled=True),
        shadow_log=JudgeShadowLogConfig(enabled=True, log_dir=str(smoke_dir)),
        verdict=VerdictConfig(
            entry_enabled=True, 
            lifecycle_enabled=True,
            shadow_plan=ShadowPlanConfig(
                enabled=True, 
                emit_all_tiers=True,
                confidence_ladder=[
                    ConfidenceLadderTier(
                        name="medium",
                        min_confidence=0.3,
                        limit_offset_bps=0,
                        tp_offset_pct=0.01,
                        sl_offset_pct=0.01
                    ),
                    ConfidenceLadderTier(
                        name="high",
                        min_confidence=0.5,
                        limit_offset_bps=0,
                        tp_offset_pct=0.01,
                        sl_offset_pct=0.01
                    )
                ]
            )
        ),
        experts=JudgeExpertsConfig(
            signal_weights=SignalWeightsExpertConfig(
                enabled=True,
                signal_threshold=0.1,
                signal_weights={"obi": 0.5},
                feature_neutrals={"obi": 0.0},
                essential_features=["obi"]
            )
        )
    )
    
    cfg = AlphaSearchConfig(
        enabled=True,
        shadow_mode=True,
        providers={
            "dummy_expert": ProviderConfig(
                enabled=True,
                threshold=0.1,
                judge_expert=JudgeExpertProviderConfig(expert_type="signal_weights")
            )
        },
        judge=judge_cfg
    )

    # 2. Plugin setup
    plugin = AlphaSearchBacktestPlugin(event_bus=DummyBus(), config=cfg)

    symbol = "BTCUSDT"
    tf_sec = 300
    ts_ms = 1714000000000

    # 3. Inject features (canonical)
    cache_entry = FeatureCacheEntry(
        symbol=symbol,
        tf_sec=tf_sec,
        bar_close_ts=ts_ms,
        features={"obi": 0.5, "ema_bias": 0.2},
        ts=ts_ms
    )
    # The cache uses key: (symbol, tf_sec, bar_close_ts)
    plugin._feature_cache[(symbol, tf_sec, ts_ms)] = cache_entry

    # 4. Trigger with regime context
    cmd_payload = {
        "symbol": symbol,
        "tf_sec": tf_sec,
        "bar_close_ts": ts_ms,
        "regime": {
            "regime": "TREND_UP",
            "confidence": "0.87",
            "ts_ms": ts_ms,
            "source_model": "aurora_regime_v1"
        }
    }
    
    msg = Message(
        op="CMD",
        verb="PROCESS_STRATEGY",
        src="smoke",
        dst="plugin",
        pld=cmd_payload
    )

    print(f"Triggering _on_decision_score with regime: {cmd_payload['regime']['regime']}")
    plugin._on_decision_score(msg)

    # 5. Trigger another without regime (to prove missing reason)
    ts_ms_missing = 1714000300000
    cache_entry_missing = FeatureCacheEntry(
        symbol=symbol,
        tf_sec=tf_sec,
        bar_close_ts=ts_ms_missing,
        features={"obi": 0.1, "ema_bias": -0.1},
        ts=ts_ms_missing
    )
    plugin._feature_cache[(symbol, tf_sec, ts_ms_missing)] = cache_entry_missing
    
    cmd_payload_missing = {
        "symbol": symbol,
        "tf_sec": tf_sec,
        "bar_close_ts": ts_ms_missing,
        # No regime dict
    }
    msg_missing = Message(
        op="CMD",
        verb="PROCESS_STRATEGY",
        src="smoke",
        dst="plugin",
        pld=cmd_payload_missing
    )
    print(f"Triggering _on_decision_score without regime")
    plugin._on_decision_score(msg_missing)

    # 6. Create fake simulation row to test join script
    sim_results = [
        {
            "cycle_key": f"ENTRY:{symbol}:{tf_sec}:{ts_ms}",
            "symbol": symbol,
            "tf_sec": tf_sec,
            "ts_ms": ts_ms,
            "confidence_tier": "high",
            "entry_side": "BUY",
            "net_pnl_pct": 0.05,
            "outcome": "FILLED_TP"
        },
        {
            "cycle_key": f"ENTRY:{symbol}:{tf_sec}:{ts_ms_missing}",
            "symbol": symbol,
            "tf_sec": tf_sec,
            "ts_ms": ts_ms_missing,
            "confidence_tier": "medium",
            "entry_side": "BUY",
            "net_pnl_pct": -0.01,
            "outcome": "FILLED_SL"
        }
    ]
    with open(smoke_dir / "shadow_simulation_results.jsonl", "w") as f:
        for r in sim_results:
            f.write(json.dumps(r) + "\n")
            
    print("\nFiles generated:")
    for f in smoke_dir.glob("*.jsonl"):
        print(f"  {f.name}")

if __name__ == "__main__":
    main()
