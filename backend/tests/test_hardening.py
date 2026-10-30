"""Hardening: production settings guards, response headers, list endpoints that must not run more
queries as rows grow, and the admin view of assistant questions."""

import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.assistant.models import AssistantLog
from apps.masters.models import Customer, Part, PartCustomer
from apps.resources.models import Resource
from apps.scheduler.models import ScheduleLine
from seeds.worked_example import build_worked_example

J = {"format": "json"}
BACKEND = Path(__file__).resolve().parent.parent
TODAY = date(2026, 11, 2)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("django.utils.timezone.localdate", lambda *a, **k: TODAY)
    cache.clear()


# --- production settings ---------------------------------------------------------------------------
def settings_error(**env) -> str:
    """Import the base settings in a clean process with the given environment; return its error."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "DB_", "COOKIE_"))}
    clean.update({"DB_ENGINE": "sqlite", **env})
    run = subprocess.run(
        [sys.executable, "-I", "-c", "import sys; sys.path.insert(0, '.'); import config.settings.base"],
        cwd=BACKEND, env=clean, capture_output=True, text=True, check=False,
    )  # fmt: skip
    return run.stderr


@pytest.mark.parametrize(
    "key",
    ["", "short-key", "change-me-to-a-long-random-string-0123456789", "x" * 31],
)
def test_production_refuses_a_weak_or_missing_secret_key(key):
    assert "DJANGO_SECRET_KEY" in settings_error(DJANGO_DEBUG="false", DJANGO_SECRET_KEY=key)


def test_production_accepts_a_long_random_key_and_turns_the_protections_on():
    key = "k" * 50
    assert settings_error(DJANGO_DEBUG="false", DJANGO_SECRET_KEY=key) == ""
    probe = subprocess.run(
        [sys.executable, "-I", "-c", "import sys; sys.path.insert(0, '.'); import config.settings.base as s; print(s.SECURE_SSL_REDIRECT, s.SECURE_HSTS_SECONDS, s.COOKIE_SECURE, s.X_FRAME_OPTIONS, s.DEBUG)"],
        cwd=BACKEND, capture_output=True, text=True, check=False,
        env={**{k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "COOKIE_"))}, "DB_ENGINE": "sqlite", "DJANGO_DEBUG": "false", "DJANGO_SECRET_KEY": key},
    )  # fmt: skip
    assert probe.stdout.split() == ["True", "31536000", "True", "DENY", "False"], probe.stderr


def test_a_short_key_is_allowed_in_debug_for_local_work():
    assert settings_error(DJANGO_DEBUG="true", DJANGO_SECRET_KEY="") == ""


# --- headers ------------------------------------------------------------------------------------------
def test_responses_carry_the_browser_protections(anon_client):
    response = anon_client.get("/api/v1/health")
    assert response["X-Frame-Options"] == "DENY" and response["X-Content-Type-Options"] == "nosniff"
    assert response["Referrer-Policy"] == "same-origin"


def test_cookies_are_httponly_and_lax(login, users):
    cookies = login(users["a_admin"]).cookies
    for name in ("vp_access", "vp_refresh"):
        assert cookies[name]["httponly"] and cookies[name]["samesite"] == "Lax"


def test_a_state_changing_cookie_request_needs_the_client_header(login, users):
    client = login(users["a_planner"])
    assert client.post("/api/v1/scenarios", {"name": "x"}, **J).status_code == 201
    client.credentials()  # drop X-VP-Client: what a forged cross-site form post would look like
    assert client.post("/api/v1/scenarios", {"name": "y"}, **J).status_code == 403
    assert client.get("/api/v1/scenarios").status_code == 200  # reads need nothing special


# --- the assistant log ---------------------------------------------------------------------------------
def test_admins_can_read_the_assistant_log_but_nobody_else(login, users, company_a, company_b):
    build_worked_example(company_a)
    planner = login(users["a_planner"])
    planner.post("/api/v1/assistant/ask", {"question": "which lines are at risk?"}, **J)
    admin = login(users["a_admin"])
    body = admin.get("/api/v1/assistant/logs").json()
    assert body["count"] == 1 and body["results"][0]["username"] == "a_planner"
    assert body["results"][0]["prompt"] == "which lines are at risk?" and body["results"][0][
        "tools"
    ] == ["get_at_risk_lines"]
    assert login(users["a_planner"]).get("/api/v1/assistant/logs").status_code == 403
    assert login(users["a_viewer"]).get("/api/v1/assistant/logs").status_code == 403
    assert login(users["b_admin"]).get("/api/v1/assistant/logs").json()["count"] == 0
    assert AssistantLog.objects.count() == 1


# --- query counts must not grow with the rows -----------------------------------------------------------
def count_queries(client, path: str) -> int:
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(path)
    assert response.status_code == 200, (path, response.content[:200])
    return len(ctx)


def grow(company, customer, part, n: int) -> None:
    resource_type = Resource.objects.filter(company=company).first().resource_type
    for i in range(n):
        c = Customer.objects.create(
            company=company, code=f"G{i}-{n}-{company.pk}", name=f"Grown {i}", priority="B"
        )
        p = Part.objects.create(
            company=company,
            part_number=f"GP{i}-{n}-{company.pk}",
            name="Grown part",
            casting_weight_kg=5,
            pouring_weight_per_mould_kg=10,
        )
        PartCustomer.objects.create(company=company, part=p, customer=c, is_default=True)
        ScheduleLine.objects.create(
            company=company,
            customer=c,
            part=p,
            dispatch_qty=10,
            internal_dispatch_date=TODAY + timedelta(days=5 + i),
        )
        Resource.objects.create(
            company=company,
            code=f"GR{i}-{n}",
            name="Grown resource",
            resource_type=resource_type,
            efficiency_pct=85,
            rate_per_hour=10,
        )


LISTS = [
    "/api/v1/schedule-lines?page_size=500",
    "/api/v1/parts?page_size=500",
    "/api/v1/customers?page_size=500",
    "/api/v1/resources?page_size=500",
    "/api/v1/plans",
    "/api/v1/scenarios",
    "/api/v1/insights",
    "/api/v1/audit-log?page_size=500",
    "/api/v1/shifts",
    "/api/v1/capacity-adjustments",
    "/api/v1/downtimes",
]


@pytest.mark.parametrize("path", LISTS)
def test_list_queries_do_not_grow_with_rows(login, users, company_a, path):
    built = build_worked_example(company_a)
    client = login(users["a_admin"])  # an admin may read every one of these lists
    client.post("/api/v1/plans", {}, **J)
    client.post("/api/v1/scenarios", {"name": "A"}, **J)
    grow(company_a, built["customer"] if "customer" in built else None, built["part"], 3)
    few = count_queries(client, path)
    grow(company_a, None, built["part"], 30)
    many = count_queries(client, path)
    assert many <= few + 2, f"{path}: {few} queries for a few rows, {many} for many"


def test_plan_line_lists_and_detail_do_not_grow(login, users, company_a):
    built = build_worked_example(company_a)
    customer = Customer.objects.get(company=company_a, code="CUST-01")
    client = login(users["a_planner"])

    def add(n):
        for i in range(n):
            ScheduleLine.objects.create(
                company=company_a,
                customer=customer,
                part=built["part"],
                dispatch_qty=20,
                internal_dispatch_date=TODAY + timedelta(days=10 + i),
            )

    add(3)
    plan = client.post("/api/v1/plans", {}, **J).json()["id"]
    few = count_queries(client, f"/api/v1/plans/{plan}/lines?page_size=500")
    add(40)
    plan = client.post("/api/v1/plans", {}, **J).json()["id"]
    many = count_queries(client, f"/api/v1/plans/{plan}/lines?page_size=500")
    assert many <= few + 2, (few, many)
    for sub in ("load", "bottlenecks", "gantt?by=resource", "gantt?by=line", f"day?date={TODAY}"):
        assert count_queries(client, f"/api/v1/plans/{plan}/{sub}") <= 20, sub
