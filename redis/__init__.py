"""
Local shim for `redis` package to make tests runnable without a Redis server.

Behavior:
- If real `redis` package is installed, re-export it.
- Otherwise, if `fakeredis` is available, provide a minimal compatible surface:
  * `from_url(...)` -> returns `fakeredis.FakeRedis(decode_responses=True)`
  * `RedisError` exception class
  * Common aliases expected by callers
"""

try:  # Prefer real redis if present
    from redis import *  # type: ignore
except Exception:  # Fallback to fakeredis-based shim
    try:
        import fakeredis

        class RedisError(Exception):
            pass

        def from_url(url: str, **kwargs):  # minimal signature used by code
            # ignore URL and return an in-memory FakeRedis client
            decode = kwargs.get("decode_responses", True)
            return fakeredis.FakeRedis(decode_responses=decode)

        # Provide minimal names some code may import
        Redis = fakeredis.FakeRedis  # type: ignore

    except Exception as e:  # Last resort: stub that raises at runtime
        class RedisError(Exception):
            pass

        def from_url(*args, **kwargs):  # pragma: no cover
            raise ImportError(
                "Neither 'redis' nor 'fakeredis' is available. Install one of them."
            )

