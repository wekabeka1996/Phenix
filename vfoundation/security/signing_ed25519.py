from __future__ import annotations
from typing import Tuple
from nacl.signing import SigningKey, VerifyKey
try:
    from nacl.exceptions import BadSignatureError  # type: ignore
except Exception:  # local shim fallback
    from nacl import BadSignatureError  # type: ignore
import hashlib
import os
import json


def kms_seed() -> bytes:
    seed = os.getenv("VFOUNDATION_KMS_SEED", "demo-seed").encode()
    return hashlib.sha256(seed).digest()


def load_keys() -> Tuple[SigningKey, VerifyKey]:
    sk = SigningKey(kms_seed())
    vk = sk.verify_key
    return sk, vk


def sign(payload: bytes) -> bytes:
    sk, _ = load_keys()
    return sk.sign(payload).signature


def canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign_canonical_json(payload: object) -> bytes:
    return sign(canonical_json_bytes(payload))


def verify_canonical_json(payload: object, signature: bytes) -> bool:
    return verify(canonical_json_bytes(payload), signature)


def verify(payload: bytes, signature: bytes) -> bool:
    _, vk = load_keys()
    try:
        vk.verify(payload, signature)
        return True
    except (BadSignatureError, ValueError, TypeError):
        return False
