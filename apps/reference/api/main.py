# PATH: apps/reference/api/main.py
from __future__ import annotations
import os
from fastapi import FastAPI

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

    @app.get("/health")
    async def health_check():
        """Basic health check endpoint."""
        return {"status": "healthy", "service": "aurora-core"}

    @app.get("/metrics")
    def metrics():
        from vfoundation.apps.reference.telemetry.metrics import (
            generate_latest,
            CONTENT_TYPE_LATEST,
        )

        data = generate_latest()
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
        from vfoundation.apps.reference.telemetry.metrics import generate_latest

        txt = generate_latest().decode("utf-8", "replace")

        equity = _mget(txt, "exposure_equity_usd")
        pos_usd = _mget(txt, "exposure_positions_usd")
        pend_usd = _mget(txt, "exposure_pending_usd")
        limit_usd = _mget(txt, "exposure_limit_usd")
        exp_rej = _mget(txt, "fsm_guard_rejects_total", 'guard="exposure"')
        ttl_exp = _mget(txt, "pending_exposure_expired_total")
        placed = _mget(txt, "orders_placed_total")
        filled = _mget(txt, "orders_filled_total")

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
        }
        from fastapi.responses import JSONResponse

        return JSONResponse(data)

    print("INFO: Debug API endpoints are DISABLED (production mode)")
