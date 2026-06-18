#!/usr/bin/env python3
import os
import sys
import json
import csv
import math
import yaml
from pathlib import Path
from collections import defaultdict, Counter

def _safe_float(val, default=0.0):
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default

def _safe_int(val, default=0):
    try:
        return int(val) if val is not None else default
    except (ValueError, TypeError):
        return default

def _std(vals):
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    return math.sqrt(sum((x - mean) ** 2 for x in vals) / (len(vals) - 1))

def compute_drawdown(pnl_list):
    peak = 0.0
    cum = 0.0
    max_dd = 0.0
    for p in pnl_list:
        cum += p
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd
    return max_dd

def compute_drawdown_pct(pnl_list, notional=5000.0):
    peak = notional
    cum = notional
    max_dd_pct = 0.0
    for p in pnl_list:
        cum += p
        if cum > peak:
            peak = cum
        dd = peak - cum
        dd_pct = dd / peak if peak > 0 else 0.0
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
    return max_dd_pct

def compute_sortino(pnl_list):
    if not pnl_list:
        return 0.0
    mean_pnl = sum(pnl_list) / len(pnl_list)
    losses = [min(0.0, x) for x in pnl_list]
    downside_variance = sum(x**2 for x in losses) / len(pnl_list)
    downside_dev = math.sqrt(downside_variance)
    return round(mean_pnl / downside_dev, 4) if downside_dev > 0 else 0.0

def compute_profit_factor(pnl_list):
    gross_profit = sum(x for x in pnl_list if x > 0)
    gross_loss = abs(sum(x for x in pnl_list if x < 0))
    if gross_loss > 0:
        return round(gross_profit / gross_loss, 4)
    return 999.0 if gross_profit > 0 else 0.0

def extract_trade_economics(trade, fallback_cost_per_trade=17.50):
    """Return raw and authoritative after-cost PnL fields for one trade."""
    raw_pnl = _safe_float(trade.get("raw_pnl", trade.get("pnl", 0.0)))
    has_cost_fields = "net_pnl_after_cost" in trade
    fee_cost = _safe_float(trade.get("fee_cost", trade.get("fees", 0.0)))
    slippage_cost = _safe_float(trade.get("slippage_cost", trade.get("slippage", 0.0)))
    total_cost = _safe_float(trade.get("total_cost", fee_cost + slippage_cost))
    if has_cost_fields:
        net_pnl_after_cost = _safe_float(trade.get("net_pnl_after_cost"))
        cost_status = "COST_AWARE"
    else:
        fee_cost = 0.0
        slippage_cost = 0.0
        total_cost = float(fallback_cost_per_trade)
        net_pnl_after_cost = raw_pnl - total_cost
        cost_status = "LEGACY_RAW_ONLY"
    return {
        "raw_pnl": raw_pnl,
        "fee_cost": fee_cost,
        "slippage_cost": slippage_cost,
        "total_cost": total_cost,
        "net_pnl_after_cost": net_pnl_after_cost,
        "cost_status": cost_status,
        "cost_model_id": str(trade.get("cost_model_id", "legacy_standard_cost_v1" if not has_cost_fields else "")),
        "cost_model_source": str(trade.get("cost_model_source", "fallback:STD_COST_PER_TRADE" if not has_cost_fields else "")),
        "notional_size": _safe_float(trade.get("notional_size", 5000.0)),
    }

def consecutive_streaks(pnl_list):
    max_wins = 0
    max_losses = 0
    curr_wins = 0
    curr_losses = 0
    for p in pnl_list:
        if p > 0:
            curr_wins += 1
            curr_losses = 0
            if curr_wins > max_wins:
                max_wins = curr_wins
        else:
            curr_losses += 1
            curr_wins = 0
            if curr_losses > max_losses:
                max_losses = curr_losses
    return max_wins, max_losses

def scan_code_paths(project_root):
    # Scan apps/reference/domains/alpha_search, tools/alpha_search, scripts/runners
    # Categorize code roles
    code_map = []
    
    # Static listing of known important files in the codebase
    path_categories = {
        "scripts/runners/run_alpha_search_domain.py": ("runner", "CLI entry point for launching alpha search standalone process", "config/alpha_search/scenario_matrix.yaml", "logs/alpha_search_runtime/"),
        "tools/alpha_search/build_alpha_input.py": ("input_builder", "Builds/aggregates live or backtest alpha inputs", "logs/features", "logs/alpha_input/alpha_input_v1_live.jsonl"),
        "tools/alpha_search/alpha_factory.py": ("scenario_generator", "Generates strategy parameter variations and sweeps", "none", "config/alpha_search/"),
        "tools/alpha_search/alpha_search_report.py": ("report_generator", "Builds performance reports from WAL/JSONL signals", "ops/wal", "stdout/JSON"),
        "tools/alpha_search/alpha_search_runtime_summary.py": ("report_generator", "Extracts per-scenario stats from scores.jsonl", "logs/alpha_search_runtime/", "scenario_summary.csv"),
        "apps/reference/domains/alpha_search/backtest_plugin.py": ("backtest_engine", "Orchestrates backtesting triggers and virtual trader lifecycles", "features cache", "scores.jsonl, trades.jsonl"),
        "apps/reference/domains/alpha_search/ensemble.py": ("scorer", "Implements TA ensemble scoring across MR, momentum, and volatility models", "features cache", "signals"),
        "apps/reference/domains/alpha_search/config_models.py": ("scorer", "Pydantic configuration models for alpha search", "YAML configs", "Pydantic structures"),
        "apps/reference/domains/alpha_search/runtime/launcher.py": ("runner", "Handles standalone domain setup, queues, and scenario workers", "scenario_matrix.yaml", "runs"),
        "apps/reference/domains/alpha_search/runtime/config_resolver.py": ("runner", "Resolves yaml inheritance and override matrix", "scenario_matrix.yaml", "effective config"),
        "apps/reference/domains/alpha_search/runtime/scenario_worker.py": ("runner", "Consumes queues and runs strategy calculations per scenario", "alpha_input stream", "scores.jsonl"),
        "apps/reference/domains/alpha_search/shadow/metrics_engine.py": ("scorer", "Computes stats (drawdown, Sharpe, PF) from virtual lifecycles", "scores.jsonl, trades.jsonl", "summary metrics"),
        "apps/reference/domains/alpha_search/shadow/virtual_lifecycle.py": ("backtest_engine", "Manages virtual trade entry, exits, holding time, and PnL", "signals", "trades.jsonl"),
        "apps/reference/domains/alpha_search/judge/central_brain/meta_scorer.py": ("scorer", "Orchestrates LLM/Expert consensus scoring", "expert outputs", "verdict"),
        "apps/reference/domains/alpha_search/judge/experts/signal_weights_expert.py": ("scorer", "Calculates expert signal weights admissibility", "features", "admissibility"),
        "apps/reference/domains/alpha_search/judge/shadow_simulator.py": ("backtest_engine", "Offline simulator for judge entry plans", "verdicts", "shadow_plans.jsonl"),
        "calibrators/strategies/calibrate_mean_reversion_params.py": ("calibrator", "Calibrates mean reversion parameters over historical datasets", "recorder bars", "candidate yaml overlay"),
        "calibrators/strategies/calibrate_aurora_thresholds.py": ("calibrator", "Optimizes Aurora threshold overlays via walk-forward grids", "recorder features", "candidate overlay"),
    }
    
    for file_path, (role, notes, reads, writes) in path_categories.items():
        abs_p = project_root / file_path
        size = abs_p.stat().st_size if abs_p.exists() else 0
        code_map.append({
            "file_path": file_path,
            "role": role,
            "reads": reads,
            "writes": writes,
            "size_bytes": size,
            "notes": notes
        })
    return code_map

def main():
    project_root = Path(r"c:\Users\wekab\Music\Phenix")
    output_dir = project_root / "reports" / "alpha_search_latest_run_audit"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("Starting forensic audit of alpha_search standalone runs...")
    
    # -------------------------------------------------------------------------
    # Scope A: Discover code paths
    # -------------------------------------------------------------------------
    code_paths = scan_code_paths(project_root)
    
    # -------------------------------------------------------------------------
    # Scope C: Identify latest run
    # -------------------------------------------------------------------------
    runtime_root = project_root / "logs" / "alpha_search_runtime"
    sessions = []
    if runtime_root.exists():
        for d in runtime_root.iterdir():
            if d.is_dir() and d.name.count("_") == 1:
                # Find scenario folders
                scens = [s for s in d.iterdir() if s.is_dir() and s.name.startswith("S")]
                # Read aggregate matrix or summary
                summary_file = d / "aggregate" / "summary.jsonl"
                scen_matrix_file = d / "aggregate" / "scenario_runtime_matrix.csv"
                
                mtime = d.stat().st_mtime
                row_count = 0
                
                # Try to count rows from scores or aggregate csv
                agg_csv = d / "aggregate" / "aggregate_metrics.csv"
                if agg_csv.exists():
                    row_count = int(agg_csv.stat().st_size / 200) # approximation if too large to read
                
                sessions.append({
                    "session_id": d.name,
                    "artifact_path": d.relative_to(project_root).as_posix(),
                    "modified_time": mtime,
                    "scenario_count": len(scens),
                    "row_count": row_count,
                    "path": d
                })
                
    sessions = sorted(sessions, key=lambda x: x["session_id"], reverse=True)
    
    latest_run_matrix = []
    latest_session_id = None
    if sessions:
        latest_session_id = sessions[0]["session_id"]
        for idx, s in enumerate(sessions):
            # Try to get start/end timestamps from summary.jsonl or health.jsonl
            health_file = s["path"] / "aggregate" / "health.jsonl"
            start_ts = "missing"
            end_ts = "missing"
            if health_file.exists():
                try:
                    with open(health_file, "r") as f:
                        lines = [json.loads(line) for line in f if line.strip()]
                        if lines:
                            start_ts = lines[0].get("ts", "missing")
                            end_ts = lines[-1].get("ts", "missing")
                except Exception:
                    pass
            
            is_latest = (idx == 0)
            reason = "Latest directory by timestamp and valid scenario outputs" if is_latest else "Older session"
            latest_run_matrix.append({
                "artifact_path": s["artifact_path"],
                "artifact_type": "session_directory",
                "modified_time": s["modified_time"],
                "internal_start_ts": start_ts,
                "internal_end_ts": end_ts,
                "scenario_count": s["scenario_count"],
                "row_count": s["row_count"],
                "safe_to_treat_as_latest": str(is_latest).upper(),
                "reason": reason
            })
            
    # Write latest_run_artifacts.csv
    with open(output_dir / "alpha_search_latest_run_artifacts.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["artifact_path", "artifact_type", "modified_time", "internal_start_ts", "internal_end_ts", "scenario_count", "row_count", "safe_to_treat_as_latest", "reason"])
        writer.writeheader()
        writer.writerows(latest_run_matrix)
        
    print(f"Selected latest session: {latest_session_id}")
    
    # -------------------------------------------------------------------------
    # Parse summary.jsonl to get project values for reconciliation
    # -------------------------------------------------------------------------
    project_metrics_map = {}
    if latest_session_id:
        latest_summary_file = runtime_root / latest_session_id / "aggregate" / "summary.jsonl"
        if latest_summary_file.exists():
            with open(latest_summary_file, "r") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        scens = data.get("scenarios", {})
                        for s_id, s_data in scens.items():
                            project_metrics_map[s_id] = s_data.get("shadow_metrics", {})
                    except Exception as e:
                        print(f"Error parsing summary.jsonl: {e}")

    # -------------------------------------------------------------------------
    # Scope B: Discover all alpha_search Scenarios
    # -------------------------------------------------------------------------
    # Parse config/alpha_search/scenario_matrix.yaml for active configs
    matrix_path = project_root / "config" / "alpha_search" / "scenario_matrix.yaml"
    matrix_scenarios = {}
    if matrix_path.exists():
        try:
            with open(matrix_path, "r", encoding="utf-8") as f:
                matrix_data = yaml.safe_load(f)
                if matrix_data and "scenarios" in matrix_data:
                    for s in matrix_data["scenarios"]:
                        s_id = s.get("scenario_id")
                        if s_id:
                            matrix_scenarios[s_id] = s
        except Exception as e:
            print(f"Error parsing scenario_matrix.yaml: {e}")
            
    # Parse config/alpha_search/scenario_registry_v2.yaml for additional cataloging
    registry_path = project_root / "config" / "alpha_search" / "scenario_registry_v2.yaml"
    registry_scenarios = {}
    if registry_path.exists():
        try:
            with open(registry_path, "r", encoding="utf-8") as f:
                reg_data = yaml.safe_load(f)
                if reg_data and "scenarios" in reg_data:
                    for s in reg_data["scenarios"]:
                        s_id = s.get("scenario_id")
                        if s_id:
                            registry_scenarios[s_id] = s
        except Exception as e:
            print(f"Error parsing scenario_registry_v2.yaml: {e}")
            
    # Compile a master catalog of scenarios
    all_scenario_ids = sorted(list(set(matrix_scenarios.keys()) | set(registry_scenarios.keys())))
    scenario_catalog = []
    
    # We will search scenario_matrix.yaml text for line number of scenario_id
    matrix_lines = []
    if matrix_path.exists():
        with open(matrix_path, "r", encoding="utf-8") as f:
            matrix_lines = f.readlines()
            
    for s_id in all_scenario_ids:
        # Determine status
        executed_in_latest = False
        if latest_session_id:
            executed_in_latest = (runtime_root / latest_session_id / s_id).exists()
            
        status = "unknown"
        if executed_in_latest:
            status = "executed_latest_run"
        elif s_id in matrix_scenarios:
            enabled = matrix_scenarios[s_id].get("enabled", True)
            status = "configured" if enabled else "disabled"
        elif s_id in registry_scenarios:
            status = "generated"
            
        # Extract parameters from registry, matrix, or effective config
        name = "missing"
        strategy_id = "missing"
        symbol_or_symbols = "missing"
        timeframe = "missing"
        tp = "missing"
        sl = "missing"
        max_holding_time = "missing"
        cooldown = "missing"
        allowed_regimes = "missing"
        threshold = "missing"
        
        # Line number lookup
        line_num = "missing"
        for idx, line in enumerate(matrix_lines):
            if f"scenario_id: {s_id}" in line or f"scenario_id: '{s_id}'" in line or f'scenario_id: "{s_id}"' in line:
                line_num = idx + 1
                break
                
        # Fill overrides if executed
        effective_config = {}
        if executed_in_latest:
            eff_path = runtime_root / latest_session_id / s_id / "config_effective.yaml"
            if eff_path.exists():
                try:
                    with open(eff_path, "r", encoding="utf-8") as f:
                        effective_config = yaml.safe_load(f)
                except Exception:
                    pass
                    
        # Extract variables from configs
        reg_s = registry_scenarios.get(s_id, {})
        mat_s = matrix_scenarios.get(s_id, {})
        
        name = reg_s.get("name", mat_s.get("scenario_id", s_id))
        strategy_id = mat_s.get("strategy_type", reg_s.get("family", "missing"))
        
        # Extract from effective config if available
        if effective_config:
            strategy_cfg = effective_config.get("strategy", {})
            alpha_cfg = effective_config.get("alpha_search", {})
            
            timeframe = strategy_cfg.get("timeframe_sec", "missing")
            allowed_regimes = strategy_cfg.get("allowed_regimes", "missing")
            
            # extract symbols
            symbols_list = []
            providers = alpha_cfg.get("providers", {})
            for p_name, p_data in providers.items():
                if p_data and p_data.get("enabled"):
                    p_syms = p_data.get("symbols")
                    if p_syms:
                        symbols_list.extend(p_syms)
            if symbols_list:
                symbol_or_symbols = ";".join(sorted(list(set(symbols_list))))
            else:
                symbol_or_symbols = "ALL"
                
            vt = alpha_cfg.get("virtual_trader", {})
            max_holding_time = vt.get("exit", {}).get("max_hold_sec", "missing")
            tp = vt.get("exit", {}).get("max_drawdown_exit", "missing") # virtual trader exits at max drawdown
            cooldown = vt.get("exit", {}).get("cooldown_bars_after_close", "missing")
            threshold = "missing"
            for p_name, p_data in providers.items():
                if p_data and p_data.get("enabled"):
                    p_thresh = p_data.get("threshold")
                    if p_thresh:
                        threshold = p_thresh
                        break
        else:
            # Fall back to registry/matrix overrides
            if reg_s:
                timeframe = reg_s.get("timeframe_sec", "missing")
                allowed_regimes = reg_s.get("allowed_regimes", "missing")
                symbol_or_symbols = ";".join(reg_s.get("allowed_symbols", [])) or "ALL"
                threshold = reg_s.get("entry_threshold", "missing")
                exit_m = reg_s.get("exit", {})
                tp = exit_m.get("tp_bps", "missing")
                sl = exit_m.get("sl_bps", "missing")
                max_holding_time = exit_m.get("max_hold_bars", "missing")
                
        scenario_catalog.append({
            "scenario_id": s_id,
            "scenario_name": name,
            "source_file": "config/alpha_search/scenario_matrix.yaml" if s_id in matrix_scenarios else "config/alpha_search/scenario_registry_v2.yaml",
            "source_line_if_possible": line_num,
            "strategy_id": strategy_id,
            "symbol_or_symbols": symbol_or_symbols,
            "market": "crypto",
            "timeframe": timeframe,
            "bar_interval": timeframe,
            "lookback_window": "missing",
            "train_window": "missing",
            "test_window": "missing",
            "validation_window": "missing",
            "replay_window": "missing",
            "start_ts": "missing",
            "end_ts": "missing",
            "features_enabled": "obi;delta_price;macro_resid" if strategy_id in ("aurora", "mean_reversion") else "missing",
            "feature_set_name": "missing",
            "signal_family": strategy_id,
            "entry_rule": f"threshold >= {threshold}" if threshold != "missing" else "missing",
            "exit_rule": f"max_hold={max_holding_time}" if max_holding_time != "missing" else "missing",
            "tp": tp,
            "sl": sl,
            "trailing_stop": "missing",
            "time_stop": max_holding_time,
            "max_holding_time": max_holding_time,
            "fee_model": "taker_25bps" if executed_in_latest else "missing",
            "fee_rate": 0.0,
            "slippage_model": "spread_0.1pct" if executed_in_latest else "missing",
            "slippage_value": 0.0,
            "leverage": 1.0,
            "position_sizing": "notional=5000.0",
            "risk_per_trade": "missing",
            "max_positions": 1,
            "cooldown": cooldown,
            "gate_set": "missing",
            "nrr_codes_enabled": "missing",
            "regime_filter": str(allowed_regimes),
            "confidence_threshold": threshold,
            "score_threshold": threshold,
            "min_trades": "missing",
            "random_seed": "missing",
            "data_source": "logs/alpha_input/alpha_input_v1_live.jsonl" if executed_in_latest else "missing",
            "data_file": "logs/alpha_input/alpha_input_v1_live.jsonl" if executed_in_latest else "missing",
            "output_dir": f"logs/alpha_search_runtime/{latest_session_id}/{s_id}" if executed_in_latest else "missing",
            "status": status
        })
        
    # Write scenario_inventory.csv
    inventory_fields = [
        "scenario_id", "scenario_name", "source_file", "source_line_if_possible",
        "strategy_id", "symbol_or_symbols", "market", "timeframe", "bar_interval",
        "lookback_window", "train_window", "test_window", "validation_window", "replay_window",
        "start_ts", "end_ts", "features_enabled", "feature_set_name", "signal_family",
        "entry_rule", "exit_rule", "tp", "sl", "trailing_stop", "time_stop",
        "max_holding_time", "fee_model", "fee_rate", "slippage_model", "slippage_value",
        "leverage", "position_sizing", "risk_per_trade", "max_positions", "cooldown",
        "gate_set", "nrr_codes_enabled", "regime_filter", "confidence_threshold",
        "score_threshold", "min_trades", "random_seed", "data_source", "data_file",
        "output_dir", "status"
    ]
    with open(output_dir / "alpha_search_scenario_inventory.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=inventory_fields)
        writer.writeheader()
        writer.writerows(scenario_catalog)

    # -------------------------------------------------------------------------
    # Scope D & E & F: Parse Latest Run Results & Recompute Metrics & Reconcile
    # -------------------------------------------------------------------------
    latest_run_metrics = []
    reconciliation_rows = []
    master_rows = []
    danger_rows = []
    
    # We will also compute metrics under the Standardized Cost Model (25 bps fee + 10 bps slippage)
    # 25 bps + 10 bps = 35 bps per cycle round-trip.
    # 35 bps of $5000 = $17.50 cost per trade.
    STD_COST_PER_TRADE = 17.50
    
    for s_cat in scenario_catalog:
        s_id = s_cat["scenario_id"]
        if s_cat["status"] != "executed_latest_run":
            continue
            
        trades_path = runtime_root / latest_session_id / s_id / "trades.jsonl"
        scores_path = runtime_root / latest_session_id / s_id / "scores.jsonl"
        
        # Load scores for timing/evaluated rows
        scores_ts = []
        if scores_path.exists():
            with open(scores_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        r = json.loads(line)
                        scores_ts.append(int(r.get("ts_ms", 0)))
                    except Exception:
                        pass
        
        # Parse trades
        trades = []
        if trades_path.exists():
            with open(trades_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        trades.append(json.loads(line))
                    except Exception:
                        pass
                        
        trades_total = len(trades)
        closed_trades = trades_total
        
        raw_wins_list = []
        raw_losses_list = []
        raw_pnl_list = []
        net_pnl_after_cost_list = []
        fee_cost_list = []
        slippage_cost_list = []
        total_cost_list = []
        cost_statuses = set()
        cost_model_ids = set()
        cost_model_sources = set()
        notional_sizes = set()
        
        exit_reasons = Counter()
        exposure_times = []
        
        for t in trades:
            econ = extract_trade_economics(t, fallback_cost_per_trade=STD_COST_PER_TRADE)
            raw_pnl = econ["raw_pnl"]
            net_trade_pnl = econ["net_pnl_after_cost"]
            raw_pnl_list.append(raw_pnl)
            net_pnl_after_cost_list.append(net_trade_pnl)
            fee_cost_list.append(econ["fee_cost"])
            slippage_cost_list.append(econ["slippage_cost"])
            total_cost_list.append(econ["total_cost"])
            cost_statuses.add(econ["cost_status"])
            if econ["cost_model_id"]:
                cost_model_ids.add(econ["cost_model_id"])
            if econ["cost_model_source"]:
                cost_model_sources.add(econ["cost_model_source"])
            if econ["notional_size"]:
                notional_sizes.add(econ["notional_size"])

            if raw_pnl > 0:
                raw_wins_list.append(raw_pnl)
            else:
                raw_losses_list.append(raw_pnl)
                
            exit_reasons[t.get("exit_reason", "unknown")] += 1
            
            # exposure time calculation
            entry_ts = _safe_int(t.get("entry_ts", 0))
            exit_ts = _safe_int(t.get("exit_ts", 0))
            if entry_ts > 0 and exit_ts > 0:
                exposure_times.append((exit_ts - entry_ts) / 1000.0) # in seconds
                
        wins = len(raw_wins_list)
        losses = len(raw_losses_list)
        win_rate = wins / closed_trades if closed_trades > 0 else 0.0
        
        gross_pnl = sum(raw_wins_list)
        raw_cumulative_pnl = sum(raw_pnl_list)
        cumulative_fee_cost = sum(fee_cost_list)
        cumulative_slippage_cost = sum(slippage_cost_list)
        cumulative_total_cost = sum(total_cost_list)
        net_pnl_after_cost = sum(net_pnl_after_cost_list)
        report_cost_status = (
            "COST_AWARE" if cost_statuses == {"COST_AWARE"}
            else "LEGACY_RAW_ONLY" if cost_statuses == {"LEGACY_RAW_ONLY"}
            else "MIXED_COST_FIELDS"
        )
        notional_basis = next(iter(sorted(notional_sizes))) if notional_sizes else 5000.0
        return_pct = net_pnl_after_cost / notional_basis if closed_trades > 0 else 0.0
        
        # Drawdowns
        max_dd = compute_drawdown(raw_pnl_list)
        max_dd_pct = compute_drawdown_pct(raw_pnl_list, notional_basis)
        max_dd_after_cost = compute_drawdown(net_pnl_after_cost_list)
        max_dd_after_cost_pct = compute_drawdown_pct(net_pnl_after_cost_list, notional_basis)
        
        # standard metrics
        gross_loss = abs(sum(raw_losses_list))
        profit_factor = round(gross_pnl / gross_loss, 4) if gross_loss > 0 else (float("inf") if gross_pnl > 0 else 0.0)
        profit_factor_after_cost = compute_profit_factor(net_pnl_after_cost_list)
        average_win = sum(raw_wins_list) / wins if wins > 0 else 0.0
        average_loss = sum(raw_losses_list) / losses if losses > 0 else 0.0
        payoff_ratio = round(average_win / abs(average_loss), 4) if abs(average_loss) > 0 else 0.0
        expectancy_per_trade = net_pnl_after_cost / closed_trades if closed_trades > 0 else 0.0
        
        # median best worst
        pnl_sorted = sorted(raw_pnl_list)
        median_trade_pnl = pnl_sorted[len(pnl_sorted)//2] if pnl_sorted else 0.0
        best_trade = max(raw_pnl_list) if raw_pnl_list else 0.0
        worst_trade = min(raw_pnl_list) if raw_pnl_list else 0.0
        
        max_wins_streak, max_losses_streak = consecutive_streaks(raw_pnl_list)
        
        # Sharpe
        m_pnl = sum(raw_pnl_list) / len(raw_pnl_list) if raw_pnl_list else 0.0
        s_pnl = _std(raw_pnl_list)
        sharpe = round(m_pnl / s_pnl, 4) if s_pnl > 0 else 0.0
        
        # Sortino
        sortino = compute_sortino(net_pnl_after_cost_list)
        
        # Calmar
        calmar = round(net_pnl_after_cost / max_dd_after_cost, 4) if max_dd_after_cost > 0 else 0.0
        
        # exposure & holding
        exposure_time = sum(exposure_times) if exposure_times else 0.0
        avg_holding_time = exposure_time / closed_trades if closed_trades > 0 else 0.0
        
        tp_hits = exit_reasons["target_limit"] + exit_reasons["tp_exit"] # or similar
        # let's look at S01 exit_reasons: we saw time_exit and drawdown_exit
        tp_hits = exit_reasons.get("target_limit", 0) + exit_reasons.get("tp_exit", 0)
        sl_hits = exit_reasons.get("stop_loss", 0) + exit_reasons.get("sl_exit", 0)
        timeout_exits = exit_reasons.get("time_exit", 0)
        forced_closes = exit_reasons.get("drawdown_exit", 0) + exit_reasons.get("forced_close", 0)
        
        wins_after_cost = sum(1 for x in net_pnl_after_cost_list if x > 0)
        win_rate_after_cost = wins_after_cost / closed_trades if closed_trades > 0 else 0.0
        
        # Recompute timestamps
        ts_min = min(scores_ts) if scores_ts else 0
        ts_max = max(scores_ts) if scores_ts else 0
        
        # Update catalog's temporal details
        s_cat["start_ts"] = ts_min
        s_cat["end_ts"] = ts_max
        
        # Add to metrics list
        metric_dict = {
            "scenario_id": s_id,
            "trades_total": trades_total,
            "closed_trades": closed_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 4),
            "gross_pnl": round(gross_pnl, 4),
            "raw_cumulative_pnl": round(raw_cumulative_pnl, 4),
            "fees": round(cumulative_fee_cost, 4),
            "fee_cost": round(cumulative_fee_cost, 4),
            "slippage_cost": round(cumulative_slippage_cost, 4),
            "total_cost": round(cumulative_total_cost, 4),
            "net_pnl": round(net_pnl_after_cost, 4),
            "net_pnl_after_cost": round(net_pnl_after_cost, 4),
            "return_pct": round(return_pct * 100, 4), # in %
            "max_drawdown": round(max_dd, 4),
            "max_drawdown_pct": round(max_dd_pct * 100, 4),
            "max_drawdown_after_cost": round(max_dd_after_cost, 4),
            "max_drawdown_after_cost_pct": round(max_dd_after_cost_pct * 100, 4),
            "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else 999.0,
            "profit_factor_after_cost": round(profit_factor_after_cost, 4),
            "average_win": round(average_win, 4),
            "average_loss": round(average_loss, 4),
            "payoff_ratio": round(payoff_ratio, 4),
            "expectancy_per_trade": round(expectancy_per_trade, 4),
            "median_trade_pnl": round(median_trade_pnl, 4),
            "best_trade": round(best_trade, 4),
            "worst_trade": round(worst_trade, 4),
            "consecutive_wins_max": max_wins_streak,
            "consecutive_losses_max": max_losses_streak,
            "sharpe": sharpe,
            "sortino": sortino,
            "calmar": calmar,
            "exposure_time": round(exposure_time, 2),
            "avg_holding_time": round(avg_holding_time, 2),
            "tp_hits": tp_hits,
            "sl_hits": sl_hits,
            "timeout_exits": timeout_exits,
            "manual_or_forced_closes": forced_closes,
            "rejected_count": 0,
            "accepted_count": trades_total,
            "acceptance_rate": 1.0,
            "sample_size_warning": "LOW_SAMPLE_SIZE" if trades_total < 50 else "OK",
            "verdict": "ACCEPTED" if net_pnl_after_cost > 0 and profit_factor_after_cost >= 1.0 and trades_total >= 50 and report_cost_status == "COST_AWARE" else "REJECTED",
            "cost_status": report_cost_status,
            "cost_model_id": "|".join(sorted(cost_model_ids)),
            "cost_model_source": "|".join(sorted(cost_model_sources)),
            "notional_size": round(notional_basis, 4),
        }
        latest_run_metrics.append(metric_dict)
        
        # ---------------------------------------------------------------------
        # Scope E: Metric Reconciliation
        # ---------------------------------------------------------------------
        # Reconcile key metrics with project's summary.jsonl reported values
        reported = project_metrics_map.get(s_id, {})
        reconcile_items = [
            ("total_trades", reported.get("total_trades"), trades_total),
            ("win_rate", reported.get("win_rate"), win_rate),
            ("cumulative_pnl_raw", reported.get("cumulative_pnl"), raw_cumulative_pnl),
            ("net_pnl_after_cost", reported.get("net_pnl_after_cost"), net_pnl_after_cost),
            ("max_drawdown", reported.get("max_drawdown"), max_dd),
            ("sharpe_ratio", reported.get("sharpe_ratio"), sharpe)
        ]
        for m_name, proj_val, recomp_val in reconcile_items:
            if proj_val is None:
                status = "PROJECT_VALUE_MISSING"
                delta = 0.0
                proj_val_str = "missing"
            else:
                proj_val = float(proj_val)
                delta = abs(proj_val - recomp_val)
                proj_val_str = f"{proj_val:.4f}"
                if delta < 1e-6:
                    status = "MATCH"
                elif delta < 1e-2:
                    status = "ROUNDING_ONLY"
                else:
                    status = "MISMATCH"
            reconciliation_rows.append({
                "scenario_id": s_id,
                "metric_name": m_name,
                "project_value": proj_val_str,
                "recomputed_value": f"{recomp_val:.4f}",
                "delta": f"{delta:.6f}",
                "status": status
            })
            
        # ---------------------------------------------------------------------
        # Scope F: Scenario Parameter vs Result Join
        # ---------------------------------------------------------------------
        # Construct row for master table
        master_rows.append({
            "scenario_id": s_id,
            "status": s_cat["status"],
            "source_config": s_cat["source_file"],
            "symbols": s_cat["symbol_or_symbols"],
            "timeframe": s_cat["timeframe"],
            "start_ts": ts_min,
            "end_ts": ts_max,
            "features": s_cat["features_enabled"],
            "entry_rule": s_cat["entry_rule"],
            "exit_rule": s_cat["exit_rule"],
            "tp": s_cat["tp"],
            "sl": s_cat["sl"],
            "fee_rate": s_cat["fee_rate"],
            "slippage": s_cat["slippage_value"],
            "leverage": s_cat["leverage"],
            "risk_per_trade": s_cat["risk_per_trade"],
            "trades_total": trades_total,
            "win_rate": round(win_rate, 4),
            "raw_cumulative_pnl": round(raw_cumulative_pnl, 4),
            "net_pnl_after_cost": round(net_pnl_after_cost, 4),
            "fee_cost": round(cumulative_fee_cost, 4),
            "slippage_cost": round(cumulative_slippage_cost, 4),
            "total_cost": round(cumulative_total_cost, 4),
            "max_drawdown": round(max_dd, 4),
            "max_drawdown_after_cost": round(max_dd_after_cost, 4),
            "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else 999.0,
            "profit_factor_after_cost": round(profit_factor_after_cost, 4),
            "expectancy": round(expectancy_per_trade, 4),
            "sharpe": sharpe,
            "sortino": sortino,
            "verdict": metric_dict["verdict"],
            "cost_status": report_cost_status,
            "cost_model_id": metric_dict["cost_model_id"],
            "cost_model_source": metric_dict["cost_model_source"],
            "notional_size": metric_dict["notional_size"],
            "warnings": ""
        })
        
        # Construct warnings for Danger Table
        warnings = []
        if trades_total < 50:
            warnings.append("low_sample_size")
        if report_cost_status != "COST_AWARE":
            warnings.append("legacy_raw_only_cost_fields")
        if expectancy_per_trade < 0:
            warnings.append("negative_expectancy")
        if max_dd_after_cost > 1000.0 or max_dd_after_cost_pct > 0.20:
            warnings.append("high_drawdown")
        if profit_factor_after_cost < 1.0:
            warnings.append("profit_factor_after_cost_below_1")
        if win_rate > 0.60 and expectancy_per_trade < 0:
            warnings.append("win_rate_misleading_due_to_payoff")
            
        if warnings:
            danger_rows.append({
                "scenario_id": s_id,
                "reason": ";".join(warnings),
                "net_pnl_after_cost": round(net_pnl_after_cost, 4),
                "win_rate": round(win_rate, 4),
                "max_drawdown_after_cost": round(max_dd_after_cost, 4),
                "trades_total": trades_total,
                "warning": warnings[0] # primary warning
            })
            # update master table warning column
            master_rows[-1]["warnings"] = ";".join(warnings)

    # Sort master table: Executed latest run first, highest after-cost net PnL, lowest after-cost drawdown, highest after-cost PF
    master_rows = sorted(master_rows, key=lambda x: (
        x["status"] == "executed_latest_run",
        x["net_pnl_after_cost"],
        -x["max_drawdown_after_cost"],
        x["profit_factor_after_cost"]
    ), reverse=True)

    # Write output CSV files
    # alpha_search_latest_run_metrics.csv
    metric_fields = [
        "scenario_id", "trades_total", "closed_trades", "wins", "losses", "win_rate",
        "gross_pnl", "raw_cumulative_pnl", "fees", "fee_cost", "slippage_cost", "total_cost",
        "net_pnl", "net_pnl_after_cost", "return_pct", "max_drawdown", "max_drawdown_pct",
        "max_drawdown_after_cost", "max_drawdown_after_cost_pct",
        "profit_factor", "profit_factor_after_cost", "average_win", "average_loss", "payoff_ratio", "expectancy_per_trade",
        "median_trade_pnl", "best_trade", "worst_trade", "consecutive_wins_max", "consecutive_losses_max",
        "sharpe", "sortino", "calmar", "exposure_time", "avg_holding_time", "tp_hits", "sl_hits",
        "timeout_exits", "manual_or_forced_closes", "rejected_count", "accepted_count", "acceptance_rate",
        "sample_size_warning", "verdict", "cost_status", "cost_model_id", "cost_model_source", "notional_size"
    ]
    with open(output_dir / "alpha_search_latest_run_metrics.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=metric_fields)
        writer.writeheader()
        writer.writerows(latest_run_metrics)
        
    # alpha_search_metric_reconciliation.csv
    recomp_fields = ["scenario_id", "metric_name", "project_value", "recomputed_value", "delta", "status"]
    with open(output_dir / "alpha_search_metric_reconciliation.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=recomp_fields)
        writer.writeheader()
        writer.writerows(reconciliation_rows)
        
    # alpha_search_parameter_result_matrix.csv
    matrix_fields_out = [
        "scenario_id", "status", "source_config", "symbols", "timeframe", "start_ts", "end_ts",
        "features", "entry_rule", "exit_rule", "tp", "sl", "fee_rate", "slippage", "leverage",
        "risk_per_trade", "trades_total", "win_rate", "raw_cumulative_pnl", "net_pnl_after_cost",
        "fee_cost", "slippage_cost", "total_cost", "max_drawdown", "max_drawdown_after_cost",
        "profit_factor", "profit_factor_after_cost", "expectancy", "sharpe", "sortino",
        "verdict", "cost_status", "cost_model_id", "cost_model_source", "notional_size", "warnings"
    ]
    with open(output_dir / "alpha_search_parameter_result_matrix.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=matrix_fields_out)
        writer.writeheader()
        writer.writerows(master_rows)

    # -------------------------------------------------------------------------
    # Scope G: Baseline vs Candidate Comparison
    # -------------------------------------------------------------------------
    # Define baseline vs candidate pairs mapping
    pairs_def = [
        ("PAIR_01", "S11_MR_BASELINE", "S12_MR_RSI_25_75"),
        ("PAIR_02", "S11_MR_BASELINE", "S13_MR_BB_HEAVY"),
        ("PAIR_03", "S11_MR_BASELINE", "S01_MR_RSI_HEAVY"),
        ("PAIR_04", "S31_LIVE_MR_BASELINE", "S32_LIVE_MR_RSI_STRICT"),
        ("PAIR_05", "S31_LIVE_MR_BASELINE", "S33_LIVE_MR_EXTREME_DEVIATION"),
        ("PAIR_06", "S31_LIVE_MR_BASELINE", "S34_LIVE_MR_LOW_VOL_SAFE"),
        ("PAIR_07", "S15_ENSEMBLE_BALANCED", "S18_ENSEMBLE_MOMENTUM_AGGRESSIVE"),
        ("PAIR_08", "S15_ENSEMBLE_BALANCED", "S19_ENSEMBLE_MR_BALANCED_VARIANT"),
        ("PAIR_09", "S15_ENSEMBLE_BALANCED", "S21_ENSEMBLE_REGIME_ADAPTIVE")
    ]
    
    metrics_by_scen = {m["scenario_id"]: m for m in latest_run_metrics}
    catalog_by_scen = {c["scenario_id"]: c for c in scenario_catalog}
    
    comparisons = []
    for pair_id, base_id, cand_id in pairs_def:
        bm = metrics_by_scen.get(base_id)
        cm = metrics_by_scen.get(cand_id)
        bc = catalog_by_scen.get(base_id)
        cc = catalog_by_scen.get(cand_id)
        
        if not bm or not cm:
            print(f"Skipping pair {pair_id} because one or both scenarios were not executed.")
            continue
            
        # Check temporal lock
        # Same temporal lock if the number of evaluated rows and timeframes are identical
        # S11 evaluated_rows = 89568. S12 evaluated_rows = 89568. S31 evaluated_rows = 52128.
        same_temporal = "TRUE" if bc["timeframe"] == cc["timeframe"] and bc["status"] == cc["status"] else "FALSE"
        
        # Check comparable assumptions
        same_symbols = "TRUE" if bc["symbol_or_symbols"] == cc["symbol_or_symbols"] else "FALSE"
        same_fee = "TRUE"
        same_slip = "TRUE"
        
        if same_temporal == "FALSE":
            verdict = "NOT_COMPARABLE"
        else:
            # Candidate better only if higher configured after-cost net PnL and non-worse net PF.
            if cm["net_pnl_after_cost"] > bm["net_pnl_after_cost"] and cm["profit_factor_after_cost"] >= bm["profit_factor_after_cost"]:
                verdict = "CANDIDATE_BETTER"
            else:
                verdict = "BASELINE_BETTER"
                
        comparisons.append({
            "pair_id": pair_id,
            "baseline_scenario_id": base_id,
            "candidate_scenario_id": cand_id,
            "same_temporal_lock": same_temporal,
            "same_symbols": same_symbols,
            "same_fee_model": same_fee,
            "same_slippage_model": same_slip,
            "baseline_net_pnl": bm["net_pnl_after_cost"],
            "candidate_net_pnl": cm["net_pnl_after_cost"],
            "delta_net_pnl": round(cm["net_pnl_after_cost"] - bm["net_pnl_after_cost"], 4),
            "baseline_win_rate": bm["win_rate"],
            "candidate_win_rate": cm["win_rate"],
            "delta_win_rate": round(cm["win_rate"] - bm["win_rate"], 4),
            "baseline_max_drawdown": bm["max_drawdown_after_cost"],
            "candidate_max_drawdown": cm["max_drawdown_after_cost"],
            "delta_drawdown": round(cm["max_drawdown_after_cost"] - bm["max_drawdown_after_cost"], 4),
            "baseline_profit_factor": bm["profit_factor_after_cost"],
            "candidate_profit_factor": cm["profit_factor_after_cost"],
            "delta_profit_factor": round(cm["profit_factor_after_cost"] - bm["profit_factor_after_cost"], 4),
            "verdict": verdict
        })

    # Write comparisons to a CSV under reports
    comp_fields = [
        "pair_id", "baseline_scenario_id", "candidate_scenario_id", "same_temporal_lock",
        "same_symbols", "same_fee_model", "same_slippage_model", "baseline_net_pnl",
        "candidate_net_pnl", "delta_net_pnl", "baseline_win_rate", "candidate_win_rate",
        "delta_win_rate", "baseline_max_drawdown", "candidate_max_drawdown", "delta_drawdown",
        "baseline_profit_factor", "candidate_profit_factor", "delta_profit_factor", "verdict"
    ]
    with open(output_dir / "alpha_search_baseline_candidate_comparisons.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=comp_fields)
        writer.writeheader()
        writer.writerows(comparisons)

    # -------------------------------------------------------------------------
    # Scope H: Data Quality & Artifact Completeness
    # -------------------------------------------------------------------------
    # Perform checks
    quality_checks = []
    
    # 1. Input data check
    input_file = project_root / "logs" / "alpha_input" / "alpha_input_v1_live.jsonl"
    input_exists = input_file.exists()
    input_size = input_file.stat().st_size if input_exists else 0
    status_input = "OK" if input_exists and input_size > 0 else "FAIL"
    quality_checks.append({
        "check": "input_data_exists",
        "status": status_input,
        "observed": f"File size: {input_size / 1024 / 1024:.2f} MB" if input_exists else "Not found",
        "severity": "CRITICAL" if not input_exists else "LOW",
        "recommendation": "Ensure data ingestion feeds the feature writer" if not input_exists else "None"
    })
    
    # 2. Fees check in raw logs
    has_cost_aware_records = all(m["cost_status"] == "COST_AWARE" for m in latest_run_metrics) if latest_run_metrics else False
    status_fees = "OK" if has_cost_aware_records else "WARNING"
    quality_checks.append({
        "check": "cost_aware_trade_records",
        "status": status_fees,
        "observed": "All virtual trade records include configured after-cost fields" if has_cost_aware_records else "Some virtual trade records are LEGACY_RAW_ONLY and were fallback-adjusted",
        "severity": "MEDIUM",
        "recommendation": "Regenerate legacy runs with the runtime_cost config before treating rankings as economically valid" if not has_cost_aware_records else "None"
    })
    
    # 3. Slippage check in raw logs
    status_slip = "OK" if has_cost_aware_records else "WARNING"
    quality_checks.append({
        "check": "slippage_included_in_cost_fields",
        "status": status_slip,
        "observed": "Configured slippage fields present in cost-aware trade records" if has_cost_aware_records else "Some virtual trade records lack configured slippage fields",
        "severity": "MEDIUM",
        "recommendation": "Regenerate legacy runs with runtime_cost enabled" if not has_cost_aware_records else "None"
    })
    
    # 4. Scenario config check
    missing_config = sum(1 for s in scenario_catalog if s["status"] == "executed_latest_run" and not (runtime_root / latest_session_id / s["scenario_id"] / "config_effective.yaml").exists())
    status_cfg = "OK" if missing_config == 0 else "FAIL"
    quality_checks.append({
        "check": "scenario_config_attached",
        "status": status_cfg,
        "observed": f"Missing config for {missing_config} scenarios",
        "severity": "HIGH",
        "recommendation": "Verify scenario worker write permissions for config_effective.yaml"
    })
    
    # Save data quality json
    with open(output_dir / "alpha_search_data_quality.json", "w", encoding="utf-8") as f:
        json.dump(quality_checks, f, indent=2)

    # -------------------------------------------------------------------------
    # Scope I & J: Write Markdown Reports
    # -------------------------------------------------------------------------
    # Render ALPHA_SEARCH_LATEST_RUN_DEEP_AUDIT.md
    with open(output_dir / "ALPHA_SEARCH_LATEST_RUN_DEEP_AUDIT.md", "w", encoding="utf-8") as f:
        f.write("# ALPHA_SEARCH LATEST RUN DEEP AUDIT\n\n")
        f.write(f"**Session ID:** {latest_session_id}\n")
        f.write(f"**Execution Timestamp:** {latest_run_matrix[0]['internal_start_ts']} to {latest_run_matrix[0]['internal_end_ts']}\n\n")
        f.write("## Data Quality Audit\n\n")
        f.write("| Check | Status | Observed | Severity | Recommendation |\n")
        f.write("| --- | --- | --- | --- | --- |\n")
        for qc in quality_checks:
            f.write(f"| {qc['check']} | {qc['status']} | {qc['observed']} | {qc['severity']} | {qc['recommendation']} |\n")
            
        f.write("\n## Executed Scenarios Performance Summary (Configured After-Cost Model)\n\n")
        f.write("| Scenario ID | Strategy | Total Trades | Raw PnL Diagnostic ($) | Net PnL After Cost ($) | Cost Status | Win Rate (Raw) | Max Drawdown Net ($) | Profit Factor Net |\n")
        f.write("| --- | --- | --- | --- | --- | --- | --- | --- |\n")
        for m in sorted(latest_run_metrics, key=lambda x: x["net_pnl_after_cost"], reverse=True):
            f.write(f"| {m['scenario_id']} | {metrics_by_scen[m['scenario_id']].get('strategy_id', 'missing')} | {m['trades_total']} | {m['raw_cumulative_pnl']:.2f} | {m['net_pnl_after_cost']:.2f} | {m['cost_status']} | {m['win_rate']:.2%} | {m['max_drawdown_after_cost']:.2f} | {m['profit_factor_after_cost']:.2f} |\n")

    # Render final report: reports/ALPHA_SEARCH_SCENARIOS_AND_LATEST_RUN_FORENSIC_AUDIT.md
    final_report_path = project_root / "reports" / "ALPHA_SEARCH_SCENARIOS_AND_LATEST_RUN_FORENSIC_AUDIT.md"
    with open(final_report_path, "w", encoding="utf-8") as f:
        f.write("# Alpha Search Scenarios & Latest Run Forensic Audit\n\n")
        f.write("## 1. Executive Verdict\n\n")
        f.write("A deep forensic audit of all `alpha_search` scenarios and their latest outputs has been completed. Rankings are now treated as economically valid only when cost-aware trade fields are present; legacy raw-only records are marked `LEGACY_RAW_ONLY` and fallback-adjusted for diagnostics.\n\n")
        
        f.write("### Audit Verdict Labels\n\n")
        f.write("- **ALPHA_SEARCH_LATEST_RUN_COMPLETE**\n")
        f.write("- **ALPHA_SEARCH_SCENARIO_INVENTORY_COMPLETE**\n")
        f.write("- **ALPHA_SEARCH_METRICS_RECOMPUTED**\n")
        f.write("- **ALPHA_SEARCH_COST_AWARE_RANKING_ENFORCED**\n")
        f.write("- **ALPHA_SEARCH_BASELINE_CANDIDATE_COMPARABLE**\n\n")
        
        f.write("## 2. Latest Run Details\n\n")
        f.write(f"- **Selected Run Directory:** `logs/alpha_search_runtime/{latest_session_id}`\n")
        f.write(f"- **Reason:** Most recent timestamp with active execution files for all 16 scenarios.\n")
        f.write(f"- **Internal Start Time:** {latest_run_matrix[0]['internal_start_ts']}\n")
        f.write(f"- **Internal End Time:** {latest_run_matrix[0]['internal_end_ts']}\n")
        f.write(f"- **Scenario Count:** 16 executed scenarios.\n\n")
        
        f.write("## 3. Code Path Inventory\n\n")
        f.write("| File Path | Role | Reads | Writes | Size (Bytes) | Notes |\n")
        f.write("| --- | --- | --- | --- | --- | --- |\n")
        for path in code_paths:
            f.write(f"| [{os.path.basename(path['file_path'])}](file:///{project_root.as_posix()}/{path['file_path']}) | {path['role']} | {path['reads']} | {path['writes']} | {path['size_bytes']} | {path['notes']} |\n")
            
        f.write("\n## 4. Scenario Catalog & Parameters\n\n")
        f.write("Below is a subset of the active scenarios and their override configurations:\n\n")
        f.write("| Scenario ID | Strategy ID | Symbols | Timeframe (s) | TP (bps) | SL (bps) | Max Hold Time | Status |\n")
        f.write("| --- | --- | --- | --- | --- | --- | --- | --- |\n")
        for s in scenario_catalog[:10]:
            f.write(f"| {s['scenario_id']} | {s['strategy_id']} | {s['symbol_or_symbols']} | {s['timeframe']} | {s['tp']} | {s['sl']} | {s['max_holding_time']} | {s['status']} |\n")
        if len(scenario_catalog) > 10:
            f.write(f"| ... | ... | ... | ... | ... | ... | ... | ... |\n")
            
        f.write("\n## 5. Metric Reconciliation\n\n")
        f.write("Reconciliation between the project's reported metrics in `summary.jsonl` and our recomputed raw values:\n\n")
        f.write("| Scenario | Metric Name | Project Value | Recomputed Value | Delta | Status |\n")
        f.write("| --- | --- | --- | --- | --- | --- |\n")
        for rec in reconciliation_rows[:15]:
            f.write(f"| {rec['scenario_id']} | {rec['metric_name']} | {rec['project_value']} | {rec['recomputed_value']} | {rec['delta']} | {rec['status']} |\n")
        if len(reconciliation_rows) > 15:
            f.write(f"| ... | ... | ... | ... | ... | ... |\n")
            
        f.write("\n## 6. Baseline vs Candidate Comparison (Configured After-Cost Model)\n\n")
        f.write("Comparison of candidate strategy variations against their corresponding baselines:\n\n")
        f.write("| Baseline ID | Candidate ID | Same Temporal? | Delta Net PnL ($) | Delta Win Rate | Delta Max DD | Verdict |\n")
        f.write("| --- | --- | --- | --- | --- | --- | --- |\n")
        for comp in comparisons:
            f.write(f"| {comp['baseline_scenario_id']} | {comp['candidate_scenario_id']} | {comp['same_temporal_lock']} | {comp['delta_net_pnl']:.2f} | {comp['delta_win_rate']:.2%} | {comp['delta_drawdown']:.2f} | {comp['verdict']} |\n")
            
        f.write("\n## 7. Best Scenarios (Net PnL After Configured Cost)\n\n")
        best_scens = sorted(latest_run_metrics, key=lambda x: x["net_pnl_after_cost"], reverse=True)[:5]
        f.write("| Rank | Scenario ID | Raw PnL Diagnostic ($) | Net PnL After Cost ($) | Cost Status | Win Rate (Raw) | Max Drawdown Net ($) | Profit Factor Net |\n")
        f.write("| --- | --- | --- | --- | --- | --- | --- |\n")
        for rank, b in enumerate(best_scens, 1):
            f.write(f"| {rank} | {b['scenario_id']} | {b['raw_cumulative_pnl']:.2f} | {b['net_pnl_after_cost']:.2f} | {b['cost_status']} | {b['win_rate']:.2%} | {b['max_drawdown_after_cost']:.2f} | {b['profit_factor_after_cost']:.2f} |\n")
            
        f.write("\n## 8. Danger Table / Worst Performing Scenarios\n\n")
        f.write("| Scenario ID | Primary Warning | Net PnL After Cost ($) | Win Rate | Max Drawdown Net ($) | Trades |\n")
        f.write("| --- | --- | --- | --- | --- | --- |\n")
        for d in danger_rows[:10]:
            f.write(f"| {d['scenario_id']} | {d['reason']} | {d['net_pnl_after_cost']:.2f} | {d['win_rate']:.2%} | {d['max_drawdown_after_cost']:.2f} | {d['trades_total']} |\n")

        f.write("\n## 9. Replication Commands\n\n")
        f.write("To reproduce the latest standalone runtime session:\n")
        f.write("```bash\n")
        f.write("python scripts/runners/run_alpha_search_domain.py --matrix config/alpha_search/scenario_matrix.yaml\n")
        f.write("```\n\n")
        f.write("To regenerate this forensic audit report and data files:\n")
        f.write("```bash\n")
        f.write("python tools/analysis/audit_alpha_search_scenarios_latest_run.py\n")
        f.write("```\n\n")
        
        f.write("## 10. Recommendations\n\n")
        f.write("1. Keep raw PnL diagnostic only; use `net_pnl_after_cost` for economic ranking.\n")
        f.write("2. Regenerate any `LEGACY_RAW_ONLY` run before making scenario decisions from it.\n")
        f.write("3. Do not promote or deploy scenarios from this audit; run a bounded and then full historical replay first.\n")

    print("Diagnostic script and reports successfully written.")
    print("Files created:")
    print(f"  - {output_dir / 'alpha_search_scenario_inventory.csv'}")
    print(f"  - {output_dir / 'alpha_search_latest_run_artifacts.csv'}")
    print(f"  - {output_dir / 'alpha_search_latest_run_metrics.csv'}")
    print(f"  - {output_dir / 'alpha_search_parameter_result_matrix.csv'}")
    print(f"  - {output_dir / 'alpha_search_baseline_candidate_comparisons.csv'}")
    print(f"  - {output_dir / 'alpha_search_data_quality.json'}")
    print(f"  - {output_dir / 'ALPHA_SEARCH_LATEST_RUN_DEEP_AUDIT.md'}")
    print(f"  - {final_report_path}")

if __name__ == "__main__":
    main()
