from fastapi import APIRouter, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

router = APIRouter()


@router.get("/metrics")
def metrics_endpoint():
    data = generate_latest()  # default REGISTRY — бачить все, в т.ч. exposure_equity_usd
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
