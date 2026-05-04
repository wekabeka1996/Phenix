"""Tests for RBAC roles and policy — Phase 17.3."""
import pytest

from vfoundation.security.rbac_abac import Permission, RBACPolicy, Role


class TestRBACPolicy:
    """Phase 17.3: Role-based access control tests."""

    def test_role_enum_values(self):
        """Role enum has viewer, operator, admin."""
        assert Role.VIEWER.value == "viewer"
        assert Role.OPERATOR.value == "operator"
        assert Role.ADMIN.value == "admin"

    def test_grant_and_is_allowed(self):
        """Grant a permission and verify access."""
        policy = RBACPolicy()
        perm = Permission(resource="orders", action="read")
        policy.grant(Role.VIEWER, perm)
        assert policy.is_allowed(Role.VIEWER, perm) is True
        assert policy.is_allowed(Role.ADMIN, perm) is False

    def test_revoke(self):
        """Revoke a permission and verify denial."""
        policy = RBACPolicy()
        perm = Permission(resource="config", action="write")
        policy.grant(Role.ADMIN, perm)
        assert policy.is_allowed(Role.ADMIN, perm) is True
        policy.revoke(Role.ADMIN, perm)
        assert policy.is_allowed(Role.ADMIN, perm) is False

    def test_permissions_for(self):
        """permissions_for returns all grants for a role."""
        policy = RBACPolicy()
        p1 = Permission(resource="orders", action="read")
        p2 = Permission(resource="orders", action="write")
        policy.grant(Role.OPERATOR, p1)
        policy.grant(Role.OPERATOR, p2)
        perms = policy.permissions_for(Role.OPERATOR)
        assert len(perms) == 2
        assert p1 in perms
        assert p2 in perms
