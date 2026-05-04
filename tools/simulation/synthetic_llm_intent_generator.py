#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, Optional


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Stage A synthetic external intent generator for /intents/llm/v1"
    )
    p.add_argument("--base-url", required=True, help="Example: https://127.0.0.1:8443")
    p.add_argument("--token", required=True, help="Bearer token")
    p.add_argument("--symbol", default="BNBUSDT")
    p.add_argument("--side", choices=["BUY", "SELL"], default="BUY")
    p.add_argument("--qty", default="0.05", help="Requested qty")
    p.add_argument("--offset-bps", type=float, default=5.0, help="Limit offset from reference in bps")
    p.add_argument("--tp-pct", type=float, default=0.4, help="TP percent from entry")
    p.add_argument("--sl-pct", type=float, default=0.25, help="SL percent from entry")
    p.add_argument("--timeout-sec", type=float, default=8.0)
    p.add_argument("--insecure", action="store_true", help="Skip TLS cert verification")
    return p.parse_args()


def _http_json(
    method: str,
    url: str,
    *,
    token: str,
    body: Optional[Dict[str, Any]] = None,
    timeout_sec: float = 8.0,
    insecure: bool = False,
) -> Dict[str, Any]:
    data = None
    headers = {"Authorization": f"Bearer {token}"}
    if body is not None:
        data = json.dumps(body, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url=url, method=method.upper(), data=data, headers=headers)
    ctx = None
    if insecure:
        ctx = ssl._create_unverified_context()

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec, context=ctx) as resp:
            raw = resp.read().decode("utf-8")
            return {"status": int(resp.status), "json": json.loads(raw) if raw else {}}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"raw": raw}
        return {"status": int(e.code), "json": parsed}


def _extract_reference_price(snapshot: Dict[str, Any]) -> Decimal:
    features = snapshot.get("features")
    if isinstance(features, dict) and features.get("price") is not None:
        return Decimal(str(features.get("price")))
    bar = snapshot.get("bar")
    if isinstance(bar, dict) and bar.get("close") is not None:
        return Decimal(str(bar.get("close")))
    raise ValueError("Snapshot has no features.price or bar.close")


def _fmt_price(px: Decimal) -> str:
    return str(px.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN).normalize())


def main() -> int:
    args = _parse_args()
    base = args.base_url.rstrip("/")
    symbol = str(args.symbol).upper()
    side = str(args.side).upper()

    q = urllib.parse.urlencode({"symbol": symbol})
    snap_url = f"{base}/snapshots/latest?{q}"
    snap_resp = _http_json(
        "GET",
        snap_url,
        token=args.token,
        timeout_sec=args.timeout_sec,
        insecure=args.insecure,
    )
    if snap_resp["status"] != 200:
        print(f"[ERR] snapshots/latest failed status={snap_resp['status']} body={snap_resp['json']}")
        return 1

    snapshot = snap_resp["json"]
    try:
        ref_price = _extract_reference_price(snapshot)
    except Exception as e:
        print(f"[ERR] cannot extract reference price: {e}")
        return 1

    bps = Decimal(str(args.offset_bps)) / Decimal("10000")
    tp_pct = Decimal(str(args.tp_pct)) / Decimal("100")
    sl_pct = Decimal(str(args.sl_pct)) / Decimal("100")

    if side == "BUY":
        limit_price = ref_price * (Decimal("1") - bps)
        tp_price = limit_price * (Decimal("1") + tp_pct)
        sl_price = limit_price * (Decimal("1") - sl_pct)
    else:
        limit_price = ref_price * (Decimal("1") + bps)
        tp_price = limit_price * (Decimal("1") - tp_pct)
        sl_price = limit_price * (Decimal("1") + sl_pct)

    snapshot_id = str(snapshot.get("snapshot_id") or "")
    digest_src = json.dumps(
        {
            "snapshot_id": snapshot_id,
            "symbol": symbol,
            "ts_ms": snapshot.get("ts_ms"),
            "features": snapshot.get("features"),
            "bar": snapshot.get("bar"),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    inputs_digest = hashlib.sha256(digest_src.encode("utf-8")).hexdigest()

    intent_id = str(uuid.uuid4())
    payload: Dict[str, Any] = {
        "intent_id": intent_id,
        "ts_ms": int(time.time() * 1000),
        "symbol": symbol,
        "side": side,
        "order": {
            "type": "LIMIT",
            "limit_price": _fmt_price(limit_price),
            "qty": str(args.qty),
            "time_in_force": "GTC",
        },
        "brackets": {
            "tp_price": _fmt_price(tp_price),
            "sl_price": _fmt_price(sl_price),
        },
        "snapshot_ref": {
            "snapshot_id": snapshot_id or f"synthetic-{int(time.time())}",
            "inputs_digest": inputs_digest,
        },
        "model_meta": {
            "model": "synthetic_intent_generator",
            "temperature": 0.0,
            "prompt_hash": hashlib.sha256(b"synthetic_stage_a").hexdigest()[:32],
        },
        "why_short": "stage_a synthetic limit intent",
    }

    idem_stable = json.dumps(
        {
            "symbol": payload["symbol"],
            "side": payload["side"],
            "order": payload["order"],
            "brackets": payload["brackets"],
            "snapshot_ref": payload["snapshot_ref"],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    payload["idempotency_key"] = f"synthetic:{hashlib.sha256(idem_stable.encode('utf-8')).hexdigest()}"

    post_url = f"{base}/intents/llm/v1"
    post_resp = _http_json(
        "POST",
        post_url,
        token=args.token,
        body=payload,
        timeout_sec=args.timeout_sec,
        insecure=args.insecure,
    )

    print(f"[INFO] symbol={symbol} side={side} ref={_fmt_price(ref_price)} limit={payload['order']['limit_price']}")
    print(f"[INFO] POST status={post_resp['status']}")
    print(json.dumps(post_resp["json"], indent=2, ensure_ascii=False))
    return 0 if post_resp["status"] == 202 else 2


if __name__ == "__main__":
    sys.exit(main())
