"""Tests for distributed idempotency layer (FSMP-P2-T02).

NOTE: These tests are superseded by tests/vfoundation/core/test_redis_store.py (Phase 9.1).
The skip is kept in place until Phase 9.1 is complete and provides equivalent coverage.
This module will be removed after Phase 9.1 completion.
"""
import pytest
pytest.skip("Idempotency tests - superseded by test_redis_store.py (Phase 9.1)",
            allow_module_level=True)
