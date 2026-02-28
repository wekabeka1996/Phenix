from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Set


class Role(Enum):
    """Standard RBAC roles."""

    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"
    SERVICE = "service"


@dataclass(frozen=True)
class Permission:
    """A single permission grant."""

    resource: str  # e.g., "orders", "config", "metrics"
    action: str    # e.g., "read", "write", "execute"


class RBACPolicy:
    """Role-based access control policy with grant/revoke/check."""

    def __init__(self) -> None:
        self._grants: Dict[Role, Set[Permission]] = {}

    def grant(self, role: Role, permission: Permission) -> None:
        """Grant a permission to a role."""
        self._grants.setdefault(role, set()).add(permission)

    def revoke(self, role: Role, permission: Permission) -> None:
        """Revoke a permission from a role."""
        perms = self._grants.get(role)
        if perms:
            perms.discard(permission)

    def is_allowed(self, role: Role, permission: Permission) -> bool:
        """Check if a role has the given permission."""
        return permission in self._grants.get(role, set())

    def permissions_for(self, role: Role) -> Set[Permission]:
        """Return all permissions granted to a role."""
        return set(self._grants.get(role, set()))

    def check(self, role: Role, resource: str, action: str) -> bool:
        """Blueprint 17.3: Check if role has permission for resource+action."""
        return self.is_allowed(role, Permission(resource=resource, action=action))

    def require(self, role: Role, resource: str, action: str) -> None:
        """Blueprint 17.3: Raise PermissionError if role lacks permission."""
        if not self.check(role, resource, action):
            raise PermissionError(
                f"Role {role.value} lacks {action} on {resource}"
            )


def require_admin(auth_header: Optional[str]) -> bool:
    # Lazy import to support test ENV changes
    from ..config import config

    if not auth_header:
        return False
    token = auth_header.replace("Bearer ", "")
    return token in config.rbac_admin_tokens
