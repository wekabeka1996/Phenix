"""
Forensic Analysis v2 — 20-Hour Oracle Performance Audit
========================================================
Reads neocortex_metrics.csv and data/neocortex.log to produce a
comprehensive performance report including confusion matrix,
per-class precision/recall, entropy trajectory, and distribution shift.
"""

import csv
import re
import sys
import os
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

# ── Paths ──────────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent.parent
CSV_PATH = BASE / "logs" / "neocortex_metrics.csv"
LOG_PATH = BASE / "data" / "neocortex.log"
REPORT_PATH = BASE / "docs" / "20H_ORACLE_REPORT.md"

CLASSES = ["TREND_UP", "TREND_DOWN",
           "MEAN_REVERSION", "HIGH_VOLATILITY", "EXHAUSTION"]
CLASS_SHORT = {"TREND_UP": "T_UP", "TREND_DOWN": "T_DN",
               "MEAN_REVERSION": "MR", "HIGH_VOLATILITY": "H_VOL", "EXHAUSTION": "EXHST"}


def parse_csv_settlements():
    """Parse CSV for oracle settlement rows (where predicted_regime and realized_regime exist)."""
    settlements = []
    if not CSV_PATH.exists():
        print(f"ERROR: {CSV_PATH} not found")
        return settlements

    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pred = row.get("predicted_regime", "").strip()
            real = row.get("realized_regime", "").strip()
            if pred and real:
                ts = row.get("timestamp", "")
                reward = row.get("oracle_reward", "")
                correct = row.get("oracle_correct", "")
                settlements.append({
                    "timestamp": float(ts) if ts else 0,
                    "predicted": int(pred),
                    "realized": int(real),
                    "reward": float(reward) if reward else 0.0,
                    "correct": correct == "1",
                })
    return settlements


def parse_csv_ppo_updates():
    """Parse CSV for PPO training metric rows."""
    updates = []
    if not CSV_PATH.exists():
        return updates

    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pi = row.get("ppo_loss_pi", "").strip()
            if pi:
                ts = row.get("timestamp", "")
                updates.append({
                    "timestamp": float(ts) if ts else 0,
                    "policy_loss": float(pi) if pi else 0.0,
                    "value_loss": float(row.get("ppo_loss_v", "0") or "0"),
                    "entropy": float(row.get("ppo_entropy", "0") or "0"),
                })
    return updates


def parse_log_ppo_updates():
    """Parse neocortex.log for PPO update lines (richer data including grad_norm)."""
    updates = []
    if not LOG_PATH.exists():
        print(f"WARNING: {LOG_PATH} not found, skipping log analysis")
        return updates

    pattern = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*PPO update complete: \{(.+)\}"
    )
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            m = pattern.search(line)
            if m:
                ts_str = m.group(1)
                data_str = m.group(2)
                rec = {"timestamp_str": ts_str}
                for key in ["loss", "policy_loss", "value_loss", "entropy", "approx_kl", "grad_norm"]:
                    km = re.search(rf"'{key}':\s*([-\d.eE+]+)", data_str)
                    if km:
                        rec[key] = float(km.group(1))
                updates.append(rec)
    return updates


def parse_log_settlements():
    """Parse neocortex.log for Oracle settlement lines."""
    settlements = []
    if not LOG_PATH.exists():
        return settlements

    pattern = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Oracle settlement #(\d+): "
        r"predicted=(PREDICT_\w+) realized=(PREDICT_\w+) reward=([-\d.]+) correct=(\w+)"
    )
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            m = pattern.search(line)
            if m:
                pred_name = m.group(3).replace("PREDICT_", "")
                real_name = m.group(4).replace("PREDICT_", "")
                settlements.append({
                    "timestamp_str": m.group(1),
                    "settlement_id": int(m.group(2)),
                    "predicted": pred_name,
                    "realized": real_name,
                    "reward": float(m.group(5)),
                    "correct": m.group(6) == "True",
                })
    return settlements


def parse_log_errors():
    """Count gradient failures and other anomalies in the log."""
    counts = Counter()
    if not LOG_PATH.exists():
        return counts

    with open(LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if "Gradient validation FAILED" in line:
                counts["gradient_failed"] += 1
            if "Advantage std is degenerate" in line:
                counts["degenerate_advantage"] += 1
            if "NaN/Inf loss" in line:
                counts["nan_loss"] += 1
            if "NaN/Inf in gradients" in line:
                counts["nan_gradients"] += 1
            if "model_corrupted" in line or "CORRUPTED" in line:
                counts["model_corrupted"] += 1
            if "ERROR" in line:
                counts["errors"] += 1
    return counts


def idx_to_name(idx):
    """Convert 0-4 index to class name."""
    return CLASSES[idx] if 0 <= idx < 5 else f"UNK_{idx}"


def confusion_matrix(settlements, use_names=False):
    """Build 5x5 confusion matrix. Returns {(pred, real): count}."""
    cm = Counter()
    for s in settlements:
        if use_names:
            p, r = s["predicted"], s["realized"]
        else:
            p, r = idx_to_name(s["predicted"]), idx_to_name(s["realized"])
        cm[(p, r)] += 1
    return cm


def format_confusion_matrix(cm, total):
    """Format confusion matrix as markdown table."""
    lines = []
    header = "| Pred \\ Real | " + \
        " | ".join(CLASS_SHORT[c] for c in CLASSES) + " | Total | Pred% |"
    sep = "|" + "---|" * (len(CLASSES) + 3)
    lines.append(header)
    lines.append(sep)

    for pred in CLASSES:
        row_total = sum(cm.get((pred, real), 0) for real in CLASSES)
        pct = f"{100*row_total/total:.1f}" if total else "0"
        cells = []
        for real in CLASSES:
            count = cm.get((pred, real), 0)
            if pred == real:
                cells.append(f"**{count}**")
            else:
                cells.append(str(count))
        lines.append(f"| **{CLASS_SHORT[pred]}** | " +
                     " | ".join(cells) + f" | {row_total} | {pct}% |")

    # Realized totals row
    real_totals = []
    for real in CLASSES:
        rt = sum(cm.get((pred, real), 0) for pred in CLASSES)
        real_totals.append(str(rt))
    lines.append(f"| **Real Total** | " +
                 " | ".join(real_totals) + f" | {total} | |")

    # Realized % row
    real_pcts = []
    for real in CLASSES:
        rt = sum(cm.get((pred, real), 0) for pred in CLASSES)
        real_pcts.append(f"{100*rt/total:.1f}%" if total else "0%")
    lines.append(f"| **Real%** | " + " | ".join(real_pcts) + " | | |")

    return "\n".join(lines)


def precision_recall(cm, total):
    """Calculate per-class precision and recall."""
    results = {}
    for cls in CLASSES:
        tp = cm.get((cls, cls), 0)
        pred_total = sum(cm.get((cls, r), 0) for r in CLASSES)
        real_total = sum(cm.get((p, cls), 0) for p in CLASSES)
        precision = tp / pred_total if pred_total > 0 else 0.0
        recall = tp / real_total if real_total > 0 else 0.0
        f1 = 2 * precision * recall / \
            (precision + recall) if (precision + recall) > 0 else 0.0
        results[cls] = {
            "tp": tp, "pred_total": pred_total, "real_total": real_total,
            "precision": precision, "recall": recall, "f1": f1,
        }
    return results


def distribution_shift(settlements, use_names=False):
    """Compare prediction distribution: first 20% vs last 20%."""
    n = len(settlements)
    first_n = max(1, n // 5)
    last_n = max(1, n // 5)
    first = settlements[:first_n]
    last = settlements[-last_n:]

    def dist(subset):
        counts = Counter()
        for s in subset:
            if use_names:
                counts[s["predicted"]] += 1
            else:
                counts[idx_to_name(s["predicted"])] += 1
        total = len(subset)
        return {c: counts.get(c, 0) / total * 100 for c in CLASSES}

    def acc(subset):
        correct = sum(1 for s in subset if s["correct"])
        return correct / len(subset) * 100 if subset else 0

    return dist(first), dist(last), acc(first), acc(last)


def entropy_trajectory(ppo_updates, n_buckets=20):
    """Bucket PPO updates into n_buckets and compute mean entropy per bucket."""
    if not ppo_updates:
        return []
    bucket_size = max(1, len(ppo_updates) // n_buckets)
    buckets = []
    for i in range(0, len(ppo_updates), bucket_size):
        chunk = ppo_updates[i:i+bucket_size]
        if not chunk:
            continue
        ts_label = chunk[0].get("timestamp_str", "")
        mean_ent = sum(u.get("entropy", 0) for u in chunk) / len(chunk)
        mean_pi = sum(u.get("policy_loss", 0) for u in chunk) / len(chunk)
        mean_gn = sum(u.get("grad_norm", 0) for u in chunk) / len(chunk)
        mean_kl = sum(u.get("approx_kl", 0) for u in chunk) / len(chunk)
        max_gn = max(u.get("grad_norm", 0) for u in chunk)
        min_ent = min(u.get("entropy", 0) for u in chunk)
        max_ent = max(u.get("entropy", 0) for u in chunk)
        buckets.append({
            "ts": ts_label, "n": len(chunk),
            "mean_entropy": mean_ent, "min_entropy": min_ent, "max_entropy": max_ent,
            "mean_policy_loss": mean_pi,
            "mean_grad_norm": mean_gn, "max_grad_norm": max_gn,
            "mean_kl": mean_kl,
        })
    return buckets


def generate_report():
    """Main analysis function. Generates markdown report."""
    print("=" * 60)
    print("FORENSIC ANALYSIS v2 — 20-Hour Oracle Audit")
    print("=" * 60)

    # ── 1. Parse data ──────────────────────────────────────────────────
    print("\n[1/6] Parsing CSV settlements...")
    csv_settlements = parse_csv_settlements()
    print(f"  CSV settlements: {len(csv_settlements)}")

    print("[2/6] Parsing log settlements...")
    log_settlements = parse_log_settlements()
    print(f"  Log settlements: {len(log_settlements)}")

    print("[3/6] Parsing log PPO updates...")
    log_ppo = parse_log_ppo_updates()
    print(f"  Log PPO updates: {len(log_ppo)}")

    print("[4/6] Parsing CSV PPO updates...")
    csv_ppo = parse_csv_ppo_updates()
    print(f"  CSV PPO updates: {len(csv_ppo)}")

    print("[5/6] Scanning for errors...")
    errors = parse_log_errors()
    print(f"  Errors found: {dict(errors)}")

    print("[6/6] Counting checkpoints...")
    cp_dir = BASE / "data" / "checkpoints"
    cp_files = sorted(cp_dir.glob("checkpoint_*.pt")
                      ) if cp_dir.exists() else []
    cp_numbered = [f for f in cp_files if f.name != "checkpoint_latest.pt"]
    print(
        f"  Checkpoint files: {len(cp_files)} ({len(cp_numbered)} numbered + latest)")

    # ── 2. Decide which data source to use ─────────────────────────────
    # Prefer log settlements (richer, named classes) over CSV (index-based)
    if log_settlements:
        settlements = log_settlements
        use_names = True
        source = "neocortex.log"
        print(
            f"\nUsing LOG settlements ({len(settlements)}) as primary source")
    elif csv_settlements:
        settlements = csv_settlements
        use_names = False
        source = "neocortex_metrics.csv"
        print(
            f"\nUsing CSV settlements ({len(settlements)}) as primary source")
    else:
        print("ERROR: No settlement data found!")
        return

    ppo_updates = log_ppo if log_ppo else csv_ppo

    # ── 3. Compute metrics ─────────────────────────────────────────────
    total = len(settlements)
    correct = sum(1 for s in settlements if s["correct"])
    accuracy = correct / total * 100 if total else 0

    cm = confusion_matrix(settlements, use_names=use_names)
    pr = precision_recall(cm, total)
    cm_text = format_confusion_matrix(cm, total)

    dist_first, dist_last, acc_first, acc_last = distribution_shift(
        settlements, use_names=use_names)
    ent_trajectory = entropy_trajectory(ppo_updates)

    # Time range
    if log_settlements:
        ts_first = log_settlements[0]["timestamp_str"]
        ts_last = log_settlements[-1]["timestamp_str"]
        sett_first = log_settlements[0]["settlement_id"]
        sett_last = log_settlements[-1]["settlement_id"]
    else:
        ts_first = str(csv_settlements[0]["timestamp"])
        ts_last = str(csv_settlements[-1]["timestamp"])
        sett_first = "N/A"
        sett_last = "N/A"

    # Average reward
    avg_reward = sum(s["reward"] for s in settlements) / total if total else 0

    # Reward by predicted class
    reward_by_pred = defaultdict(list)
    for s in settlements:
        key = s["predicted"] if use_names else idx_to_name(s["predicted"])
        reward_by_pred[key].append(s["reward"])
    avg_reward_by_pred = {k: sum(v)/len(v) for k, v in reward_by_pred.items()}

    # ── 4. Console summary ─────────────────────────────────────────────
    print(f"\n{'-'*60}")
    print(f"OVERALL ACCURACY: {accuracy:.1f}% ({correct}/{total})")
    print(f"TIME RANGE: {ts_first} -> {ts_last}")
    print(f"SETTLEMENT RANGE: #{sett_first} -> #{sett_last}")
    print(f"AVG REWARD: {avg_reward:.4f}")
    print(f"{'-'*60}")

    print("\nPER-CLASS METRICS:")
    print(f"{'Class':<18} {'Prec':>6} {'Recall':>6} {'F1':>6} {'Predicted':>9} {'Realized':>9}")
    for cls in CLASSES:
        p = pr[cls]
        print(f"{CLASS_SHORT[cls]:<18} {p['precision']:.3f}  {p['recall']:.3f}  {p['f1']:.3f}  "
              f"{p['pred_total']:>8}  {p['real_total']:>8}")

    print("\nDISTRIBUTION SHIFT (first 20% -> last 20%):")
    for cls in CLASSES:
        sc = CLASS_SHORT[cls]
        print(f"  {sc:<8} {dist_first[cls]:5.1f}% -> {dist_last[cls]:5.1f}%")
    print(f"  Accuracy: {acc_first:.1f}% -> {acc_last:.1f}%")

    if ent_trajectory:
        print("\nENTROPY TRAJECTORY (bucketed):")
        for b in ent_trajectory:
            print(f"  {b['ts']}  entropy={b['mean_entropy']:.4f} [{b['min_entropy']:.2e}..{b['max_entropy']:.4f}]  "
                  f"pi_loss={b['mean_policy_loss']:.6f}  grad={b['mean_grad_norm']:.2f} (max {b['max_grad_norm']:.1f})  "
                  f"kl={b['mean_kl']:.6f}")

    # ── 5. Generate markdown report ────────────────────────────────────
    report_lines = []
    report_lines.append("# 20-Hour Oracle Performance Report")
    report_lines.append(
        f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"**Data source:** `{source}`")
    report_lines.append(f"**Time range:** {ts_first} → {ts_last}")
    report_lines.append(
        f"**Settlements:** #{sett_first} → #{sett_last} ({total:,} total)")
    report_lines.append(f"**PPO updates:** {len(ppo_updates):,}")
    report_lines.append(
        f"**Checkpoints:** {len(cp_numbered)} numbered + latest")

    # Executive summary
    report_lines.append("\n## Executive Summary\n")

    # Determine health status
    if ent_trajectory:
        last_bucket = ent_trajectory[-1]
        last_entropy = last_bucket["mean_entropy"]
        last_pi = last_bucket["mean_policy_loss"]
    else:
        last_entropy = 0
        last_pi = 0

    if last_entropy < 0.01:
        entropy_status = "DEAD (mode collapse)"
    elif last_entropy < 0.3:
        entropy_status = "LOW (partial collapse)"
    elif last_entropy < 0.8:
        entropy_status = "MODERATE (learning)"
    elif last_entropy < 1.3:
        entropy_status = "HEALTHY (exploring)"
    else:
        entropy_status = "HIGH (random/over-exploring)"

    is_learning = abs(last_pi) > 0.001
    accuracy_vs_random = accuracy - 20.0  # 5-class random = 20%
    accuracy_vs_majority = accuracy - max(
        sum(1 for s in settlements if (
            s["realized"] if use_names else idx_to_name(s["realized"])) == cls)
        for cls in CLASSES) / total * 100 if total else 0

    report_lines.append(f"| Metric | Value | Status |")
    report_lines.append(f"|--------|-------|--------|")
    report_lines.append(
        f"| Overall Accuracy | **{accuracy:.1f}%** | {'Above' if accuracy_vs_random > 0 else 'Below'} random baseline (20%) by {accuracy_vs_random:+.1f}pp |")
    report_lines.append(
        f"| Avg Reward | **{avg_reward:.4f}** | {'Positive' if avg_reward > 0 else 'Negative'} |")
    report_lines.append(
        f"| Final Entropy | **{last_entropy:.4f}** | {entropy_status} |")
    report_lines.append(
        f"| Policy Learning | **{last_pi:.6f}** | {'Active' if is_learning else 'Stalled (≈0)'} |")
    report_lines.append(
        f"| Gradient Failures | **{errors.get('gradient_failed', 0)}** | {'Clean' if errors.get('gradient_failed', 0) == 0 else 'Problematic'} |")
    report_lines.append(
        f"| Checkpoint Rotation | **{len(cp_numbered)} files** | {'Healthy' if len(cp_numbered) <= 6 else 'Broken'} |")

    # Confusion Matrix
    report_lines.append("\n## Confusion Matrix\n")
    report_lines.append(
        "Rows = Predicted, Columns = Realized. **Bold** = correct predictions.\n")
    report_lines.append(cm_text)

    # Precision / Recall
    report_lines.append("\n## Per-Class Performance\n")
    report_lines.append(
        "| Class | Precision | Recall | F1 | Predicted | Realized | Avg Reward |")
    report_lines.append(
        "|-------|-----------|--------|----|-----------|----------|------------|")
    for cls in CLASSES:
        p = pr[cls]
        sc = CLASS_SHORT[cls]
        ar = avg_reward_by_pred.get(cls, 0)
        report_lines.append(
            f"| {sc} | {p['precision']:.3f} | {p['recall']:.3f} | {p['f1']:.3f} | "
            f"{p['pred_total']:,} ({100*p['pred_total']/total:.1f}%) | "
            f"{p['real_total']:,} ({100*p['real_total']/total:.1f}%) | {ar:+.3f} |"
        )

    # Distribution shift
    report_lines.append("\n## Distribution Shift (First 20% → Last 20%)\n")
    report_lines.append("| Class | First 20% | Last 20% | Δ |")
    report_lines.append("|-------|-----------|----------|---|")
    for cls in CLASSES:
        sc = CLASS_SHORT[cls]
        d = dist_last[cls] - dist_first[cls]
        report_lines.append(
            f"| {sc} | {dist_first[cls]:.1f}% | {dist_last[cls]:.1f}% | {d:+.1f}pp |")
    report_lines.append(
        f"| **Accuracy** | **{acc_first:.1f}%** | **{acc_last:.1f}%** | **{acc_last-acc_first:+.1f}pp** |")

    # Entropy trajectory
    report_lines.append("\n## PPO Health — Entropy & Loss Trajectory\n")
    report_lines.append(
        "| Time | Entropy (mean) | Entropy (range) | Policy Loss | Grad Norm (mean/max) | KL |")
    report_lines.append(
        "|------|----------------|-----------------|-------------|---------------------|-----|")
    for b in ent_trajectory:
        report_lines.append(
            f"| {b['ts']} | {b['mean_entropy']:.4f} | [{b['min_entropy']:.2e}, {b['max_entropy']:.4f}] | "
            f"{b['mean_policy_loss']:.6f} | {b['mean_grad_norm']:.2f} / {b['max_grad_norm']:.1f} | "
            f"{b['mean_kl']:.6f} |"
        )

    # Red flags
    report_lines.append("\n## Red Flags & Anomalies\n")
    red_flags = []

    # Check for mode collapse
    for cls in CLASSES:
        pred_pct = pr[cls]["pred_total"] / total * 100 if total else 0
        if pred_pct > 60:
            red_flags.append(
                f"**Mode collapse**: {CLASS_SHORT[cls]} predicted {pred_pct:.1f}% of the time")
        if pred_pct < 2 and pr[cls]["real_total"] / total * 100 > 5:
            red_flags.append(
                f"**Blind spot**: {CLASS_SHORT[cls]} predicted only {pred_pct:.1f}% but realized {pr[cls]['real_total']/total*100:.1f}%")

    if last_entropy < 0.01:
        red_flags.append(
            f"**Entropy dead**: {last_entropy:.2e} — policy has collapsed to deterministic")
    if not is_learning:
        red_flags.append(
            f"**Policy stalled**: policy_loss ≈ {last_pi:.2e}, no active learning")
    if errors.get("gradient_failed", 0) > 10:
        red_flags.append(
            f"**Gradient instability**: {errors['gradient_failed']} validation failures")
    if errors.get("nan_loss", 0) > 0:
        red_flags.append(f"**NaN losses**: {errors['nan_loss']} events")
    if accuracy < 25:
        red_flags.append(
            f"**Below-random accuracy**: {accuracy:.1f}% (random=20%, majority baseline higher)")

    # Check for entropy oscillation
    if ent_trajectory and len(ent_trajectory) > 3:
        dead_buckets = sum(
            1 for b in ent_trajectory if b["min_entropy"] < 1e-6)
        if dead_buckets > len(ent_trajectory) * 0.3:
            red_flags.append(
                f"**Entropy oscillation**: {dead_buckets}/{len(ent_trajectory)} buckets contain near-zero entropy updates")

    if not red_flags:
        report_lines.append("No critical red flags detected.")
    else:
        for flag in red_flags:
            report_lines.append(f"- {flag}")

    # Error log
    report_lines.append("\n## Error Log Summary\n")
    if errors:
        for k, v in sorted(errors.items()):
            report_lines.append(f"- `{k}`: {v}")
    else:
        report_lines.append("No errors detected in logs.")

    # ── 6. Write report ────────────────────────────────────────────────
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines) + "\n")

    print(f"\n{'='*60}")
    print(f"Report written to: {REPORT_PATH}")
    print(f"{'='*60}")


if __name__ == "__main__":
    generate_report()
