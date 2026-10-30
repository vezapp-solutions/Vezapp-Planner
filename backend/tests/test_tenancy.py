"""Company A must never see, change, create into or reference company B's data."""

import pytest

from apps.accounts.models import User
from apps.companies.models import Company, Plant


def test_list_only_returns_own_company_rows(login, users, plants):
    rows = login(users["a_admin"]).get("/api/v1/plants").json()["results"]
    assert [r["id"] for r in rows] == [plants["a"].pk]


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_other_company_row_is_404_not_403(login, users, plants, method):
    client = login(users["a_admin"])
    url = f"/api/v1/plants/{plants['b'].pk}"
    kwargs = {"data": {"name": "Hacked"}, "format": "json"} if method == "patch" else {}
    assert getattr(client, method)(url, **kwargs).status_code == 404
    assert Plant.objects.get(pk=plants["b"].pk).name == "B Plant"


def test_company_in_request_body_is_ignored_on_create(login, users, company_a, company_b):
    response = login(users["a_admin"]).post(
        "/api/v1/plants", {"name": "Sneaky", "company": company_b.pk}, format="json"
    )
    assert response.status_code == 201
    assert Plant.objects.get(name="Sneaky").company_id == company_a.pk


def test_company_cannot_be_moved_by_update(login, users, plants, company_b):
    response = login(users["a_admin"]).patch(
        f"/api/v1/plants/{plants['a'].pk}", {"company": company_b.pk}, format="json"
    )
    assert response.status_code == 200
    assert Plant.objects.get(pk=plants["a"].pk).company_id != company_b.pk


def test_same_plant_name_is_allowed_in_different_companies(login, users, plants):
    response = login(users["a_admin"]).post("/api/v1/plants", {"name": "B Plant"}, format="json")
    assert response.status_code == 201


def test_duplicate_plant_name_in_one_company_is_a_400_not_a_500(login, users, plants):
    response = login(users["a_admin"]).post("/api/v1/plants", {"name": "a plant"}, format="json")
    assert response.status_code == 400


def test_user_list_and_detail_are_scoped_to_company(login, users):
    client = login(users["a_admin"])
    names = {r["username"] for r in client.get("/api/v1/users").json()["results"]}
    assert names == {"a_admin", "a_planner", "a_viewer"}
    assert client.get(f"/api/v1/users/{users['b_admin'].pk}").status_code == 404
    assert (
        client.patch(
            f"/api/v1/users/{users['b_admin'].pk}", {"first_name": "X"}, format="json"
        ).status_code
        == 404
    )


def test_company_endpoint_hides_other_companies(login, users, company_a, company_b):
    client = login(users["a_viewer"])
    assert [c["id"] for c in client.get("/api/v1/companies").json()["results"]] == [company_a.pk]
    assert client.get(f"/api/v1/companies/{company_b.pk}").status_code == 404


def test_company_header_override_is_ignored_for_company_users(login, users, plants, company_b):
    client = login(users["a_admin"])
    client.credentials(HTTP_X_VP_CLIENT="web", HTTP_X_COMPANY_ID=str(company_b.pk))
    rows = client.get("/api/v1/plants").json()["results"]
    assert [r["id"] for r in rows] == [plants["a"].pk]


def test_vezapp_admin_without_header_sees_no_tenant_rows(login, users, plants):
    assert login(users["vezapp_admin"]).get("/api/v1/plants").json()["results"] == []


def test_vezapp_admin_can_act_for_a_company_with_header(login, users, plants, company_b):
    client = login(users["vezapp_admin"])
    client.credentials(HTTP_X_VP_CLIENT="web", HTTP_X_COMPANY_ID=str(company_b.pk))
    rows = client.get("/api/v1/plants").json()["results"]
    assert [r["id"] for r in rows] == [plants["b"].pk]
    created = client.post("/api/v1/plants", {"name": "Added by Vezapp"}, format="json")
    assert created.status_code == 201
    assert Plant.objects.get(name="Added by Vezapp").company_id == company_b.pk


def test_vezapp_admin_header_for_inactive_or_unknown_company_yields_nothing(
    login, users, plants, company_b
):
    company_b.is_active = False
    company_b.save()
    client = login(users["vezapp_admin"])
    client.credentials(HTTP_X_VP_CLIENT="web", HTTP_X_COMPANY_ID=str(company_b.pk))
    assert client.get("/api/v1/plants").json()["results"] == []
    client.credentials(HTTP_X_VP_CLIENT="web", HTTP_X_COMPANY_ID="99999")
    assert client.get("/api/v1/plants").json()["results"] == []
    assert client.post("/api/v1/plants", {"name": "Nope"}, format="json").status_code == 400


def test_queryset_helper_returns_nothing_without_a_company(db, plants):
    assert Plant.objects.for_company(None).count() == 0


def test_user_model_forbids_company_less_non_admin(db):
    from django.db import IntegrityError, transaction

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(username="loose", password="x", role="planner")
    assert not Company.objects.filter(name="loose").exists()
