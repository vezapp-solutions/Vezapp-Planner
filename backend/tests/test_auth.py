from django.conf import settings

from apps.accounts.authentication import ACCESS_COOKIE, REFRESH_COOKIE
from tests.conftest import PASSWORD


def test_health_is_public(db, anon_client):
    response = anon_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["app"] == settings.APP_NAME == "Vezapp Planner"


def test_login_sets_httponly_cookies_and_returns_profile(anon_client, users):
    response = anon_client.post(
        "/api/v1/auth/login", {"username": "a_planner", "password": PASSWORD}, format="json"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "planner"
    assert body["company"]["name"] == "Foundry A"
    assert "access" not in body and "refresh" not in body  # tokens never reach JS
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        assert response.cookies[name]["httponly"]
        assert response.cookies[name]["samesite"] == "Lax"


def test_login_rejects_bad_password_with_generic_message(anon_client, users):
    response = anon_client.post(
        "/api/v1/auth/login", {"username": "a_planner", "password": "nope"}, format="json"
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password."


def test_login_rejects_inactive_company(anon_client, users, company_a):
    company_a.is_active = False
    company_a.save()
    response = anon_client.post(
        "/api/v1/auth/login", {"username": "a_planner", "password": PASSWORD}, format="json"
    )
    assert response.status_code == 403


def test_me_requires_login(anon_client):
    assert anon_client.get("/api/v1/me").status_code == 401


def test_me_returns_current_user(login, users):
    response = login(users["vezapp_admin"]).get("/api/v1/me")
    assert response.status_code == 200
    assert response.json()["role"] == "vezapp_admin"
    assert response.json()["company"] is None


def test_cookie_write_without_client_header_is_refused(login, users):
    client = login(users["a_admin"])
    client.credentials()  # drop the custom header; cookies stay
    response = client.post("/api/v1/plants", {"name": "X"}, format="json")
    assert response.status_code == 403


def test_refresh_rotates_cookies(login, users):
    client = login(users["a_viewer"])
    old_refresh = client.cookies[REFRESH_COOKIE].value
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    assert client.cookies[REFRESH_COOKIE].value != old_refresh
    assert client.get("/api/v1/me").status_code == 200


def test_logout_clears_cookies_and_blacklists_refresh(login, users):
    client = login(users["a_viewer"])
    refresh = client.cookies[REFRESH_COOKIE].value
    assert client.post("/api/v1/auth/logout").status_code == 204

    client.cookies[REFRESH_COOKIE] = refresh  # replay the old refresh token
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_refresh_without_cookie_is_401(anon_client):
    assert anon_client.post("/api/v1/auth/refresh").status_code == 401


def test_deactivated_user_loses_access(login, users):
    client = login(users["a_viewer"])
    users["a_viewer"].is_active = False
    users["a_viewer"].save()
    assert client.get("/api/v1/me").status_code == 401
