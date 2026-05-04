class BadSignatureError(Exception):
    pass

# Provide exceptions submodule compatibility: `from nacl.exceptions import BadSignatureError`
class exceptions:  # type: ignore
    BadSignatureError = BadSignatureError
