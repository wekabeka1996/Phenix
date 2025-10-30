"""
Test ImportError guard (REDIS_AVAILABLE=False) — lines 19-21.

Strategy: MetaPathFinder blocks redis import before redis_store.py loads.
"""

import importlib.util
import os
import sys
from importlib.abc import MetaPathFinder
from types import ModuleType
from typing import Optional

import pytest


class BlockRedisImportFinder(MetaPathFinder):
    """Meta path finder that blocks redis import."""

    def find_spec(
        self,
        fullname: str,
        path: Optional[list[str]],
        target: Optional[ModuleType] = None,
    ) -> None:
        """Block redis import by returning None and raising ImportError."""
        if fullname == "redis" or fullname.startswith("redis."):
            raise ImportError(f"redis import blocked by test (fullname={fullname})")
        return None


def test_import_guard_sets_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Cover lines 19-21: REDIS_AVAILABLE=False when redis import fails.

    Uses MetaPathFinder to block redis import before redis_store.py loads.
    """
    # Step 1: Disable autouse Lua patch
    monkeypatch.setenv("IDEMP_TEST_DISABLE_LUA_PATCH", "1")

    # Step 2: Remove redis from sys.modules (if already loaded)
    modules_to_remove = [
        k for k in sys.modules if k == "redis" or k.startswith("redis.")
    ]
    for mod in modules_to_remove:
        sys.modules.pop(mod, None)

    # Step 3: Install MetaPathFinder at position 0 (highest priority)
    finder = BlockRedisImportFinder()
    sys.meta_path.insert(0, finder)

    try:
        # Step 4: Load redis_store.py as new module (not from sys.modules cache)
        redis_store_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "vfoundation",
            "vfoundation",
            "core",
            "idempotency",
            "backends",
            "redis_store.py",
        )
        redis_store_path = os.path.abspath(redis_store_path)

        spec = importlib.util.spec_from_file_location(
            "test_idemp_store_fallback",  # Unique module name
            redis_store_path,
        )
        assert spec is not None, "Failed to create spec"
        assert spec.loader is not None, "Spec has no loader"

        module = importlib.util.module_from_spec(spec)

        # Step 5: Execute module → triggers lines 16-21
        try:
            spec.loader.exec_module(module)
        except ImportError:
            # Expected: redis import fails, but module should handle it
            pass

        # Step 6: Verify REDIS_AVAILABLE=False
        assert hasattr(module, "REDIS_AVAILABLE"), "Module should have REDIS_AVAILABLE"
        assert module.REDIS_AVAILABLE is False, (
            "REDIS_AVAILABLE should be False when redis import blocked"
        )

        # Verify Redis class is None
        assert hasattr(module, "Redis"), "Module should have Redis"
        assert module.Redis is None, "Redis should be None when import fails"

    finally:
        # Cleanup: Remove finder and test module
        if finder in sys.meta_path:
            sys.meta_path.remove(finder)
        sys.modules.pop("test_idemp_store_fallback", None)

        # Re-enable autouse patch for subsequent tests
        monkeypatch.delenv("IDEMP_TEST_DISABLE_LUA_PATCH", raising=False)
