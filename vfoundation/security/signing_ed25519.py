from __future__ import annotations
from typing import Tuple
from nacl.signing import SigningKey, VerifyKey
try:
    from nacl.exceptions import BadSignatureError  # type: ignore
except Exception:  # local shim fallback
    from nacl import BadSignatureError  # type: ignore
import hashlib
import os


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


def verify(payload: bytes, signature: bytes) -> bool:
    _, vk = load_keys()
    try:
        vk.verify(payload, signature)
        return True
    except BadSignatureError:
        return False
