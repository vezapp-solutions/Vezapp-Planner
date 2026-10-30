"""Sweeps over every API route: nobody anonymous gets in, viewers never write, and one company
never sees another's rows. New routes are covered automatically, so a forgotten permission class or
tenant filter fails here."""

import re
from datetime import date

import pytest
from django.core.cache import cache
from django.urls import get_resolver

from apps.masters.models import Customer
from apps.scheduler.models import ScheduleLine
from seeds.worked_example import build_worked_example

J = {"format": "json"}
TODAY = date(2026, 11, 2)

# Routes that are open on purpose.
OPEN = {"api/v1/health", "api/v1/auth/login", "api/v1/auth/refresh", "api/v1/auth/logout"}
# Writes every signed-in role may make: asking the read-only assistant.
ANYONE_MAY_POST = {
    "api/v1/assistant/ask",
    "api/v1/assistant/explain",
    "api/v1/assistant/monthly-summary",
}


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("django.utils.timezone.localdate", lambda *a, **k: TODAY)
    cache.clear()


def _walk(patterns, prefix=""):
    for p in patterns:
        if hasattr(p, "url_patterns"):
            yield from _walk(p.url_patterns, prefix + str(p.pattern))
        else:
            yield prefix + str(p.pattern)


def _clean(route: str, values: dict[str, str] | None = None) -> str:
    """A concrete URL path from a route: every placeholder becomes 1, or the value given for it."""
    values = values or {}
    route = route.replace("^", "").replace("$", "").replace("\\.", ".")
    route = re.sub(r"\(\?P<(\w+)>[^)]*\)", lambda m: values.get(m.group(1), "1"), route)
    route = re.sub(r"<(?:\w+:)?(\w+)>", lambda m: values.get(m.group(1), "1"), route)
    return "/" + route.strip("/")


ROUTES = sorted({r for r in _walk(get_resolver().url_patterns) if r.startswith("api/v1/")})


def _path(route):
    return _clean(route)


def _key(route):
    return _clean(route).strip("/")


def test_the_sweep_sees_the_routes_it_should():
    keys = {_key(r) for r in ROUTES}
    assert len(ROUTES) > 60
    assert {
        "api/v1/plans",
        "api/v1/scenarios",
        "api/v1/insights",
        "api/v1/assistant/ask",
        "api/v1/data-health",
        "api/v1/users",
    } <= keys


@pytest.mark.parametrize("route", ROUTES, ids=_key)
def test_anonymous_callers_get_nothing(anon_client, route):
    if _key(route) in OPEN:
        return
    for method in ("get", "post", "patch", "delete"):
        response = getattr(anon_client, method)(
            _path(route),
            **({"data": {}, "format": "json"} if method != "get" and method != "delete" else {}),
        )
        assert response.status_code in (401, 403), (
            f"{method.upper()} {_path(route)} gave {response.status_code}"
        )


@pytest.mark.parametrize("route", ROUTES, ids=_key)
def test_viewers_can_never_write(login, users, route):
    if _key(route) in OPEN | ANYONE_MAY_POST:
        return
    client = login(users["a_viewer"])
    for method in ("post", "put", "patch", "delete"):
        kwargs = {} if method == "delete" else {"data": {}, "format": "json"}
        response = getattr(client, method)(_path(route), **kwargs)
        assert response.status_code in (403, 405), (
            f"{method.upper()} {_path(route)} gave {response.status_code}"
        )


@pytest.fixture
def two_companies(login, users, company_a, company_b):
    """Both companies get the same plant, lines, a plan, a scenario and insights."""
    clients = {"a": login(users["a_admin"]), "b": login(users["b_admin"])}
    for company, client in ((company_a, clients["a"]), (company_b, clients["b"])):
        built = build_worked_example(company)
        customer = Customer.objects.get(company=company, code="CUST-01")
        ScheduleLine.objects.create(
            company=company,
            customer=customer,
            part=built["part"],
            dispatch_qty=300,
            internal_dispatch_date=date(2026, 11, 20),
        )
        ScheduleLine.objects.create(
            company=company,
            customer=customer,
            part=built["part"],
            dispatch_qty=1500,
            internal_dispatch_date=date(2026, 11, 6),
        )
        assert client.post("/api/v1/plans", {}, **J).status_code == 201
        scenario = client.post(
            "/api/v1/scenarios", {"name": f"Scenario of {company.pk}"}, **J
        ).json()
        client.post(
            f"/api/v1/scenarios/{scenario['id']}/changes",
            {
                "kind": "change_qty",
                "params": {
                    "line": ScheduleLine.objects.filter(company=company).first().pk,
                    "qty": 50,
                },
            },
            **J,
        )
        client.post("/api/v1/assistant/ask", {"question": "which lines are at risk?"}, **J)
    return clients


def _items(response):
    is_json = response.status_code == 200 and response["Content-Type"].startswith(
        "application/json"
    )
    body = response.json() if is_json else None
    items = body.get("results") if isinstance(body, dict) else body
    if (
        isinstance(items, list)
        and items
        and all(isinstance(i, dict) and isinstance(i.get("id"), int) for i in items)
    ):
        return items
    return None


LIST_ROUTES = [r for r in ROUTES if "(?P<" not in r and "<" not in r and _key(r) not in OPEN]


@pytest.mark.parametrize("route", LIST_ROUTES, ids=_key)
def test_one_company_never_sees_the_others_rows(two_companies, route):
    a, b = two_companies["a"], two_companies["b"]
    path = _path(route) + "?page_size=500"
    items_a, items_b = _items(a.get(path)), _items(b.get(path))
    if items_a is None or items_b is None:
        return  # not a list of records (a computed view, or empty)
    ids_a, ids_b = {i["id"] for i in items_a}, {i["id"] for i in items_b}
    master_rows = {
        "api/v1/shifts",
        "api/v1/operation-types",
        "api/v1/resource-types",
    }  # each company has its own copies
    assert ids_a.isdisjoint(ids_b), f"{path}: both companies see rows {sorted(ids_a & ids_b)}"
    # And a row of A is a 404 for B (or refused), never its data.
    detail = _path(route).rstrip("/")
    for item in items_a[:3]:
        if a.get(f"{detail}/{item['id']}").status_code != 200:
            continue
        response = b.get(f"{detail}/{item['id']}")
        assert response.status_code in (403, 404), (
            f"{detail}/{item['id']} gave {response.status_code} to the other company"
        )
    assert _key(route) not in master_rows or ids_a


def test_other_companies_cannot_reach_a_plans_sub_resources(two_companies):
    a, b = two_companies["a"], two_companies["b"]
    plan_id = a.get("/api/v1/plans").json()["results"][0]["id"]
    line_id = a.get(f"/api/v1/plans/{plan_id}/lines").json()["results"][0]["id"]
    for route in ROUTES:
        if "(?P<pk>" not in route or "plans/" not in route or _key(route) in OPEN:
            continue
        path = _clean(route, {"pk": str(plan_id), "line_id": str(line_id)})
        if a.get(path).status_code != 200:
            continue  # a POST action, or one that needs parameters
        assert b.get(path).status_code in (403, 404), path


def test_scenario_and_insight_routes_are_closed_to_the_other_company(two_companies):
    a, b = two_companies["a"], two_companies["b"]
    scenario = a.get("/api/v1/scenarios").json()["results"][0]["id"]
    card = a.get("/api/v1/insights").json()["results"][0]["id"]
    for path in (f"/api/v1/scenarios/{scenario}", f"/api/v1/insights/{card}"):
        assert b.get(path).status_code == 404
    for path in (
        f"/api/v1/scenarios/{scenario}/run",
        f"/api/v1/scenarios/{scenario}/apply",
        f"/api/v1/scenarios/{scenario}/changes",
        f"/api/v1/insights/{card}/dry-run",
    ):
        assert b.post(path, {}, **J).status_code == 404, path


def test_the_assistant_log_belongs_to_one_company(two_companies):
    from apps.assistant.models import AssistantLog

    assert {log.company_id for log in AssistantLog.objects.filter(username="a_admin")} != {
        log.company_id for log in AssistantLog.objects.filter(username="b_admin")
    }
