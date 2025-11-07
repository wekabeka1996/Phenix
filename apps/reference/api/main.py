# PATH: apps/reference/api/main.py
from __future__ import annotations
import os
from fastapi import FastAPI
import asyncio
import json
from datetime import datetime
from typing import Dict, Any

# FSMP-REFACTOR-T03-B: Separate debug and production APIs
# Debug endpoints only available when TRADING_ENV != 'production'
if os.environ.get("TRADING_ENV", "development").lower() != "production":
    # Development/staging: expose full debug API
    from vfoundation.obs.debug_api import app

    print(
        "INFO: Debug API endpoints are ENABLED (TRADING_ENV={})".format(
            os.environ.get("TRADING_ENV", "development")
        )
    )
else:
    # Production: clean API without debug endpoints
    app = FastAPI(
        title="Aurora Core API",
        description="Production API for Aurora Core FSM Federation",
        version="1.0.0",
    )

    # WebSocket for live dashboard updates
    from fastapi import WebSocket, WebSocketDisconnect

    connected_clients = set()

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint for live dashboard updates."""
        await websocket.accept()
        connected_clients.add(websocket)

        try:
            # Send initial connection message
            await websocket.send_json({
                "type": "connected",
                "timestamp": datetime.now().isoformat(),
                "message": "Connected to Aurora Core dashboard"
            })

            # Keep connection alive and send periodic updates
            while True:
                try:
                    # Get current metrics
                    from prometheus_client import generate_latest
                    from apps.reference.api.metrics import update_hybrid_coherence_metrics
                    update_hybrid_coherence_metrics()

                    txt = generate_latest().decode("utf-8", "replace")

                    # Parse key metrics
                    equity = _mget(txt, "exposure_equity_usd")
                    pos_usd = _mget(txt, "exposure_positions_usd")
                    pend_usd = _mget(txt, "exposure_pending_usd")
                    limit_usd = _mget(txt, "exposure_limit_usd")
                    placed = _mget(txt, "orders_placed_total")
                    filled = _mget(txt, "orders_filled_total")
                    exp_rej = _mget(
                        txt, "fsm_guard_rejects_total", 'guard="exposure"')

                    # Get alert stats
                    alert_stats = {"active_alerts": 0, "last_alerts": []}
                    try:
                        # Try to get alert manager stats if available
                        from apps.reference.main import alert_manager
                        if 'alert_manager' in globals() or hasattr(alert_manager, 'get_alert_stats'):
                            alert_stats = alert_manager.get_alert_stats()
                    except:
                        pass

                    # Send dashboard data
                    dashboard_data = {
                        "type": "metrics_update",
                        "timestamp": datetime.now().isoformat(),
                        "exposure": {
                            "equity_usd": equity,
                            "positions_usd": pos_usd,
                            "pending_usd": pend_usd,
                            "limit_usd": limit_usd,
                            "utilization_pct": ((pos_usd + pend_usd) / limit_usd * 100.0) if limit_usd > 0 else 0.0,
                        },
                        "orders": {
                            "placed_total": placed,
                            "filled_total": filled,
                            "success_rate": (filled / placed * 100.0) if placed > 0 else 0.0
                        },
                        "alerts": {
                            "active_count": alert_stats.get("active_alerts", 0),
                            "recent_count": len(alert_stats.get("recent_alert_keys", []))
                        },
                        "guards": {
                            "exposure_rejects": exp_rej
                        }
                    }

                    await websocket.send_json(dashboard_data)

                    # Wait 5 seconds before next update
                    await asyncio.sleep(5)

                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "timestamp": datetime.now().isoformat(),
                        "message": f"Error getting metrics: {str(e)}"
                    })
                    await asyncio.sleep(5)

        except WebSocketDisconnect:
            connected_clients.discard(websocket)
        except Exception as e:
            print(f"WebSocket error: {e}")
            connected_clients.discard(websocket)

    @app.get("/health")
    async def health_check():
        """Basic health check endpoint."""
        return {"status": "healthy", "service": "aurora-core"}

    @app.get("/metrics")
    def metrics():
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        from apps.reference.api.metrics import update_hybrid_coherence_metrics
        update_hybrid_coherence_metrics()
        data = generate_latest()  # default REGISTRY
        from fastapi import Response

        return Response(content=data, media_type=CONTENT_TYPE_LATEST)

    def _mget(
        txt: str, name: str, label_filter: str | None = None, default: float = 0.0
    ) -> float:
        import re

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

    @app.get("/statdump")
    def statdump():
        # читаємо те саме, що віддає /metrics, з внутрішнього реєстру
        from apps.reference.telemetry.metrics import generate_latest
        from apps.reference.bootstrap.preflight import get_hybrid_coherence_state

        txt = generate_latest().decode("utf-8", "replace")

        equity = _mget(txt, "exposure_equity_usd")
        pos_usd = _mget(txt, "exposure_positions_usd")
        pend_usd = _mget(txt, "exposure_pending_usd")
        limit_usd = _mget(txt, "exposure_limit_usd")
        exp_rej = _mget(txt, "fsm_guard_rejects_total", 'guard="exposure"')
        ttl_exp = _mget(txt, "pending_exposure_expired_total")
        placed = _mget(txt, "orders_placed_total")
        filled = _mget(txt, "orders_filled_total")

        # Hybrid coherence state
        hybrid_state = get_hybrid_coherence_state()
        hybrid_ok = hybrid_state['last_result']['ok']
        hybrid_reasons = hybrid_state['last_result']['reasons']
        risk_portfolio_source = hybrid_state['risk_portfolio_source']
        execution_mode = hybrid_state['execution_mode']

        # Зчитуємо частину ops-конфіга (через простий env або ваш ConfigLoader)
        panic = os.environ.get("OPS_PANIC", "false").lower() == "true"

        data = {
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
            },
            "orders": {"placed_total": placed, "filled_total": filled},
            "ops": {"panic_killswitch": panic},
            "hybrid": {
                "ok": hybrid_ok,
                "reasons": hybrid_reasons,
                "risk_portfolio_source": risk_portfolio_source,
                "execution_mode": execution_mode,
            },
        }
        from fastapi.responses import JSONResponse

        return JSONResponse(data)

    print("INFO: Debug API endpoints are DISABLED (production mode)")
