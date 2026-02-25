# Market Data Troubleshooting

## Overview

This guide covers common issues, diagnostic procedures, and resolution steps for the `market_data` domain. It blends standard operational troubleshooting with deep forensic diagnosis methods.

**Quick Diagnosis:** Check `/health` endpoint and `docker stats`.
**Most Common Issues:** API Connectivity, Data Freshness (Stale), Memory Leaks (Forensic).

---

## Health Check & Monitoring

### Primary Health Check
```bash
curl http://localhost:8000/health
# Check "data_freshness" field. If > 5s, data is STALE.
```

### Forensic Metrics (Prometheus/Logs)
-   `market_data_uptime_seconds`: Restart loops indicate crashes.
-   `market_data_memory_usage_bytes`: Linear growth indicates a leak.
-   `events_emitted_total`: Flatline indicates a "Blackhole" connection.

---

## Forensic Deep Dive Scenarios

### Issue 1: The "Silent Stop" (Blackhole Connection)
**Symptoms:**
-   Service is "Healthy" (process running).
-   Logs stop showing "Tick:" messages.
-   No error logs (Clean logs).

**Diagnose:**
1.  Check `proxy.py` logs. Is it complaining about the worker?
2.  Run `tcpdump` or check network traffic. If zero visible incoming packets despite "Connected" state -> **Blackhole**.

**Fix:** Restart the container (`docker restart market-data`). Permanent fix requires code change (Read Timeout).

### Issue 2: OOM Crash (Memory Leak)
**Symptoms:**
-   Container restarts periodically (e.g., every 24h).
-   `docker stats` shows RAM climbing steadily (100MB -> 200MB -> 500MB...) regardless of market activity.

**Cause:** The `seen_trade_ids` set in `WebSocketAggregator` never shrinks.
**Fix:** Temporary: Set Docker memory limit to force restart. Permanent: Code fix (LRU Cache).

### Issue 3: Missing Candles (Data Gaps)
**Symptoms:**
-   Strategies complain about "skipped bars".
-   `gap_bars_skipped` > 0 in `EVT:BAR_CLOSED`.

**Cause:**
1.  **Network Drop**: Genuine internet failure.
2.  **OOO Processing**: High jitter caused ticks to arrive out of order, and `BarAggregator` dropped them.

**Diagnose:** Search logs for "discarding out-of-order tick". If frequent explanation is Network Jitter.

---

## Standard Common Issues

### API Connectivity (40%)
**Symptom:** `ConnectionRefused` or `TimeoutError`.
**Fix:**
-   Verify `BINANCE_API_KEY`.
-   Check DNS/Firewall.
-   System clock sync (`ntpdate`). Binance rejects requests with skewed clocks.

### Rate Limits (429)
**Symptom:** `HTTP 429` errors.
**Fix:**
-   Increase `poll_interval_sec` in config.
-   Check if other services share the same IP/Key.

### "Zombie" Legacy Mode
**Symptom:** High API latency, UI freezes.
**Diagnose:** Check logs for "MarketDataConnector initialized" (Legacy) vs "Proxy initialized" (Modern).
**Fix:** Ensure `market_data.mode: proxy` is set in `system.yaml`.

---

## Emergency Procedures

### Service Restart
```bash
# Graceful
docker-compose restart market-data

# Force Kill (clears memory leak immediately)
docker-compose rm -f -s market-data && docker-compose up -d market-data
```

### Data Recovery
The system is designed to be "Memoryless" on restart. It will backfill the last few minutes of data if `historical_backfill` is enabled (currently Experimental). Generally, expect a "Cold Start" gap.
