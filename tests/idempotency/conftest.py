"""
Shared fixtures for idempotency tests.

Auto-patches Redis with Lua emulation for ALL tests in this directory.
Can be disabled per-test via IDEMP_TEST_DISABLE_LUA_PATCH=1 env var.
"""

import hashlib
import os
from typing import Generator

import pytest

from tests.idempotency.fixtures.lua_executor import LuaExecutor


try:
    import fakeredis
    import redis as redis_module

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    fakeredis = None  # type: ignore
    redis_module = None  # type: ignore


# Global state for session-wide Lua emulation
_GLOBAL_FAKE_REDIS: object = None
_GLOBAL_EXECUTOR: object = None
_ORIGINAL_FROM_URL: object = None
_ORIGINAL_STORE_INIT: object = None


def _setup_global_lua_patch() -> None:
    """Setup global Lua emulation patches (called once at module load)."""
    global \
        _GLOBAL_FAKE_REDIS, \
        _GLOBAL_EXECUTOR, \
        _ORIGINAL_FROM_URL, \
        _ORIGINAL_STORE_INIT

    # Check if patch disabled via env var
    if os.environ.get("IDEMP_TEST_DISABLE_LUA_PATCH") == "1":
        return

    if not REDIS_AVAILABLE:
        return

    if _GLOBAL_FAKE_REDIS is not None:
        return  # Already patched

    # Create shared fakeredis instance
    _GLOBAL_FAKE_REDIS = fakeredis.FakeStrictRedis(decode_responses=True)
    fake_redis = _GLOBAL_FAKE_REDIS

    # Create LuaExecutor
    _GLOBAL_EXECUTOR = LuaExecutor(fake_redis)  # type: ignore
    executor = _GLOBAL_EXECUTOR

    # Patch redis.from_url
    _ORIGINAL_FROM_URL = redis_module.from_url

    def fake_from_url(*args: object, **kwargs: object) -> object:
        return fake_redis

    redis_module.from_url = fake_from_url  # type: ignore

    # Patch script_load
    script_sha_map: dict[str, str] = {}

    def fake_script_load(script: str) -> str:
        if script not in script_sha_map:
            sha = hashlib.sha1(script.encode()).hexdigest()[:40]
            script_sha_map[script] = sha

            # Infer script type (order matters!)
            if "DELETE" in script or "DEL" in script:
                executor.register_script(sha, "release")  # type: ignore
            elif "status" in script and "CONFIRMED" in script:
                executor.register_script(sha, "confirm")  # type: ignore
            elif "EXISTS" in script and "owner" in script:
                executor.register_script(sha, "reserve")  # type: ignore

        return script_sha_map[script]

    fake_redis.script_load = fake_script_load  # type: ignore

    # Patch client.eval (fallback when _use_sha=False)
    def fake_eval(script: str, numkeys: int, *keys_and_args: str) -> object:
        # Infer script type from content
        if "EXISTS" in script and "owner" in script:
            script_type = "reserve"
        elif "status" in script and "CONFIRMED" in script:
            script_type = "confirm"
        elif "DELETE" in script or "DEL" in script:
            script_type = "release"
        else:
            raise ValueError(f"Cannot classify script for eval: {script[:50]}")

        # Route to executor by script type
        if script_type == "reserve":
            return executor._execute_reserve(numkeys, *keys_and_args)  # type: ignore
        elif script_type == "confirm":
            return executor._execute_confirm(numkeys, *keys_and_args)  # type: ignore
        elif script_type == "release":
            return executor._execute_release(numkeys, *keys_and_args)  # type: ignore
        else:
            raise ValueError(f"Unknown script type: {script_type}")

    fake_redis.eval = fake_eval  # type: ignore

    # Patch RedisIdempotencyStore.__init__
    from vfoundation.core.idempotency.backends import redis_store

    _ORIGINAL_STORE_INIT = redis_store.RedisIdempotencyStore.__init__

    def patched_init(self: object, *args: object, **kwargs: object) -> None:
        _ORIGINAL_STORE_INIT(self, *args, **kwargs)  # type: ignore

        store_self: redis_store.RedisIdempotencyStore = self  # type: ignore

        def patched_evalsha(sha: str, numkeys: int, *keys_and_args: str) -> object:
            return executor.evalsha(sha, numkeys, *keys_and_args)  # type: ignore

        store_self.client.evalsha = patched_evalsha  # type: ignore

    redis_store.RedisIdempotencyStore.__init__ = patched_init  # type: ignore


# Apply patches at module load time
_setup_global_lua_patch()


@pytest.fixture
def redis_url() -> str:
    """Redis URL for testing."""
    return "redis://localhost:6379/15"


@pytest.fixture
def worker_id() -> str:
    """Default worker ID for tests."""
    return "test-worker-1"


@pytest.fixture
def lua_executor() -> Generator[LuaExecutor, None, None]:
    """
    Access to global LuaExecutor (for tests that need it explicitly).
    """
    if not REDIS_AVAILABLE:
        pytest.skip("fakeredis not installed")

    yield _GLOBAL_EXECUTOR  # type: ignore


@pytest.fixture
def make_digest() -> object:
    """Helper to create payload digest."""

    def _make_digest(payload: str) -> str:
        return hashlib.sha256(payload.encode()).hexdigest()

    return _make_digest


@pytest.fixture(autouse=True)
def cleanup_redis() -> Generator[None, None, None]:
    """Auto-cleanup Redis after each test."""
    yield

    if _GLOBAL_FAKE_REDIS is not None:
        _GLOBAL_FAKE_REDIS.flushdb()  # type: ignore
