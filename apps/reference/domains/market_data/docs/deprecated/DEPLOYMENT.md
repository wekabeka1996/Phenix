# Market Data Deployment

## Overview
The `market_data` domain is designed as a **Satellite Microservice**. In a full deployment, it runs alongside the core strategy containers, providing them with a cleaned stream of market events.

**Deployment Model:** Containerized (Docker/K8s)
**Availability:** 99.9% (Requires Restart Policy)
**Scaling:** Horizontal (By Symbol Sharding)

---

## 1. Container Configuration

### Dockerfile
```dockerfile
FROM python:3.11-slim

# Install system deps (curl for healthcheck)
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY apps/ ./apps/
COPY vfoundation/ ./vfoundation/

# HEALTHCHECK is critical for "Blackhole" detection
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "apps.reference.domains.market_data.main"]
```

### Docker Compose
```yaml
market-data:
  restart: always  # Essential for OOM recovery
  deploy:
    resources:
      limits:
        memory: 512M # Limit blast radius of memory leak
```

---

## 2. Environment Configuration

| Variable | Default | Description |
| :--- | :--- | :--- |
| `MARKET_DATA_MODE` | `proxy` | **CRITICAL**: Selects Proxy Architecture. |
| `TRADING_MODE` | `live` | Selects between `api.binance.com` and `testnet.binance.vision`. |
| `BINANCE_API_KEY` | - | Required for REST Fallback (though WS is public). |
| `POLL_INTERVAL_SEC` | `1.0` | Batch frequency for Worker -> Main IPC. |

---

## 3. Operational Risks (Forensic)

### ⚠️ Warning: The "Zombie" Mode
If environment variable `MARKET_DATA_MODE` is unset or invalid, the system might default to `legacy`.
**Check:** Run `ps aux` in the container.
-   **GOOD:** 2+ Python processes (Main + Worker).
-   **BAD:** 1 Python process (Main only).

### ⚠️ Warning: The OOM Timebomb
Due to the `seen_trade_ids` leak, this container **will** consume increasing RAM.
**Standard Procedure:** Scheduled restart every 24h OR strict memory limit + `restart: always` policy.

---

## 4. Kubernetes Deployment

### Liveness Probe (Blackhole Protection)
The Liveness probe is your primary defense against "Silent Stops".
```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 15
  failureThreshold: 3
```
If the internal loop hangs or the "Blackhole" state is detected (freshness > threshold), the `/health` endpoint should return 500, triggering a Pod Restart.
