"""J6-S12.1 — Post-Fix Regime-Aware Replay Dataset Generation.

This script generates bounded Judge envelope + verdict + shadow_entry_plan
data through the J6-S11-patched code path, ensuring every envelope has
either non-null regime fields or explicit regime_missing_reason.

Strategy:
1. Load alpha_input_v1.jsonl snapshots (257k records, existing data)
2. Convert string regime -> dict regime (matching FE payload format)
3. Feed through ScenarioWorker -> AlphaSearchBacktestPlugin (J6-S11 path)
4. Write all judge artifacts to logs/judge_experts_j6_s12_1/ (bounded)
5. Verify regime coverage in output envelopes

Scope: alpha_search / LLM Judge replay/data-generation path ONLY.
No advisory, no promotion, no live execution, no config tuning.
"""
import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
)
LOG = logging.getLogger("j6_s12_1")

# ── Configuration ───────────────────────────────────────────────────────────
INPUT_PATH = PROJECT_ROOT / "logs" / "alpha_input" / "alpha_input_v1.jsonl"
OUTPUT_DIR = PROJECT_ROOT / "logs" / "judge_experts_j6_s12_1"
CONFIG_PATH = PROJECT_ROOT / "config" / "alpha_search.yaml"

# Bounded sample: take first N snapshots with real (non-PENDING) regimes
# plus a small sample of PENDING for REGIME_CONTEXT_MISSING verification
MAX_REGIME_SNAPSHOTS = 500
MAX_PENDING_SNAPSHOTS = 50


def load_alpha_search_config():
    """Load alpha_search config with judge shadow_log redirected to bounded dir."""
    from apps.reference.domains.alpha_search.config_models import (
        AlphaSearchConfig,
    )

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    cfg_data = raw["alpha_search"]

    # Override shadow_log.log_dir to bounded output
    if "judge" in cfg_data and "shadow_log" in cfg_data["judge"]:
        cfg_data["judge"]["shadow_log"]["log_dir"] = str(OUTPUT_DIR)

    return AlphaSearchConfig.model_validate(cfg_data)


def build_regime_dict(regime_str: str) -> dict | None:
    """Convert regime string to dict matching the FE CMD:PROCESS_STRATEGY format.

    The live FE path (feature_engineering.py:2288-2304) sends regime as:
        {"regime": "TREND_UP", "confidence": 0.87, "source_model": "...", ...}

    The alpha_input_v1.jsonl only has a string label. We synthesize the
    minimal dict that _on_decision_score (backtest_plugin.py:616-623) requires.

    Returns None for "PENDING"/"DEFAULT" to test REGIME_CONTEXT_MISSING path.
    """
    if regime_str in ("PENDING", "DEFAULT", "", None):
        return None  # Will trigger REGIME_CONTEXT_MISSING

    return {
        "regime": regime_str,
        "confidence": 0.75,  # Synthetic but realistic for replay
        "ts_ms": int(time.time() * 1000),
        "source_model": "aurora_regime_v1",
    }


def select_bounded_sample(input_path: Path) -> list[dict]:
    """Select a bounded sample with regime diversity.

    Selects up to MAX_REGIME_SNAPSHOTS with real regimes and
    MAX_PENDING_SNAPSHOTS with PENDING to verify both paths.
    """
    regime_rows = []
    pending_rows = []
    regime_counter = Counter()

    LOG.info("Scanning %s for bounded sample...", input_path)
    total = 0
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            total += 1
            row = json.loads(line)
            regime = row.get("regime", "PENDING")

            if regime in ("PENDING", "DEFAULT"):
                if len(pending_rows) < MAX_PENDING_SNAPSHOTS:
                    pending_rows.append(row)
            else:
                if len(regime_rows) < MAX_REGIME_SNAPSHOTS:
                    regime_rows.append(row)
                    regime_counter[regime] += 1

            if (
                len(regime_rows) >= MAX_REGIME_SNAPSHOTS
                and len(pending_rows) >= MAX_PENDING_SNAPSHOTS
            ):
                break

    LOG.info(
        "Scanned %d rows. Selected %d regime + %d pending = %d total",
        total,
        len(regime_rows),
        len(pending_rows),
        len(regime_rows) + len(pending_rows),
    )
    LOG.info("Regime distribution in sample: %s", dict(regime_counter))

    return regime_rows + pending_rows


def run_through_plugin(config, snapshots: list[dict]) -> dict:
    """Feed snapshots through AlphaSearchBacktestPlugin with J6-S11 patch active.

    Uses the same pipeline as ScenarioWorker but with regime dict conversion.
    """
    from apps.reference.orchestrator.utils_event_bus import LocalBus
    from apps.reference.domains.alpha_search.backtest_plugin import (
        AlphaSearchBacktestPlugin,
    )

    bus = LocalBus()
    plugin = AlphaSearchBacktestPlugin(
        event_bus=bus,
        config=config,
    )

    stats = {
        "snapshots_fed": 0,
        "cache_phase_ok": 0,
        "score_phase_ok": 0,
        "errors": 0,
    }

    for i, snapshot in enumerate(snapshots):
        try:
            symbol = snapshot["symbol"]
            tf_sec = snapshot.get("tf_sec", 300)
            bar_close_ts = snapshot.get("bar_close_ts", snapshot.get("ts_ms", 0))
            features = snapshot.get("features", {})
            regime_str = snapshot.get("regime", "PENDING")

            # Phase 1: Cache features
            feature_payload = {
                "symbol": symbol,
                "features": features,
                "tf_sec": tf_sec,
                "bar_close_ts": bar_close_ts,
                "ts": snapshot.get("ts_ms", 0),
                "bar": {"close_ts": bar_close_ts},
                "warmup_readiness": snapshot.get("warmup_status", {}),
            }
            bus.emit(
                event_name=config.triggers.feature_event,
                payload=feature_payload,
                why=f"j6_s12_1_replay:{i}",
            )
            stats["cache_phase_ok"] += 1

            # Phase 2: Trigger scoring with regime DICT (J6-S11 format)
            regime_dict = build_regime_dict(regime_str)
            decision_payload = {
                "symbol": symbol,
                "tf_sec": tf_sec,
                "bar_close_ts": bar_close_ts,
                "regime": regime_dict,  # Dict or None — not string!
            }
            bus.emit(
                event_name="CMD:PROCESS_STRATEGY",
                payload=decision_payload,
                why=f"j6_s12_1_replay_trigger:{i}",
            )
            stats["score_phase_ok"] += 1
            stats["snapshots_fed"] += 1

            if (i + 1) % 100 == 0:
                LOG.info("  Processed %d/%d snapshots", i + 1, len(snapshots))

        except Exception as e:
            stats["errors"] += 1
            LOG.warning("Snapshot %d error: %s", i, e)

    # Flush plugin shutdown (writes any remaining state)
    try:
        plugin.shutdown()
    except Exception:
        pass

    return stats


def verify_output(output_dir: Path) -> dict:
    """Verify the generated envelopes have regime data."""
    envelope_files = list(output_dir.glob("envelope_*.jsonl"))
    total = 0
    with_regime = 0
    with_missing_reason = 0
    no_regime_no_reason = 0
    regime_counter = Counter()

    for efile in envelope_files:
        with open(efile, "r", encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                total += 1
                regime = d.get("regime")
                reason = d.get("regime_missing_reason")

                if regime is not None:
                    with_regime += 1
                    regime_counter[regime] += 1
                elif reason is not None:
                    with_missing_reason += 1
                else:
                    no_regime_no_reason += 1

    verdict_files = list(output_dir.glob("verdict_*.jsonl"))
    verdict_count = 0
    for vfile in verdict_files:
        with open(vfile, "r", encoding="utf-8") as f:
            verdict_count += sum(1 for _ in f)

    plan_files = list(output_dir.glob("shadow_entry_plan_*.jsonl"))
    plan_count = 0
    for pfile in plan_files:
        with open(pfile, "r", encoding="utf-8") as f:
            plan_count += sum(1 for _ in f)

    return {
        "envelope_files": len(envelope_files),
        "total_envelopes": total,
        "with_non_null_regime": with_regime,
        "with_regime_missing_reason": with_missing_reason,
        "no_regime_no_reason_VIOLATION": no_regime_no_reason,
        "regime_coverage_pct": round(
            100.0 * with_regime / total, 1) if total > 0 else 0.0,
        "regime_distribution": dict(regime_counter),
        "verdict_files": len(verdict_files),
        "verdict_count": verdict_count,
        "plan_files": len(plan_files),
        "plan_count": plan_count,
    }


def main():
    LOG.info("=" * 80)
    LOG.info("J6-S12.1 — Post-Fix Regime-Aware Replay Dataset Generation")
    LOG.info("=" * 80)

    # Pre-checks
    if not INPUT_PATH.exists():
        LOG.error("Input not found: %s", INPUT_PATH)
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Clean previous output
    for f in OUTPUT_DIR.glob("*.jsonl"):
        f.unlink()
    LOG.info("Output directory cleaned: %s", OUTPUT_DIR)

    # Load config
    config = load_alpha_search_config()
    LOG.info("Config loaded. Judge mode=%s, shadow_log.log_dir=%s",
             config.judge.mode if config.judge else "N/A",
             config.judge.shadow_log.log_dir if config.judge and config.judge.shadow_log else "N/A")

    # Select bounded sample
    snapshots = select_bounded_sample(INPUT_PATH)
    if not snapshots:
        LOG.error("No snapshots selected. Aborting.")
        return

    # Run through plugin
    LOG.info("Running %d snapshots through J6-S11-patched plugin...", len(snapshots))
    run_stats = run_through_plugin(config, snapshots)
    LOG.info("Plugin run complete: %s", json.dumps(run_stats))

    # Verify output
    LOG.info("Verifying output...")
    verification = verify_output(OUTPUT_DIR)

    LOG.info("=" * 80)
    LOG.info("VERIFICATION RESULTS")
    LOG.info("=" * 80)
    for k, v in verification.items():
        LOG.info("  %-40s = %s", k, v)

    # J6-S12.1 pass/fail
    invariant_ok = verification["no_regime_no_reason_VIOLATION"] == 0
    has_regime_data = verification["with_non_null_regime"] > 0
    has_missing = verification["with_regime_missing_reason"] > 0

    LOG.info("")
    LOG.info("INVARIANT (every envelope has regime OR reason): %s",
             "PASS" if invariant_ok else "FAIL")
    LOG.info("HAS REGIME DATA: %s (count=%d)",
             "PASS" if has_regime_data else "FAIL",
             verification["with_non_null_regime"])
    LOG.info("HAS MISSING REASON: %s (count=%d)",
             "PASS" if has_missing else "FAIL",
             verification["with_regime_missing_reason"])

    # Save verification results
    results_path = OUTPUT_DIR / "j6_s12_1_verification.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({
            "run_stats": run_stats,
            "verification": verification,
            "invariant_ok": invariant_ok,
            "has_regime_data": has_regime_data,
            "has_missing_reason": has_missing,
            "ts": int(time.time()),
        }, f, indent=2)
    LOG.info("Results saved to %s", results_path)


if __name__ == "__main__":
    main()
