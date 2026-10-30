"""Role matrix per endpoint family."""

import pytest

from apps.accounts.models import User

ROLES = ["vezapp_admin", "a_admin", "a_planner", "a_viewer"]


@pytest.mark.parametrize(
    ("who", "expected"),
    [("vezapp_admin", 200), ("a_admin", 200), ("a_planner", 403), ("a_viewer", 403)],
)
def test_user_list_is_admin_only(login, users, who, expected):
    assert login(users[who]).get("/api/v1/users").status_code == expected


@pytest.mark.parametrize(
    ("who", "expected"),
    [("vezapp_admin", 201), ("a_admin", 403), ("a_planner", 403), ("a_viewer", 403)],
)
def test_only_vezapp_admin_creates_companies(login, users, who, expected):
    response = login(users[who]).post("/api/v1/companies", {"name": "New Foundry"}, format="json")
    assert response.status_code == expected


@pytest.mark.parametrize("who", ROLES)
def test_everyone_can_read_own_company(login, users, who):
    assert login(users[who]).get("/api/v1/companies").status_code == 200


@pytest.mark.parametrize(
    ("who", "expected"),
    [("vezapp_admin", 200), ("a_admin", 200), ("a_planner", 403), ("a_viewer", 403)],
)
def test_company_update_roles(login, users, company_a, who, expected):
    response = login(users[who]).patch(
        f"/api/v1/companies/{company_a.pk}", {"address": "New address"}, format="json"
    )
    assert response.status_code == expected


def test_company_admin_cannot_deactivate_company(login, users, company_a):
    response = login(users["a_admin"]).patch(
        f"/api/v1/companies/{company_a.pk}", {"is_active": False}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    ("who", "expected"),
    [("a_admin", 201), ("a_planner", 403), ("a_viewer", 403)],
)
def test_master_writes_follow_role_matrix(login, users, who, expected):
    response = login(users[who]).post("/api/v1/plants", {"name": "New Plant"}, format="json")
    assert response.status_code == expected


@pytest.mark.parametrize("who", ["a_admin", "a_planner", "a_viewer"])
def test_everyone_in_company_can_read_plants(login, users, plants, who):
    response = login(users[who]).get("/api/v1/plants")
    assert response.status_code == 200
    assert [p["name"] for p in response.json()["results"]] == ["A Plant"]


def test_company_admin_cannot_create_vezapp_admin(login, users):
    response = login(users["a_admin"]).post(
        "/api/v1/users",
        {"username": "evil", "password": "Str0ng-pass-99", "role": "vezapp_admin"},
        format="json",
    )
    assert response.status_code == 400
    assert not User.objects.filter(username="evil").exists()


def test_company_admin_creates_user_in_own_company_whatever_the_body_says(
    login, users, company_a, company_b
):
    response = login(users["a_admin"]).post(
        "/api/v1/users",
        {
            "username": "new.planner",
            "password": "Str0ng-pass-99",
            "role": "planner",
            "company": company_b.pk,
        },
        format="json",
    )
    assert response.status_code == 201
    assert User.objects.get(username="new.planner").company_id == company_a.pk


def test_non_vezapp_user_needs_a_company_as_vezapp_admin(login, users):
    response = login(users["vezapp_admin"]).post(
        "/api/v1/users",
        {"username": "orphan", "password": "Str0ng-pass-99", "role": "planner"},
        format="json",
    )
    assert response.status_code == 400


def test_password_is_never_returned(login, users):
    response = login(users["a_admin"]).get("/api/v1/users")
    assert all("password" not in row for row in response.json()["results"])


def test_user_cannot_delete_self(login, users):
    admin = users["a_admin"]
    assert login(admin).delete(f"/api/v1/users/{admin.pk}").status_code == 403
