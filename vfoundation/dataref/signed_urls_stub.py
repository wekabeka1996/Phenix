from __future__ import annotations
import base64
import hmac
import hashlib
import time
from typing import Tuple


def make_signed_url(path: str, ttl_s: int = 60) -> Tuple[str, str]:
    exp = int(time.time() + ttl_s)
    msg = f"{path}:{exp}".encode()
    key = b"local-secret"
    sig = base64.urlsafe_b64encode(hmac.new(key, msg, hashlib.sha256).digest()).decode()
    return f"file://{path}", sig
