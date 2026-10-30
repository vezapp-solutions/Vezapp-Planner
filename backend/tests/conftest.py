import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.roles import Role
from apps.companies.models import Company, Plant

PASSWORD = "Test-pass-12345"


@pytest.fixture
def company_a(db):
    return Company.objects.create(name="Foundry A")


@pytest.fixture
def company_b(db):
    return Company.objects.create(name="Foundry B")


def make_user(username, role, company=None):
    return User.objects.create_user(
        username=username, password=PASSWORD, role=role, company=company
    )


@pytest.fixture
def users(company_a, company_b):
    return {
        "vezapp_admin": make_user("vz", Role.VEZAPP_ADMIN),
        "a_admin": make_user("a_admin", Role.COMPANY_ADMIN, company_a),
        "a_planner": make_user("a_planner", Role.PLANNER, company_a),
        "a_viewer": make_user("a_viewer", Role.VIEWER, company_a),
        "b_admin": make_user("b_admin", Role.COMPANY_ADMIN, company_b),
        "b_viewer": make_user("b_viewer", Role.VIEWER, company_b),
    }


@pytest.fixture
def plants(company_a, company_b):
    return {
        "a": Plant.objects.create(company=company_a, name="A Plant"),
        "b": Plant.objects.create(company=company_b, name="B Plant"),
    }


def _client():
    client = APIClient()
    client.credentials(HTTP_X_VP_CLIENT="web")
    return client


@pytest.fixture
def anon_client():
    return _client()


@pytest.fixture
def login(db):
    """Sign in through the real endpoint so cookies, CSRF header and audit context are exercised."""

    def _login(user):
        client = _client()
        response = client.post(
            "/api/v1/auth/login", {"username": user.username, "password": PASSWORD}, format="json"
        )
        assert response.status_code == 200, response.content
        return client

    return _login
