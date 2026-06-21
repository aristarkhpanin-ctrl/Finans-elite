"""Роли и права доступа (RBAC, 6.4; ARCHITECTURE-SaaS.md §11).

Иерархия прав (по возрастанию): viewer ⊂ analyst ⊂ editor ⊂ admin ⊂ owner.
"""
from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    ANALYST = "analyst"
    VIEWER = "viewer"


class Perm(str, Enum):
    PROJECT_READ = "project.read"
    PROJECT_CREATE = "project.create"
    PROJECT_UPDATE = "project.update"
    PROJECT_DELETE = "project.delete"
    PROJECT_CALCULATE = "project.calculate"
    MEMBER_READ = "member.read"
    MEMBER_MANAGE = "member.manage"
    ORG_MANAGE = "org.manage"
    BILLING_MANAGE = "billing.manage"


_VIEWER = {Perm.PROJECT_READ, Perm.PROJECT_CALCULATE, Perm.MEMBER_READ}
_ANALYST = _VIEWER | {Perm.PROJECT_CREATE, Perm.PROJECT_UPDATE}
_EDITOR = _ANALYST | {Perm.PROJECT_DELETE}
_ADMIN = _EDITOR | {Perm.MEMBER_MANAGE}
_OWNER = _ADMIN | {Perm.ORG_MANAGE, Perm.BILLING_MANAGE}

ROLE_PERMISSIONS: dict[Role, set[Perm]] = {
    Role.VIEWER: _VIEWER,
    Role.ANALYST: _ANALYST,
    Role.EDITOR: _EDITOR,
    Role.ADMIN: _ADMIN,
    Role.OWNER: _OWNER,
}


def is_valid_role(role: str) -> bool:
    return role in (r.value for r in Role)


def has_permission(role: str | None, perm: Perm) -> bool:
    if role is None or not is_valid_role(role):
        return False
    return perm in ROLE_PERMISSIONS[Role(role)]
