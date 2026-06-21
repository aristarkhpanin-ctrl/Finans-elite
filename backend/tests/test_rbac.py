"""Тесты ролей и прав доступа (RBAC, 6.4)."""
from types import SimpleNamespace

import pytest

from app.rbac import Perm, Role, has_permission


# --- матрица прав (юнит) ---

def test_permission_hierarchy():
    assert has_permission(Role.VIEWER, Perm.PROJECT_READ)
    assert not has_permission(Role.VIEWER, Perm.PROJECT_CREATE)
    assert has_permission(Role.ANALYST, Perm.PROJECT_UPDATE)
    assert not has_permission(Role.ANALYST, Perm.PROJECT_DELETE)
    assert has_permission(Role.EDITOR, Perm.PROJECT_DELETE)
    assert not has_permission(Role.EDITOR, Perm.MEMBER_MANAGE)
    assert has_permission(Role.ADMIN, Perm.MEMBER_MANAGE)
    assert not has_permission(Role.ADMIN, Perm.BILLING_MANAGE)
    assert has_permission(Role.OWNER, Perm.BILLING_MANAGE)


def test_unknown_role_has_no_permissions():
    assert not has_permission("ghost", Perm.PROJECT_READ)
    assert not has_permission(None, Perm.PROJECT_READ)


# --- сквозные тесты через API ---

@pytest.fixture
def team(client, register):
    owner = register("owner@e.ru", "Owner Org")
    org_id = client.post("/api/v1/organizations", json={"name": "Команда"}, headers=owner).json()["id"]
    owner_h = {**owner, "X-Organization-Id": org_id}

    def member(email: str, role: str) -> dict:
        h = register(email, f"personal-{email}")
        client.post(f"/api/v1/organizations/{org_id}/members",
                    json={"email": email, "role": role}, headers=owner_h)
        return {**h, "X-Organization-Id": org_id}

    return SimpleNamespace(org_id=org_id, owner=owner_h, member=member)


def _sample(client):
    return client.get("/api/v1/sample").json()


def _make_project(client, headers) -> str:
    return client.post("/api/v1/projects", json={"name": "P", "model": _sample(client)},
                       headers=headers).json()["id"]


def test_viewer_read_only(client, team):
    viewer = team.member("viewer@e.ru", "viewer")
    pid = _make_project(client, team.owner)
    # читать и считать — можно
    assert client.get("/api/v1/projects", headers=viewer).status_code == 200
    assert client.post(f"/api/v1/projects/{pid}/calculate", headers=viewer).status_code == 200
    # создавать/удалять — нельзя
    assert client.post("/api/v1/projects", json={"name": "X", "model": _sample(client)},
                       headers=viewer).status_code == 403
    assert client.delete(f"/api/v1/projects/{pid}", headers=viewer).status_code == 403


def test_analyst_can_edit_not_delete(client, team):
    analyst = team.member("analyst@e.ru", "analyst")
    pid = _make_project(client, analyst)  # analyst может создавать
    assert client.put(f"/api/v1/projects/{pid}", json={"name": "Y"}, headers=analyst).status_code == 200
    assert client.delete(f"/api/v1/projects/{pid}", headers=analyst).status_code == 403


def test_editor_full_project_lifecycle(client, team):
    editor = team.member("editor@e.ru", "editor")
    pid = _make_project(client, editor)
    assert client.delete(f"/api/v1/projects/{pid}", headers=editor).status_code == 204


def test_member_management_requires_admin(client, team):
    viewer = team.member("viewer@e.ru", "viewer")
    admin = team.member("admin@e.ru", "admin")
    payload = {"email": "x@e.ru", "role": "viewer"}
    # viewer не может управлять участниками
    assert client.post(f"/api/v1/organizations/{team.org_id}/members",
                       json=payload, headers=viewer).status_code == 403
    # admin — может
    assert client.post(f"/api/v1/organizations/{team.org_id}/members",
                       json=payload, headers=admin).status_code == 201


def test_invalid_role_rejected(client, team):
    assert client.post(f"/api/v1/organizations/{team.org_id}/members",
                       json={"email": "z@e.ru", "role": "superuser"},
                       headers=team.owner).status_code == 422


def test_my_organizations_lists_roles(client, team):
    viewer = team.member("viewer@e.ru", "viewer")
    orgs = client.get("/api/v1/organizations", headers=viewer).json()
    # у пользователя своя организация (owner) и команда (viewer)
    roles = {o["name"]: o["role"] for o in orgs}
    assert roles["Команда"] == "viewer"
