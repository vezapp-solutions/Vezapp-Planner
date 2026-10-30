"""Onboarding a client through the API the Companies and Users screens use."""

from apps.companies.models import Company
from apps.resources.models import ResourceType
from tests.conftest import PASSWORD, _client

NEW_PASSWORD = "Fresh-start-4821"


def test_vezapp_admin_onboards_a_company_and_its_first_admin(login, users):
    vezapp = login(users["vezapp_admin"])

    created = vezapp.post(
        "/api/v1/companies", {"name": "Sharma Castings", "gstin": ""}, format="json"
    )
    assert created.status_code == 201, created.content
    company = Company.objects.get(pk=created.json()["id"])
    # The standard resource types are ready for the new company.
    assert ResourceType.objects.filter(company=company).exists()

    admin = vezapp.post(
        "/api/v1/users",
        {
            "username": "sharma_admin",
            "role": "company_admin",
            "company": company.pk,
            "password": NEW_PASSWORD,
        },
        format="json",
    )
    assert admin.status_code == 201, admin.content
    assert "password" not in admin.json()

    # The new admin signs in and adds a planner to their own company only.
    client = _client()
    signed_in = client.post(
        "/api/v1/auth/login", {"username": "sharma_admin", "password": NEW_PASSWORD}, format="json"
    )
    assert signed_in.status_code == 200
    planner = client.post(
        "/api/v1/users",
        {"username": "sharma_planner", "role": "planner", "password": NEW_PASSWORD},
        format="json",
    )
    assert planner.status_code == 201, planner.content
    assert planner.json()["company"] == company.pk


def test_weak_or_missing_password_is_refused(login, users, company_a):
    vezapp = login(users["vezapp_admin"])
    base = {"username": "weak_user", "role": "viewer", "company": company_a.pk}

    assert vezapp.post("/api/v1/users", base, format="json").status_code == 400
    assert (
        vezapp.post("/api/v1/users", {**base, "password": "12345"}, format="json").status_code
        == 400
    )


def test_admin_sets_a_new_password_for_a_user(login, users):
    admin = login(users["a_admin"])
    response = admin.patch(
        f"/api/v1/users/{users['a_viewer'].pk}", {"password": NEW_PASSWORD}, format="json"
    )
    assert response.status_code == 200, response.content

    signed_in = _client().post(
        "/api/v1/auth/login", {"username": "a_viewer", "password": NEW_PASSWORD}, format="json"
    )
    assert signed_in.status_code == 200
    old = _client().post(
        "/api/v1/auth/login", {"username": "a_viewer", "password": PASSWORD}, format="json"
    )
    assert old.status_code in {400, 401}


def test_nobody_locks_themselves_out(login, users):
    me = users["a_admin"]
    admin = login(me)

    assert (
        admin.patch(f"/api/v1/users/{me.pk}", {"is_active": False}, format="json").status_code
        == 400
    )
    assert (
        admin.patch(f"/api/v1/users/{me.pk}", {"role": "viewer"}, format="json").status_code == 400
    )
    assert admin.delete(f"/api/v1/users/{me.pk}").status_code == 403
    # Saving other details of your own account is fine.
    assert (
        admin.patch(f"/api/v1/users/{me.pk}", {"first_name": "Asha"}, format="json").status_code
        == 200
    )


def test_company_admin_cannot_reach_another_companys_users(login, users):
    admin = login(users["a_admin"])
    other = users["b_viewer"]

    assert admin.get(f"/api/v1/users/{other.pk}").status_code == 404
    assert (
        admin.patch(f"/api/v1/users/{other.pk}", {"is_active": False}, format="json").status_code
        == 404
    )
