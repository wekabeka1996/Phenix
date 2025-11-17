#!/usr/bin/env python3
import os
import re
import json
import sys
import time
from urllib.request import urlopen, Request
from urllib.error import URLError
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, timedelta

from apps.reference.config_loader import reload_config


def _get_cfg():
    # читання з централізованого ConfigLoader або env fallback
    try:
        cfg = reload_config()
        ops_config = getattr(cfg, "ops", None)
        if ops_config is None and isinstance(cfg, dict):
            ops_config = cfg.get("ops", {})

        if ops_config is None:
            ops_config = {}

        if hasattr(ops_config, "metrics_url"):
            url = ops_config.metrics_url
        elif isinstance(ops_config, dict):
            url = ops_config.get(
                "metrics_url", "http://127.0.0.1:8000/metrics")
        else:
            url = "http://127.0.0.1:8000/metrics"

        if hasattr(ops_config, "reports_dir"):
            out_dir = ops_config.reports_dir
        elif isinstance(ops_config, dict):
            out_dir = ops_config.get("reports_dir", "reports")
        else:
            out_dir = "reports"
    except Exception:
        url = os.environ.get(
            "OPS_METRICS_URL", "http://127.0.0.1:8000/metrics")
        out_dir = os.environ.get("OPS_REPORTS_DIR", "reports")
    return url, out_dir


def _scrape_metrics_text(url: str) -> str:
    try:
        req = Request(url, headers={"User-Agent": "metrics-summary/1.0"})
        with urlopen(req, timeout=3) as r:
            return r.read().decode("utf-8", "replace")
    except URLError as e:
        return ""


def _mget(
    txt: str, name: str, label_filter: str | None = None, default: float = 0.0
) -> float:
    """
    Витягає значення метрики з Prometheus-тексту.
    Напр., name='exposure_equity_usd'
          name='order_state_total' + label_filter='status="FILLED"'
    """
    if not txt:
        return default
    if label_filter:
        pat = rf"^{re.escape(name)}\{{[^}}]*{label_filter}[^}}]*\}}\s+([0-9eE\.\+\-]+)$"
    else:
        pat = rf"^{re.escape(name)}\s+([0-9eE\.\+\-]+)$"
    for line in txt.splitlines():
        m = re.match(pat, line)
        if m:
            try:
                return float(m.group(1))
            except Exception:
                return default
    return default


def main():
    url, out_dir = _get_cfg()
    txt = _scrape_metrics_text(url)
    # exposure
    equity = _mget(txt, "exposure_equity_usd")
    pos_usd = _mget(txt, "exposure_positions_usd")
    pend_usd = _mget(txt, "exposure_pending_usd")
    limit_usd = _mget(txt, "exposure_limit_usd")
    # guards
    exp_rej = _mget(txt, "fsm_guard_rejects_total", 'guard="exposure"')
    ttl_exp = _mget(txt, "pending_exposure_expired_total")
    daily_blk = _mget(
        txt, "fsm_guard_rejects_total", 'guard="daily"'
    )  # якщо додасте лічильник далі
    # orders
    placed = _mget(txt, "orders_placed_total")
    filled = _mget(txt, "orders_filled_total")
    # New correlation metrics
    open_success_total = _mget(txt, "open_success_total")
    cmd_open_total = _mget(txt, "cmd_open_total")
    time_to_open_ms_sum = _mget(txt, "time_to_open_ms_sum")
    time_to_open_count = _mget(txt, "time_to_open_count")
    defer_rate = _mget(txt, "defer_rate")
    block_rate = _mget(txt, "block_rate")
    retry_count = _mget(txt, "retry_count")
    qos_cooldown_hits = _mget(txt, "qos_cooldown_hits")
    # Calculate derived metrics
    open_success_rate = open_success_total / \
        cmd_open_total if cmd_open_total > 0 else 0.0
    mean_time_to_open_ms = time_to_open_ms_sum / \
        time_to_open_count if time_to_open_count > 0 else 0.0

    # Mock breakdown_by_symbol - in real implementation, collect from metrics with labels
    # Get symbols from config - centralized configuration
    from apps.reference.config_symbols import get_trading_symbols
    symbols = get_trading_symbols()

    breakdown_by_symbol = {}
    for symbol in symbols:
        breakdown_by_symbol[symbol] = {
            "open_success_rate": 0.95,
            "cmd_open_count": 80,
            "dec_open_count": 76
        }

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "period_hours": 24,
        "metrics": {
            "open_success_rate": round(open_success_rate, 4),
            "mean_time_to_open_ms": round(mean_time_to_open_ms, 2),
            "defer_rate": round(defer_rate, 4),
            "block_rate": round(block_rate, 4),
            "retry_count": int(retry_count),
            "qos_cooldown_hits": int(qos_cooldown_hits)
        },
        "breakdown_by_symbol": breakdown_by_symbol,
        "alerts": [],  # TODO: implement alerts logic
        "exposure": {
            "equity_usd": equity,
            "positions_usd": pos_usd,
            "pending_usd": pend_usd,
            "limit_usd": limit_usd,
            "utilization_pct": ((pos_usd + pend_usd) / limit_usd * 100.0)
            if limit_usd > 0
            else 0.0,
        },
        "guards": {
            "exposure_rejects_total": exp_rej,
            "pending_expired_total": ttl_exp,
            "daily_rejects_total": daily_blk,
        },
        "orders": {"placed_total": placed, "filled_total": filled},
    }
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "summary_gate_status.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(out_path)


if __name__ == "__main__":
    sys.exit(main())


class MetricsSummary:
    """
    Generates L3-METRICS-SUMMARY report for gate status monitoring.
    """

    def __init__(self, reports_dir: str = "reports"):
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(exist_ok=True)

    def collect_metrics(self) -> Dict[str, Any]:
        """
        Collect metrics from various sources.
        In real implementation, query Prometheus or parse logs/WAL.
        """
        # Get symbols from config - centralized configuration
        from apps.reference.config_symbols import get_trading_symbols
        symbols = get_trading_symbols()

        # Build breakdown_by_symbol dynamically
        breakdown_by_symbol = {}
        for symbol in symbols:
            breakdown_by_symbol[symbol] = {
                "open_success_rate": 0.95,
                "cmd_open_count": 80,
                "dec_open_count": 76
            }

        # Mock data - replace with actual collection logic
        return {
            "open_success_total": 150,
            "cmd_open_total": 160,
            "time_to_open_ms_sum": 25000,  # sum of all times
            "time_to_open_count": 150,
            "defer_rate": 0.025,  # 2.5%
            "block_rate": 0.0125,  # 1.25%
            "retry_count": 5,
            "qos_cooldown_hits": 2,
            "breakdown_by_symbol": breakdown_by_symbol
        }

    def calculate_derived_metrics(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate derived metrics like rates and averages."""
        cmd_open_total = metrics.get("cmd_open_total", 0)
        open_success_total = metrics.get("open_success_total", 0)
        time_to_open_ms_sum = metrics.get("time_to_open_ms_sum", 0)
        time_to_open_count = metrics.get("time_to_open_count", 0)

        open_success_rate = (
            open_success_total / cmd_open_total if cmd_open_total > 0 else 0.0
        )
        mean_time_to_open_ms = (
            time_to_open_ms_sum / time_to_open_count if time_to_open_count > 0 else 0.0
        )

        return {
            "open_success_rate": round(open_success_rate, 4),
            "mean_time_to_open_ms": round(mean_time_to_open_ms, 2),
            "defer_rate": metrics.get("defer_rate", 0.0),
            "block_rate": metrics.get("block_rate", 0.0),
            "retry_count": metrics.get("retry_count", 0),
            "qos_cooldown_hits": metrics.get("qos_cooldown_hits", 0),
            "breakdown_by_symbol": metrics.get("breakdown_by_symbol", {})
        }

    def check_alerts(self, metrics: Dict[str, Any]) -> List[str]:
        """Generate alerts based on metric thresholds."""
        alerts = []

        if metrics["open_success_rate"] < 0.9:
            alerts.append("Open success rate below 90% threshold")

        if metrics["mean_time_to_open_ms"] > 100:
            alerts.append("Mean time to open exceeds 100ms threshold")

        if metrics["defer_rate"] > 0.05:
            alerts.append("Defer rate above 5% threshold")

        if metrics["block_rate"] > 0.02:
            alerts.append("Block rate above 2% threshold")

        for symbol, data in metrics["breakdown_by_symbol"].items():
            if data["open_success_rate"] < 0.9:
                alerts.append(f"{symbol} open success rate below 90%")

        return alerts

    def generate_report(self) -> Dict[str, Any]:
        """Generate the complete summary report."""
        metrics = self.collect_metrics()
        derived = self.calculate_derived_metrics(metrics)
        alerts = self.check_alerts(derived)

        report = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "period_hours": 24,
            "metrics": derived,
            "alerts": alerts
        }

        return report

    def save_report(self, report: Dict[str, Any], filename: str = "summary_gate_status.json"):
        """Save report to JSON file."""
        filepath = self.reports_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"Report saved to {filepath}")

    def run(self):
        """Main execution method."""
        report = self.generate_report()
        self.save_report(report)
        return report
