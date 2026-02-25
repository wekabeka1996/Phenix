from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError
import sys

vk = VerifyKey(b"\x00" * 32)
try:
    vk.verify(b"payload", b"short")
    print("No exception")
except BadSignatureError:
    print("Caught BadSignatureError")
except ValueError as e:
    print(f"Caught ValueError: {e}")
except TypeError as e:
    print(f"Caught TypeError: {e}")
except Exception as e:
    print(f"Caught unexpected: {type(e).__name__}: {e}")
