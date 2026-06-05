"""Quick debug test to see actual evalsha behavior."""

from vfoundation.core.idempotency.backends.redis_store import RedisIdempotencyStore


def test_debug_evalsha_simple(
    redis_url: str,
    lua_executor: object,
) -> None:
    """Debug test: check what evalsha returns."""
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id="debug-worker",
        ttl_ms=60_000,
        timeout_ms=100,
    )

    # Try simple reserve
    try:
        result = store.reserve(
            key="debug-key",
            payload_digest="abc123",
            ttl_ms=10_000,
            owner="debug-worker",
        )
        print(f"SUCCESS: {result}")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        raise
