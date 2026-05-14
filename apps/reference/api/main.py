# PATH: apps/reference/api/main.py
from __future__ import annotations
from functools import lru_cache
import logging
import os
from fastapi import FastAPI
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from apps.reference.domains.shadow_telemetry.trading_read_models import (
    TradingReadModelService,
    TradingReadModelUnavailableError,
)


LOG = logging.getLogger(__name__)


def _metric_get(
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


def _build_statdump_payload() -> Dict[str, Any]:
    from apps.reference.telemetry.metrics import generate_latest
    from apps.reference.bootstrap.preflight import get_hybrid_coherence_state

    txt = generate_latest().decode("utf-8", "replace")

    equity = _metric_get(txt, "exposure_equity_usd")
    pos_usd = _metric_get(txt, "exposure_positions_usd")
    pend_usd = _metric_get(txt, "exposure_pending_usd")
    limit_usd = _metric_get(txt, "exposure_limit_usd")
    exp_rej = _metric_get(txt, "fsm_guard_rejects_total", 'guard="exposure"')
    ttl_exp = _metric_get(txt, "pending_exposure_expired_total")
    placed = _metric_get(txt, "orders_placed_total")
    filled = _metric_get(txt, "orders_filled_total")

    hybrid_state = get_hybrid_coherence_state()
    hybrid_ok = hybrid_state["last_result"]["ok"]
    hybrid_reasons = hybrid_state["last_result"]["reasons"]
    risk_portfolio_source = hybrid_state["risk_portfolio_source"]
    execution_mode = hybrid_state["execution_mode"]

    panic = os.environ.get("OPS_PANIC", "false").lower() == "true"

    data: Dict[str, Any] = {
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

    try:
        from apps.reference.main import execution_position  # type: ignore

        if execution_position:
            data["execution_position"] = execution_position.get_metrics()
            try:
                og = getattr(execution_position, "order_guardian", None)
                if og and hasattr(og, "_impl"):
                    data["guardian"] = {
                        "unified": True,
                        "emit_tidy_event": True,
                    }
                else:
                    data["guardian"] = {"note": "guardian metrics not available"}
            except Exception:
                data["guardian"] = {"note": "guardian metrics error"}
    except Exception:
        pass

    return data


class _ShadowTelemetryHttpSnapshotStore:
    source_name = "shadow_telemetry_api"

    def __init__(self, *, base_url: str, timeout_sec: float = 1.0) -> None:
        self.base_url = str(base_url).rstrip("/")
        self.timeout_sec = float(timeout_sec)

    def latest(self, symbol: Optional[str], tf_sec: Optional[int]) -> Optional[Dict[str, Any]]:
        payload = self._request_json(
            "/snapshots/latest", symbol=symbol, tf_sec=tf_sec)
        return payload if isinstance(payload, dict) else None

    def tail(self, symbol: Optional[str], limit: int) -> list[Dict[str, Any]]:
        payload = self._request_json(
            "/snapshots/tail", symbol=symbol, limit=limit)
        if not isinstance(payload, dict):
            return []
        items = payload.get("items")
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]

    def _request_json(self, path: str, **query: Any) -> Optional[Any]:
        params = {key: value for key,
                  value in query.items() if value is not None}
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        request = Request(url, headers={"accept": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout_sec) as response:
                status = int(getattr(response, "status", 200))
                if status != 200:
                    return None
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code != 404:
                LOG.debug("Shadow telemetry request failed for %s: %s", url, exc)
            return None
        except (URLError, OSError, TimeoutError, ValueError) as exc:
            LOG.debug("Shadow telemetry request failed for %s: %s", url, exc)
            return None
        return payload


@lru_cache(maxsize=1)
def _shadow_telemetry_snapshot_store() -> object | None:
    project_root = Path(__file__).resolve().parents[3]
    try:
        from apps.reference.config_loader import ConfigLoader

        config = ConfigLoader(config_dir=project_root /
                              "config" / "aurora").load_config()
        shadow_api = config.domains.shadow_telemetry.api
    except Exception:
        LOG.debug("Failed to resolve shadow telemetry API config", exc_info=True)
        return None

    if not bool(shadow_api.enabled):
        return None

    scheme = "https" if bool(shadow_api.tls) else "http"
    base_url = f"{scheme}://{shadow_api.host}:{shadow_api.port}"
    return _ShadowTelemetryHttpSnapshotStore(base_url=base_url)


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
                    from apps.reference.telemetry.metrics import update_hybrid_coherence_metrics
                    from apps.reference.bootstrap.preflight import get_hybrid_coherence_state
                    try:
                        state = get_hybrid_coherence_state()
                        update_hybrid_coherence_metrics(state)
                    except Exception as e:
                        # Fail-open for observability
                        import logging
                        logging.getLogger(__name__).warning(
                            f"Failed to update hybrid coherence metrics: {e}")

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
        from apps.reference.telemetry.metrics import update_hybrid_coherence_metrics
        from apps.reference.bootstrap.preflight import get_hybrid_coherence_state
        try:
            state = get_hybrid_coherence_state()
            update_hybrid_coherence_metrics(state)
        except Exception as e:
            # Fail-open for observability: log but don't crash
            import logging
            logging.getLogger(__name__).warning(
                f"Failed to update hybrid coherence metrics: {e}")
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

        # Merge ExecPosFSM and Guardian metrics (JSON)
        try:
            from apps.reference.main import execution_position  # type: ignore
            if execution_position:
                data["execution_position"] = execution_position.get_metrics()
                # Guardian metrics (best-effort)
                try:
                    og = getattr(execution_position, 'order_guardian', None)
                    if og and hasattr(og, '_impl'):
                        # If services guardian has internal metrics, expose minimal introspection
                        data["guardian"] = {
                            "unified": True,
                            "emit_tidy_event": True,
                        }
                    else:
                        data["guardian"] = {
                            "note": "guardian metrics not available"}
                except Exception:
                    data["guardian"] = {"note": "guardian metrics error"}
        except Exception:
            # Keep /statdump working if execution_position not initialized
            pass
        from fastapi.responses import JSONResponse

        return JSONResponse(data)

    print("INFO: Debug API endpoints are DISABLED (production mode)")


def _trading_read_models() -> TradingReadModelService:
    project_root = Path(__file__).resolve().parents[3]
    execution_position = None
    try:
        from apps.reference.main import execution_position as runtime_execution_position  # type: ignore
        execution_position = runtime_execution_position
    except Exception:
        execution_position = None
    return TradingReadModelService(
        project_root=project_root,
        snapshot_store=_shadow_telemetry_snapshot_store(),
        execution_position=execution_position,
    )


def _register_statdump_route() -> None:
    existing_paths = {getattr(route, "path", None)
                      for route in getattr(app, "routes", [])}
    if "/statdump" in existing_paths:
        return

    @app.get("/statdump")
    def statdump():
        from fastapi.responses import JSONResponse

        return JSONResponse(_build_statdump_payload())


def _register_trading_read_model_routes() -> None:
    existing_paths = {getattr(route, "path", None)
                      for route in getattr(app, "routes", [])}
    if "/api/trading/positions/active" in existing_paths:
        return

    @app.get("/api/trading/context/latest")
    def trading_context_latest(symbol: str, tf_sec: int = 300):
        try:
            return _trading_read_models().get_context_latest(symbol=symbol, tf_sec=tf_sec)
        except TradingReadModelUnavailableError as exc:
            from fastapi import HTTPException
            raise HTTPException(status_code=503, detail=str(exc))

    @app.get("/api/trading/context/history")
    def trading_context_history(symbol: str, tf_sec: int = 300, limit: int = 50):
        return _trading_read_models().get_context_history(symbol=symbol, tf_sec=tf_sec, limit=limit)

    @app.get("/api/trading/positions/active")
    def trading_positions_active():
        try:
            return {"items": _trading_read_models().get_active_positions(allow_degraded=True)}
        except TradingReadModelUnavailableError as exc:
            from fastapi import HTTPException
            raise HTTPException(status_code=503, detail=str(exc))

    @app.get("/api/trading/positions/{lifecycle_id}")
    def trading_position_detail(lifecycle_id: str):
        item = _trading_read_models().get_position(lifecycle_id)
        if item is None:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=404, detail="lifecycle_id not found")
        return item

    @app.get("/api/trading/positions/{lifecycle_id}/brackets")
    def trading_position_brackets(lifecycle_id: str):
        item = _trading_read_models().get_bracket_state(lifecycle_id)
        if item is None:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=404, detail="lifecycle_id not found")
        return item

    @app.get("/api/trading/rejections/recent")
    def trading_recent_rejections(limit: int = 20):
        try:
            return {"items": _trading_read_models().get_recent_rejections(limit=limit)}
        except TradingReadModelUnavailableError as exc:
            from fastapi import HTTPException
            raise HTTPException(status_code=503, detail=str(exc))

    @app.get("/api/trading/decisions/recent")
    def trading_recent_decisions(limit: int = 20):
        return {"items": _trading_read_models().get_recent_decisions(limit=limit)}

    @app.get("/api/trading/market/overview")
    def trading_market_overview(symbols: Optional[str] = None, tf_sec: int = 300):
        symbol_list = [part.strip().upper() for part in str(
            symbols or "").split(",") if part.strip()]
        try:
            return _trading_read_models().get_market_overview(
                symbols=symbol_list,
                tf_sec=tf_sec,
                allow_degraded=True,
            )
        except TradingReadModelUnavailableError as exc:
            from fastapi import HTTPException
            raise HTTPException(status_code=503, detail=str(exc))


_register_statdump_route()
_register_trading_read_model_routes()
