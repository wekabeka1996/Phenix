"""Tests for RBAC check/require — Blueprint 17.3."""
from __future__ import annotations

import pytest
from vfoundation.security.rbac_abac import Permission, RBACPolicy, Role


class TestRBACCheckRequire:
    def test_check_matches_is_allowed(self) -> None:
        """check() returns same result as is_allowed() with Permission."""
        policy = RBACPolicy()
        policy.grant(Role.ADMIN, Permission(resource="orders", action="write"))
        assert policy.check(Role.ADMIN, "orders", "write") is True
        assert policy.check(Role.VIEWER, "orders", "write") is False

    def test_require_raises_permission_error(self) -> None:
        """require() raises PermissionError when role lacks permission."""
        policy = RBACPolicy()
        with pytest.raises(PermissionError, match="lacks write on orders"):
            policy.require(Role.VIEWER, "orders", "write")

    def test_role_service_exists(self) -> None:
        """Role.SERVICE enum member exists."""
        assert Role.SERVICE.value == "service"
