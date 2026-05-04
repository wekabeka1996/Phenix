"""
DEPRECATED: This module is not used. Metrics are handled in apps.reference.telemetry.metrics.
Do not import or use this router — it will cause conflicts with /metrics endpoint in main.py.
"""

from fastapi import APIRouter, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

# DEPRECATED: Do not use this router
router = APIRouter()


@router.get("/metrics")
def metrics_endpoint():
    # DEPRECATED: This endpoint is duplicated in main.py and should not be used
    raise RuntimeError("DEPRECATED: Use /metrics from main.py instead. This router is not included in the app.")
