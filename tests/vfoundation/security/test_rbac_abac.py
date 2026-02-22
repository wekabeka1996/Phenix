"""Tests for vfoundation.security.rbac_abac — Phase 1.4."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _set_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the config singleton's token list directly."""
    from vfoundation.config import config
    monkeypatch.setattr(config, "rbac_admin_tokens", ["admin-tok-1", "admin-tok-2"])


def test_valid_bearer_token() -> None:
    from vfoundation.security.rbac_abac import require_admin
    assert require_admin("Bearer admin-tok-1") is True


def test_valid_bearer_token_second() -> None:
    from vfoundation.security.rbac_abac import require_admin
    assert require_admin("Bearer admin-tok-2") is True


def test_invalid_token() -> None:
    from vfoundation.security.rbac_abac import require_admin
    assert require_admin("Bearer wrong-token") is False


def test_none_header() -> None:
    from vfoundation.security.rbac_abac import require_admin
    assert require_admin(None) is False


def test_empty_header() -> None:
    from vfoundation.security.rbac_abac import require_admin
    assert require_admin("") is False
