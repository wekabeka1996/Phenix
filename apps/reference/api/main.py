# PATH: apps/reference/api/main.py
from __future__ import annotations
import os
from fastapi import FastAPI

# FSMP-REFACTOR-T03-B: Separate debug and production APIs
# Debug endpoints only available when TRADING_ENV != 'production'
if os.environ.get("TRADING_ENV", "development").lower() != "production":
    # Development/staging: expose full debug API
    from vfoundation.obs.debug_api import app
    print("INFO: Debug API endpoints are ENABLED (TRADING_ENV={})".format(
        os.environ.get("TRADING_ENV", "development")
    ))
else:
    # Production: clean API without debug endpoints
    app = FastAPI(
        title="Aurora Core API",
        description="Production API for Aurora Core FSM Federation",
        version="1.0.0"
    )
    
    @app.get("/health")
    async def health_check():
        """Basic health check endpoint."""
        return {"status": "healthy", "service": "aurora-core"}
    
    print("INFO: Debug API endpoints are DISABLED (production mode)")
