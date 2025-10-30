#!/usr/bin/env python3
import os, re, json, sys, time
from urllib.request import urlopen, Request
from urllib.error import URLError
import yaml


def _get_cfg():
    # читання з YAML конфігу або env з дефолтами
    config_path = os.environ.get("OPS_CONFIG_PATH", "configs/master_config_v1.yaml")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        ops_config = config.get("ops", {})
        url = ops_config.get("metrics_url", "http://127.0.0.1:8000/metrics")
        out_dir = ops_config.get("reports_dir", "reports")
    except (FileNotFoundError, yaml.YAMLError):
        # fallback до env
        url = os.environ.get("OPS_METRICS_URL", "http://127.0.0.1:8000/metrics")
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
    # decisions
    # приклад символу — якщо експортуєте лейбли по символу (необов'язково)
    # rl_eth   = _mget(txt, "decision_rate_limited_total", 'symbol="ETHUSDT"')

    summary = {
        "ts_ms": int(time.time() * 1000),
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
