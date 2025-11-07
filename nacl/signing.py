import hmac
import hashlib


class VerifyKey:
    def __init__(self, key_bytes: bytes):
        self._key = key_bytes

    def verify(self, payload: bytes, signature: bytes) -> None:
        expected = hmac.new(self._key, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, signature):
            from nacl import BadSignatureError

            raise BadSignatureError("invalid signature")


class SigningKey:
    def __init__(self, seed: bytes):
        # Derive a key for HMAC usage from seed
        self._key = hashlib.sha256(seed).digest()
        self.verify_key = VerifyKey(self._key)

    class _Sig:
        def __init__(self, sig: bytes):
            self.signature = sig

    def sign(self, payload: bytes):
        sig = hmac.new(self._key, payload, hashlib.sha256).digest()
        return self._Sig(sig)

