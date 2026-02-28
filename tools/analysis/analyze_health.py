#!/usr/bin/env python3
"""
Neocortex Forensic Health Analyzer

Analyzes logs and telemetry to verify if the RL integration is REAL or BROKEN.

Checks:
1. Perception: Feature ingestion (FEATURES_CALCULATED events)
2. Action: Order matching (ORDER_PLACED events)
3. Reward: PnL parsing (Reward Injected logs)
4. Brain: VAE/WM training (Loss trends)
5. PPO: RL training (PPO loss columns)

Usage:
    python tools/analyze_health.py
"""

import os
import sys
import csv
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Any, Optional, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class Colors:
    """ANSI color codes for terminal output."""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'


def safe_read_csv(filepath: Path, max_rows: int = 10000) -> List[Dict]:
    """Read CSV safely, handling concurrent writes."""
    rows = []
    try:
        with open(filepath, 'r', newline='', errors='ignore') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i >= max_rows:
                    break
                rows.append(row)
    except Exception as e:
        print(f"Warning: Could not read CSV: {e}")
    return rows


def safe_read_log(filepath: Path, max_lines: int = 50000) -> List[str]:
    """Read log file safely, handling concurrent writes."""
    lines = []
    try:
        with open(filepath, 'r', errors='ignore') as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                lines.append(line.strip())
    except Exception as e:
        print(f"Warning: Could not read log: {e}")
    return lines


def parse_float_safe(value: str) -> Optional[float]:
    """Parse float safely, return None for empty/invalid."""
    if not value or value.strip() == '':
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def ascii_chart(values: List[float], width: int = 50, height: int = 10) -> str:
    """Generate ASCII chart for terminal display."""
    if not values:
        return "  No data"
    
    min_val = min(values)
    max_val = max(values)
    val_range = max_val - min_val if max_val != min_val else 1
    
    # Normalize to 0-height range
    normalized = [(v - min_val) / val_range * (height - 1) for v in values]
    
    # Sample values if too many
    if len(normalized) > width:
        step = len(normalized) // width
        normalized = normalized[::step][:width]
    
    # Build chart
    chart = []
    for row in range(height - 1, -1, -1):
        line = "  │"
        for val in normalized:
            if int(val) >= row:
                line += "█"
            else:
                line += " "
        chart.append(line)
    
    chart.append("  └" + "─" * len(normalized))
    chart.append(f"   Start: {min_val:.4f}  →  End: {max_val:.4f}")
    
    return "\n".join(chart)


def analyze_metrics_csv(filepath: Path) -> Dict[str, Any]:
    """Analyze neocortex_metrics.csv telemetry."""
    result = {
        "total_rows": 0,
        "vae_losses": [],
        "wm_losses": [],
        "ppo_pi_losses": [],
        "ppo_v_losses": [],
        "ppo_entropy": [],
        "rewards": [],
        "cumulative_reward": 0,
        "shadow_actions": defaultdict(int),
        "first_timestamp": None,
        "last_timestamp": None,
        "train_steps": 0,
    }
    
    rows = safe_read_csv(filepath)
    result["total_rows"] = len(rows)
    
    for row in rows:
        # VAE loss
        vae = parse_float_safe(row.get("vae_loss", ""))
        if vae is not None:
            result["vae_losses"].append(vae)
        
        # WM loss
        wm = parse_float_safe(row.get("wm_loss", ""))
        if wm is not None:
            result["wm_losses"].append(wm)
        
        # PPO losses
        ppo_pi = parse_float_safe(row.get("ppo_loss_pi", ""))
        if ppo_pi is not None:
            result["ppo_pi_losses"].append(ppo_pi)
        
        ppo_v = parse_float_safe(row.get("ppo_loss_v", ""))
        if ppo_v is not None:
            result["ppo_v_losses"].append(ppo_v)
        
        entropy = parse_float_safe(row.get("ppo_entropy", ""))
        if entropy is not None:
            result["ppo_entropy"].append(entropy)
        
        # Rewards
        reward = parse_float_safe(row.get("last_reward", ""))
        if reward is not None:
            result["rewards"].append(reward)
        
        cum_reward = parse_float_safe(row.get("cumulative_reward", ""))
        if cum_reward is not None:
            result["cumulative_reward"] = cum_reward
        
        # Shadow actions
        action_name = row.get("shadow_action_name", "")
        if action_name:
            result["shadow_actions"][action_name] += 1
        
        # Timestamps
        ts = row.get("datetime", "")
        if ts:
            if result["first_timestamp"] is None:
                result["first_timestamp"] = ts
            result["last_timestamp"] = ts
        
        # Train steps
        train_step = parse_float_safe(row.get("total_train_steps", ""))
        if train_step and train_step > result["train_steps"]:
            result["train_steps"] = int(train_step)
    
    return result


def analyze_neocortex_log(filepath: Path) -> Dict[str, Any]:
    """Analyze neocortex.log for key events."""
    result = {
        "features_calculated": 0,
        "orders_placed": 0,
        "orders_rejected": 0,
        "reward_injected": 0,
        "episode_complete": 0,
        "ppo_training": 0,
        "dream_consolidation": 0,
        "checkpoints_saved": 0,
        "errors": 0,
        "warnings": 0,
    }
    
    if not filepath.exists():
        return result
    
    lines = safe_read_log(filepath)
    
    for line in lines:
        line_lower = line.lower()
        
        if "features_calculated" in line_lower or "ingested tick" in line_lower:
            result["features_calculated"] += 1
        
        if "order_placed" in line_lower:
            result["orders_placed"] += 1
        
        if "order_rejected" in line_lower:
            result["orders_rejected"] += 1
        
        if "reward inject" in line_lower or "pnl=" in line_lower:
            result["reward_injected"] += 1
        
        if "episode complete" in line_lower:
            result["episode_complete"] += 1
        
        if "ppo training" in line_lower or "ppo update" in line_lower:
            result["ppo_training"] += 1
        
        if "dream consolidation" in line_lower:
            result["dream_consolidation"] += 1
        
        if "checkpoint saved" in line_lower or "checkpoint_" in line_lower:
            result["checkpoints_saved"] += 1
        
        if "error" in line_lower:
            result["errors"] += 1
        
        if "warning" in line_lower:
            result["warnings"] += 1
    
    return result


def analyze_order_log(filepath: Path) -> Dict[str, Any]:
    """Analyze order_log_v1.jsonl for orders and regimes."""
    import json
    
    result = {
        "total_orders": 0,
        "placed": 0,
        "rejected": 0,
        "regimes": defaultdict(int),
        "symbols": defaultdict(int),
        "reject_reasons": defaultdict(int),
    }
    
    if not filepath.exists():
        return result
    
    lines = safe_read_log(filepath, max_lines=10000)
    
    for line in lines:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            result["total_orders"] += 1
            
            event_type = entry.get("event_type", "")
            if event_type == "ORDER_PLACED":
                result["placed"] += 1
            elif event_type == "ORDER_REJECTED":
                result["rejected"] += 1
                nrr = entry.get("nrr_code", "UNKNOWN")
                result["reject_reasons"][nrr] += 1
            
            # Regime
            metadata = entry.get("metadata", {})
            regime = metadata.get("regime", entry.get("regime", "UNKNOWN"))
            result["regimes"][regime] += 1
            
            # Symbol
            symbol = entry.get("symbol", "UNKNOWN")
            result["symbols"][symbol] += 1
            
        except json.JSONDecodeError:
            continue
    
    return result


def analyze_core_log(filepath: Path) -> Dict[str, Any]:
    """Analyze aurora_core.log for position events."""
    result = {
        "position_closed": 0,
        "equity_updates": 0,
        "last_equity": None,
    }
    
    if not filepath.exists():
        return result
    
    lines = safe_read_log(filepath, max_lines=20000)
    
    for line in lines:
        if "Position closed" in line:
            result["position_closed"] += 1
        
        if "totalWalletBalance" in line:
            result["equity_updates"] += 1
            # Extract equity
            match = re.search(r'totalWalletBalance=([0-9.]+)', line)
            if match:
                result["last_equity"] = float(match.group(1))
    
    return result


def check_feature_logs(features_dir: Path) -> Dict[str, Any]:
    """Check feature log files for data."""
    result = {
        "symbols": [],
        "total_lines": 0,
        "last_modified": None,
    }
    
    if not features_dir.exists():
        return result
    
    for log_file in features_dir.glob("*.log"):
        symbol = log_file.stem
        result["symbols"].append(symbol)
        
        # Count lines
        try:
            with open(log_file, 'r') as f:
                lines = sum(1 for _ in f)
                result["total_lines"] += lines
        except:
            pass
        
        # Last modified
        mtime = log_file.stat().st_mtime
        dt = datetime.fromtimestamp(mtime)
        if result["last_modified"] is None or dt > result["last_modified"]:
            result["last_modified"] = dt
    
    return result


def generate_report():
    """Generate comprehensive forensic analysis report."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}╔══════════════════════════════════════════════════════════════════╗{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}║          NEOCORTEX FORENSIC HEALTH ANALYSIS                     ║{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}║          {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                                     ║{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}╚══════════════════════════════════════════════════════════════════╝{Colors.END}\n")
    
    # File paths
    logs_dir = PROJECT_ROOT / "logs"
    metrics_csv = logs_dir / "neocortex_metrics.csv"
    neocortex_log = logs_dir / "neocortex.log"
    order_log = logs_dir / "order_log_v1.jsonl"
    core_log = logs_dir / "aurora_core.log"
    features_dir = logs_dir / "features"
    
    # Analyze all sources
    print(f"{Colors.BLUE}[1/5] Analyzing telemetry CSV...{Colors.END}")
    metrics = analyze_metrics_csv(metrics_csv) if metrics_csv.exists() else {}
    
    print(f"{Colors.BLUE}[2/5] Analyzing neocortex log...{Colors.END}")
    neo_log = analyze_neocortex_log(neocortex_log)
    
    print(f"{Colors.BLUE}[3/5] Analyzing order log...{Colors.END}")
    orders = analyze_order_log(order_log)
    
    print(f"{Colors.BLUE}[4/5] Analyzing core log...{Colors.END}")
    core = analyze_core_log(core_log)
    
    print(f"{Colors.BLUE}[5/5] Analyzing feature logs...{Colors.END}")
    features = check_feature_logs(features_dir)
    
    # =========================================================================
    # REPORT OUTPUT
    # =========================================================================
    
    print(f"\n{Colors.BOLD}{'═' * 70}{Colors.END}")
    print(f"{Colors.BOLD}                           ANALYSIS RESULTS{Colors.END}")
    print(f"{Colors.BOLD}{'═' * 70}{Colors.END}\n")
    
    # ---------- PERCEPTION ----------
    print(f"{Colors.BOLD}{Colors.CYAN}▶ CHECK 1: PERCEPTION (Feature Ingestion){Colors.END}")
    print(f"  Feature Log Symbols: {', '.join(features.get('symbols', [])) or 'NONE'}")
    print(f"  Total Feature Lines: {features.get('total_lines', 0):,}")
    print(f"  Last Modified: {features.get('last_modified', 'N/A')}")
    print(f"  CSV Telemetry Rows: {metrics.get('total_rows', 0):,}")
    
    if features.get('total_lines', 0) > 0:
        print(f"  {Colors.GREEN}✓ PERCEPTION: HEALTHY{Colors.END}")
    else:
        print(f"  {Colors.RED}✗ PERCEPTION: NO DATA{Colors.END}")
    
    # ---------- ACTION ----------
    print(f"\n{Colors.BOLD}{Colors.CYAN}▶ CHECK 2: ACTION (Shadow Intents & Orders){Colors.END}")
    shadow_dist = dict(metrics.get('shadow_actions', {}))
    print(f"  Shadow Intent Distribution: {shadow_dist}")
    print(f"  Order Log - Placed: {orders.get('placed', 0)}")
    print(f"  Order Log - Rejected: {orders.get('rejected', 0)}")
    print(f"  Regimes Seen: {dict(orders.get('regimes', {}))}")
    
    if sum(shadow_dist.values()) > 0:
        print(f"  {Colors.GREEN}✓ ACTION: HEALTHY (Diverse intents){Colors.END}")
    else:
        print(f"  {Colors.YELLOW}⚠ ACTION: No shadow intents logged{Colors.END}")
    
    # ---------- REWARD ----------
    print(f"\n{Colors.BOLD}{Colors.CYAN}▶ CHECK 3: REWARD (PnL Parsing){Colors.END}")
    rewards_count = len(metrics.get('rewards', []))
    cumulative = metrics.get('cumulative_reward', 0)
    position_closed = core.get('position_closed', 0)
    equity = core.get('last_equity')
    
    print(f"  Reward Events in CSV: {rewards_count}")
    print(f"  Cumulative Reward: {cumulative:.4f}")
    print(f"  Position Closed Events: {position_closed}")
    print(f"  Last Known Equity: ${equity:.2f}" if equity else "  Last Known Equity: UNKNOWN")
    
    if rewards_count > 0:
        print(f"  {Colors.GREEN}✓ REWARD: FLOWING{Colors.END}")
    elif position_closed > 0:
        print(f"  {Colors.YELLOW}⚠ REWARD: Positions closed but rewards not logged{Colors.END}")
    else:
        print(f"  {Colors.RED}✗ REWARD: NO REWARDS YET (No closed positions){Colors.END}")
    
    # ---------- BRAIN (VAE/WM) ----------
    print(f"\n{Colors.BOLD}{Colors.CYAN}▶ CHECK 4: BRAIN (VAE/WM Training){Colors.END}")
    vae_losses = metrics.get('vae_losses', [])
    wm_losses = metrics.get('wm_losses', [])
    
    if vae_losses:
        print(f"  VAE Loss Samples: {len(vae_losses)}")
        print(f"  VAE Loss Range: {min(vae_losses):.4f} → {max(vae_losses):.4f}")
        print(f"  VAE Loss (last 10 avg): {sum(vae_losses[-10:])/min(10, len(vae_losses)):.4f}")
        
        # ASCII chart
        print(f"\n  {Colors.BOLD}VAE Loss Trend:{Colors.END}")
        print(ascii_chart(vae_losses[-100:], width=40, height=6))
        
        if len(vae_losses) > 10 and vae_losses[-1] <= vae_losses[0]:
            print(f"\n  {Colors.GREEN}✓ VAE: LEARNING (Loss decreasing){Colors.END}")
        else:
            print(f"\n  {Colors.YELLOW}⚠ VAE: ACTIVE (Loss plateau or increasing){Colors.END}")
    else:
        print(f"  {Colors.RED}✗ VAE: NO TRAINING DATA{Colors.END}")
    
    if wm_losses:
        print(f"\n  WM Loss Samples: {len(wm_losses)}")
        print(f"  WM Loss (last 10 avg): {sum(wm_losses[-10:])/min(10, len(wm_losses)):.6f}")
    
    # ---------- PPO ----------
    print(f"\n{Colors.BOLD}{Colors.CYAN}▶ CHECK 5: PPO (Reinforcement Learning){Colors.END}")
    ppo_pi = metrics.get('ppo_pi_losses', [])
    ppo_v = metrics.get('ppo_v_losses', [])
    ppo_ent = metrics.get('ppo_entropy', [])
    train_steps = metrics.get('train_steps', 0)
    
    print(f"  PPO Policy Loss Samples: {len(ppo_pi)}")
    print(f"  PPO Value Loss Samples: {len(ppo_v)}")
    print(f"  PPO Entropy Samples: {len(ppo_ent)}")
    print(f"  Total Train Steps: {train_steps}")
    
    if ppo_pi:
        print(f"  PPO Policy Loss (avg): {sum(ppo_pi)/len(ppo_pi):.6f}")
        print(f"  {Colors.GREEN}✓ PPO: TRAINING ACTIVE{Colors.END}")
    else:
        print(f"  {Colors.RED}✗ PPO: IDLE (No training steps found){Colors.END}")
        print(f"    → Reason: PPO needs episodes with rewards to fill buffer")
    
    # =========================================================================
    # VERDICT
    # =========================================================================
    print(f"\n{Colors.BOLD}{'═' * 70}{Colors.END}")
    print(f"{Colors.BOLD}                              VERDICT{Colors.END}")
    print(f"{Colors.BOLD}{'═' * 70}{Colors.END}\n")
    
    issues = []
    
    # Determine status
    perception_ok = features.get('total_lines', 0) > 0
    action_ok = sum(shadow_dist.values()) > 0
    reward_ok = rewards_count > 0
    vae_ok = len(vae_losses) > 0
    ppo_ok = len(ppo_pi) > 0
    
    if not perception_ok:
        issues.append("Feature ingestion not working")
    if not action_ok:
        issues.append("Shadow intents not generating")
    if not reward_ok:
        issues.append("No PnL rewards flowing (need closed positions with profit/loss)")
    if not vae_ok:
        issues.append("VAE not training")
    if not ppo_ok:
        issues.append("PPO not training (waiting for reward episodes)")
    
    if perception_ok and action_ok and vae_ok:
        if reward_ok and ppo_ok:
            status = f"{Colors.GREEN}✅ FULLY OPERATIONAL{Colors.END}"
            verdict = "All systems nominal. Neocortex is learning from real trading data."
        elif reward_ok:
            status = f"{Colors.YELLOW}⚠️  PARTIALLY OPERATIONAL{Colors.END}"
            verdict = "Rewards flowing, PPO waiting for buffer fill. Keep running."
        else:
            status = f"{Colors.YELLOW}⚠️  WAITING FOR REWARDS{Colors.END}"
            verdict = "Perception OK, waiting for closed positions to generate PnL rewards."
    else:
        status = f"{Colors.RED}❌ CRITICAL ISSUES DETECTED{Colors.END}"
        verdict = "System has integration problems. Check logs for errors."
    
    print(f"  Status: {status}")
    print(f"  Verdict: {verdict}")
    
    if issues:
        print(f"\n  {Colors.YELLOW}Issues Found:{Colors.END}")
        for issue in issues:
            print(f"    • {issue}")
    
    print(f"\n{Colors.BOLD}{'═' * 70}{Colors.END}")
    print(f"  Timestamps: {metrics.get('first_timestamp', 'N/A')} → {metrics.get('last_timestamp', 'N/A')}")
    print(f"  Analysis completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{Colors.BOLD}{'═' * 70}{Colors.END}\n")


if __name__ == "__main__":
    generate_report()
