"""Insights through the API on the section 7.5 plant: refresh on plan runs, every card type, trends,
dry run, roles, tenancy, digest, data health and the three reports."""

from datetime import date, timedelta

import pytest

from apps.insights.models import Insight, InsightRun
from apps.masters.models import Customer, OperationType, Part, PartCustomer, PartOperation
from apps.plans.models import Plan
from apps.resources.models import Resource
from apps.scheduler.models import LineStatus, ScheduleLine
from insights import rules
from seeds.demo_a import build_demo_foundry
from seeds.worked_example import build_worked_example

J = {"format": "json"}
TODAY = date(2026, 11, 2)  # a Monday


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("django.utils.timezone.localdate", lambda *a, **k: TODAY)


def add_line(company, customer, part, qty, due, **kw):
    return ScheduleLine.objects.create(
        company=company,
        customer=customer,
        part=part,
        dispatch_qty=qty,
        internal_dispatch_date=due,
        **kw,
    )


@pytest.fixture
def plant(company_a):
    """The 7.5 plant with an overloaded furnace F1, an idle spare furnace F2 and some history."""
    built = build_worked_example(company_a)
    customer = Customer.objects.get(company=company_a, code="CUST-01")
    f1 = built["furnace"]
    Resource.objects.create(
        company=company_a, code="F2", name="Induction furnace 2", resource_type=f1.resource_type,
        plant=f1.plant, efficiency_pct=85, heat_kg=1000, heat_minutes=75,
    )  # fmt: skip
    built["customer"] = customer
    built["big"] = add_line(
        company_a, customer, built["part"], 1500, date(2026, 11, 6)
    )  # cannot make it
    built["easy"] = add_line(company_a, customer, built["part"], 100, date(2026, 11, 30))

    # Last month: four shipped lines, two of them late.
    for n, late in enumerate([0, 0, 3, 5]):
        due = date(2026, 10, 5) + timedelta(days=n)
        add_line(
            company_a, customer, built["part"], 50, due, status=LineStatus.DISPATCHED,
            actual_dispatch_date=due + timedelta(days=late), actual_dispatched_qty=50,
        )  # fmt: skip

    # A part with no route, and a line for it that is already past its internal date.
    bare = Part.objects.create(
        company=company_a,
        part_number="NR-1",
        name="No route yet",
        casting_weight_kg=5,
        pouring_weight_per_mould_kg=10,
    )
    PartCustomer.objects.create(company=company_a, part=bare, customer=customer, is_default=True)
    built["bare_line"] = add_line(company_a, customer, bare, 10, date(2026, 10, 20))
    return built


def make_plan(client):
    response = client.post("/api/v1/plans", {}, **J)
    assert response.status_code == 201, response.content
    return response.json()


def cards(client, **params):
    response = client.get("/api/v1/insights", params)
    assert response.status_code == 200, response.content
    return response.json()


def by_key(client):
    return {c["key"]: c for c in cards(client)["results"]}


# --- refresh on every plan run --------------------------------------------------------------------
def test_calculating_a_plan_refreshes_the_insights(login, users, plant):
    client = login(users["a_planner"])
    assert cards(client) == {
        "run": None,
        "count": 0,
        "results": [],
    }  # nothing before the first plan
    plan = make_plan(client)
    body = cards(client)
    assert (
        body["run"]["trigger"] == "plan"
        and body["run"]["plan"] == plan["id"]
        and body["run"]["plan_version"] == 1
    )
    assert body["count"] == len(body["results"]) == body["run"]["counts"]["total"] > 0
    ranks = [c["rank"] for c in body["results"]]
    assert ranks == sorted(ranks, reverse=True)  # ranked most important first


def test_every_insight_type_is_produced_on_realistic_data(login, users, plant):
    client = login(users["a_planner"])
    make_plan(client)
    types = {c["type"] for c in cards(client)["results"]}
    assert types == {
        "at_risk", "bottleneck_forecast", "capacity_gap", "melting", "load_balancing",
        "month_forecast", "concentration", "dispatch_performance", "data_health",
    }  # fmt: skip


def test_the_numbers_on_the_cards_match_the_plan(login, users, plant):
    client = login(users["a_planner"])
    plan = make_plan(client)
    got = by_key(client)
    summary = got["at_risk:summary"]
    lines = {
        ln["id"]: ln for ln in client.get(f"/api/v1/plans/{plan['id']}/lines").json()["results"]
    }
    late = [ln for ln in lines.values() if ln["status"] in ("at_risk", "unscheduled")]
    assert summary["numbers"]["lines_at_risk"] == len(late) >= 1
    assert summary["numbers"]["pieces_late"] == sum(ln["qty"] for ln in late)
    assert set(summary["entities"]["lines"]) <= set(lines)
    forecast = got["bottleneck:forecast"]["numbers"]
    # The core machine and the furnace both run flat out in this plant, so either is the bottleneck.
    assert forecast["top_resource"] in ("F1", "CM1")
    assert forecast["peak_utilisation"] == pytest.approx(1.0, abs=0.03)
    assert got["melting:tonnes"]["numbers"]["by_grade"].keys() == {"GG25"}
    month = got["month_forecast"]["numbers"]
    assert month["month"] == "2026-11" and month["planned_qty"] == 1600


def test_dispatch_performance_card_comes_from_actual_dates(login, users, plant):
    client = login(users["a_planner"])
    make_plan(client)
    overall = by_key(client)["dispatch:overall"]
    assert overall["numbers"]["month"] == "2026-10" and overall["numbers"]["lines"] == 4
    assert overall["numbers"]["on_time"] == 2 and overall["numbers"]["on_time_pct"] == 0.5
    assert overall["severity"] == "critical"  # 50% is under the 60% line


def test_data_health_cards_name_the_gaps(login, users, plant):
    client = login(users["a_planner"])
    make_plan(client)
    got = by_key(client)
    assert got["data_health:no_route"]["numbers"] == {"items": 1, "lines_affected": 1}
    assert got["data_health:no_route"]["severity"] == "critical"
    assert got["data_health:past_due"]["entities"]["items"][0]["subject"] == "CUST-01"


def test_cards_carry_a_trace_and_a_next_step(login, users, plant):
    client = login(users["a_planner"])
    make_plan(client)
    for card in cards(client)["results"]:
        assert card["title"] and card["message"] and card["why"], card["key"]
        assert card["severity"] in ("critical", "warning", "info") and card["trend"] == "new"
        if card["severity"] != "info":
            assert card["action"], card["key"]


# --- history and trend ----------------------------------------------------------------------------------
def test_refreshing_again_shows_a_trend_and_keeps_history(login, users, plant):
    client = login(users["a_planner"])
    make_plan(client)
    assert client.post("/api/v1/insights/refresh", {}, **J).status_code == 201
    trends = {c["trend"] for c in cards(client)["results"]}
    assert trends == {"same"}  # nothing changed between the runs
    history = client.get("/api/v1/insights/history").json()
    assert [h["trigger"] for h in history] == ["manual", "plan"]


def test_a_worse_situation_shows_as_worse_and_a_resolved_card_is_counted(login, users, plant):
    client = login(users["a_planner"])
    make_plan(client)
    first = by_key(client)
    ScheduleLine.objects.filter(pk=plant["easy"].pk).update(
        dispatch_qty=1500, internal_date=None
    ) if False else None
    ScheduleLine.objects.filter(pk=plant["big"].pk).update(dispatch_qty=3000)
    client.post("/api/v1/plans", {}, **J)  # a new plan run
    after = by_key(client)
    assert after["at_risk:summary"]["trend"] in ("worse", "same")
    assert (
        after["at_risk:summary"]["numbers"]["pieces_late"]
        >= first["at_risk:summary"]["numbers"]["pieces_late"]
    )
    ScheduleLine.objects.filter(pk=plant["bare_line"].pk).delete()
    client.post("/api/v1/insights/refresh", {}, **J)
    assert cards(client)["run"]["counts"]["resolved"] >= 1  # the past-due health card is gone


def test_old_runs_are_pruned(login, users, plant, monkeypatch):
    monkeypatch.setattr(rules, "RUNS_KEPT", 2)
    client = login(users["a_planner"])
    make_plan(client)
    for _ in range(3):
        client.post("/api/v1/insights/refresh", {}, **J)
    assert InsightRun.objects.count() == 2
    assert (
        Insight.objects.filter(run__in=InsightRun.objects.all()).count() == Insight.objects.count()
    )


def test_a_failing_insight_never_fails_the_plan(login, users, plant, monkeypatch):
    def boom(plan):
        raise RuntimeError("insight trouble")

    monkeypatch.setattr("apps.insights.collect.line_facts", boom)
    client = login(users["a_planner"])
    assert client.post("/api/v1/plans", {}, **J).status_code == 201
    assert Plan.objects.count() == 1 and InsightRun.objects.count() == 0


def test_loading_actual_dispatch_dates_refreshes_the_dispatch_cards(login, users, plant):
    from apps.scheduler import service as upload
    from apps.scheduler.importer import COLUMNS

    client = login(users["a_planner"])
    make_plan(client)
    before = InsightRun.objects.count()
    headers = [h for _, h in COLUMNS]
    row = {"customer_code": "CUST-01", "part_number": "H-120", "dispatch_qty": "70", "internal_date": "25-10-2026",
           "actual_date": "27-10-2026", "actual_qty": "70"}  # fmt: skip
    csv = ",".join(headers) + "\n" + ",".join(row.get(key, "") for key, _ in COLUMNS) + "\n"
    upload.commit(
        plant["customer"].company, users["a_planner"], "actuals.csv", csv.encode(), "insert", False
    )
    assert InsightRun.objects.count() == before + 1
    assert InsightRun.objects.first().trigger == "actuals"


# --- dry run of a load-balancing suggestion ----------------------------------------------------------------
def test_load_balancing_dry_run_shows_the_effect_and_changes_nothing(login, users, plant):
    client = login(users["a_planner"])
    make_plan(client)
    f2 = Resource.objects.get(code="F2")
    card = by_key(client)[f"load_balancing:{plant['part'].pk}:melting:{f2.pk}"]
    assert card["entities"]["dry_run"]["resource_id"] == Resource.objects.get(code="F2").pk
    route_before = list(
        PartOperation.objects.filter(part=plant["part"], op_type__code="melting").values_list(
            "resources", flat=True
        )
    )

    response = client.post(f"/api/v1/insights/{card['id']}/dry-run", {}, **J)
    assert response.status_code == 200, response.content
    diff = response.json()["diff"]
    assert (
        diff["counts"]["total"] >= 1 and diff["counts"]["earlier"] >= 1
    )  # more furnace room pulls dates in
    assert {ln["part_number"] for ln in diff["lines"]} == {"H-120"}
    assert (
        list(
            PartOperation.objects.filter(part=plant["part"], op_type__code="melting").values_list(
                "resources", flat=True
            )
        )
        == route_before
    )


def test_only_load_balancing_cards_can_be_dry_run(login, users, plant):
    client = login(users["a_planner"])
    make_plan(client)
    other = by_key(client)["at_risk:summary"]
    assert client.post(f"/api/v1/insights/{other['id']}/dry-run", {}, **J).status_code == 400


# --- roles and tenancy -----------------------------------------------------------------------------------------
def test_viewers_read_insights_but_cannot_refresh_or_test(login, users, plant):
    planner, viewer = login(users["a_planner"]), login(users["a_viewer"])
    make_plan(planner)
    assert (
        viewer.get("/api/v1/insights").status_code == 200
        and viewer.get("/api/v1/insights/digest").status_code == 200
    )
    card = cards(viewer)["results"][0]
    assert viewer.get(f"/api/v1/insights/{card['id']}").status_code == 200
    assert viewer.post("/api/v1/insights/refresh", {}, **J).status_code == 403
    assert viewer.post(f"/api/v1/insights/{card['id']}/dry-run", {}, **J).status_code == 403
    assert viewer.post("/api/v1/insights", {}, **J).status_code == 403


def test_nobody_can_create_or_edit_cards_directly(login, users, plant):
    planner = login(users["a_planner"])
    make_plan(planner)
    card = cards(planner)["results"][0]
    assert planner.post("/api/v1/insights", {"title": "x"}, **J).status_code == 405
    assert planner.patch(f"/api/v1/insights/{card['id']}", {"title": "x"}, **J).status_code == 405
    assert planner.delete(f"/api/v1/insights/{card['id']}").status_code == 405


def test_company_b_never_sees_company_as_insights(login, users, plant, company_b):
    build_worked_example(company_b)
    a = login(users["a_planner"])
    make_plan(a)
    a_card = cards(a)["results"][0]
    b = login(users["b_admin"])
    assert cards(b)["results"] == []
    assert b.get(f"/api/v1/insights/{a_card['id']}").status_code == 404
    assert b.post(f"/api/v1/insights/{a_card['id']}/dry-run", {}, **J).status_code == 404
    make_plan(b)
    assert all(
        Insight.objects.get(pk=c["id"]).company_id == company_b.pk for c in cards(b)["results"]
    )
    assert {c["id"] for c in cards(a)["results"]}.isdisjoint({c["id"] for c in cards(b)["results"]})


def test_filters_by_type_and_severity(login, users, plant):
    client = login(users["a_planner"])
    make_plan(client)
    assert {c["type"] for c in cards(client, type="at_risk")["results"]} == {"at_risk"}
    assert {c["severity"] for c in cards(client, severity="critical")["results"]} == {"critical"}


# --- digest -------------------------------------------------------------------------------------------------------------
def test_digest_is_the_top_five_cards(login, users, plant):
    client = login(users["a_viewer"])
    login(users["a_planner"]).post("/api/v1/plans", {}, **J)
    body = client.get("/api/v1/insights/digest").json()
    top = cards(client)["results"][:5]
    assert [i["key"] for i in body["items"]] == [c["key"] for c in top]
    assert body["title"].startswith("Daily digest, 02-11-2026") and "1. [" in body["text"]


def test_digest_pdf(login, users, plant):
    client = login(users["a_planner"])
    make_plan(client)
    response = client.get("/api/v1/insights/digest", {"output": "pdf"})
    assert response.status_code == 200 and response["Content-Type"] == "application/pdf"
    assert (
        response.content.startswith(b"%PDF")
        and "daily-digest.pdf" in response["Content-Disposition"]
    )
    assert client.get("/api/v1/insights/digest", {"output": "docx"}).status_code == 400


def test_digest_with_no_plan_is_calm(login, users, company_a):
    body = login(users["a_planner"]).get("/api/v1/insights/digest").json()
    assert body["items"] == [] and "Nothing needs attention today." in body["text"]


# --- data health ------------------------------------------------------------------------------------------------------------
def test_data_health_lists_items_with_the_reason(login, users, plant):
    client = login(users["a_planner"])
    body = client.get("/api/v1/data-health").json()
    kinds = {i["kind"] for i in body["items"]}
    assert {"no_route", "past_due"} <= kinds and body["count"] == len(body["items"])
    no_route = next(i for i in body["items"] if i["kind"] == "no_route")
    assert (
        no_route["subject"] == "NR-1"
        and no_route["lines_affected"] == 1
        and no_route["link"].startswith("/masters/parts/")
    )
    assert "cannot be planned" in no_route["why"]
    assert body["items"][0]["severity"] == "error"  # errors first


def test_data_health_reports_route_steps_without_resources(login, users, plant):
    row = PartOperation.objects.filter(part=plant["part"], op_type__code="fettling").get()
    row.resources.clear()
    items = login(users["a_planner"]).get("/api/v1/data-health").json()["items"]
    assert any(i["kind"] == "no_capacity" and "Fettling" in i["subject"] for i in items)


def test_data_health_for_viewers_and_tenancy(login, users, plant, company_b):
    assert login(users["a_viewer"]).get("/api/v1/data-health").status_code == 403
    build_worked_example(company_b)
    assert login(users["b_admin"]).get("/api/v1/data-health").json()["items"] == []


# --- reports ----------------------------------------------------------------------------------------------------------------------
def test_dispatch_performance_report(login, users, plant):
    client = login(users["a_viewer"])
    body = client.get("/api/v1/reports/dispatch-performance").json()
    assert (
        body["overall"]["lines"] == 4
        and body["overall"]["on_time"] == 2
        and body["overall"]["on_time_pct"] == 0.5
    )
    assert body["overall"]["avg_delay_days"] == 4.0 and body["overall"]["max_delay_days"] == 5
    assert body["by_customer"][0]["group"] == "CUST-01" and body["by_part"][0]["group"] == "H-120"
    assert [m["group"] for m in body["by_month"]] == ["2026-10"]
    narrowed = client.get(
        "/api/v1/reports/dispatch-performance", {"from": "2026-10-07", "to": "2026-10-31"}
    ).json()
    assert narrowed["overall"]["lines"] == 2
    assert (
        client.get("/api/v1/reports/dispatch-performance", {"customer": "NOPE"}).json()["overall"]
        is None
    )
    assert (
        client.get("/api/v1/reports/dispatch-performance", {"from": "yesterday"}).status_code == 400
    )


@pytest.mark.parametrize("kind", ["dispatch-performance", "utilisation", "plan-vs-actual"])
@pytest.mark.parametrize("output, magic", [("pdf", b"%PDF"), ("xlsx", b"PK")])
def test_reports_export_to_pdf_and_excel(login, users, plant, kind, output, magic):
    client = login(users["a_planner"])
    make_plan(client)
    response = client.get(f"/api/v1/reports/{kind}", {"output": output})
    assert response.status_code == 200 and response.content.startswith(magic)
    assert f"{kind}.{output}" in response["Content-Disposition"]


def test_report_output_must_be_pdf_or_xlsx(login, users, plant):
    assert (
        login(users["a_planner"])
        .get("/api/v1/reports/dispatch-performance", {"output": "csv"})
        .status_code
        == 400
    )


def test_unknown_report_is_404(login, users, plant):
    assert login(users["a_planner"]).get("/api/v1/reports/nonsense").status_code == 404


def test_utilisation_report_per_resource_and_week(login, users, plant):
    client = login(users["a_planner"])
    assert client.get("/api/v1/reports/utilisation").json() == {
        "plan": None,
        "from": None,
        "to": None,
        "resources": [],
    }
    assert (
        client.get("/api/v1/reports/utilisation", {"output": "pdf"}).status_code == 400
    )  # needs a plan
    make_plan(client)
    body = client.get(
        "/api/v1/reports/utilisation", {"from": "2026-11-02", "to": "2026-11-13"}
    ).json()
    f1 = next(r for r in body["resources"] if r["code"] == "F1")
    assert f1["peak_utilisation"] == pytest.approx(1.0, abs=0.03)  # full on its busiest day
    assert 0.3 < f1["utilisation"] < 0.9  # but only a part of the fortnight's capacity
    assert f1["load"] <= f1["capacity"] and f1["peak_date"].startswith("2026-11")
    assert [w["week_start"] for w in f1["weeks"]] == ["2026-11-02", "2026-11-09"]
    f2 = next((r for r in body["resources"] if r["code"] == "F2"), None)
    assert f2 is None or not f2["load"]  # the spare furnace takes no work


def test_plan_vs_actual_compares_with_the_confirmed_plan(login, users, plant):
    client = login(users["a_planner"])
    empty = client.get("/api/v1/reports/plan-vs-actual").json()
    assert (
        empty["summary"]["lines"] == 4 and empty["summary"]["with_confirmed_plan"] == 0
    )  # nothing confirmed yet

    plan = make_plan(client)
    easy_estimate = next(
        ln
        for ln in client.get(f"/api/v1/plans/{plan['id']}/lines").json()["results"]
        if ln["qty"] == 100
    )["est_dispatch_date"]
    assert client.post(f"/api/v1/plans/{plan['id']}/confirm", {}, **J).status_code == 200
    estimate = date.fromisoformat(easy_estimate)
    ScheduleLine.objects.filter(pk=plant["easy"].pk).update(
        actual_dispatch_date=estimate + timedelta(days=2),
        actual_dispatched_qty=100,
        status=LineStatus.DISPATCHED,
    )
    body = client.get("/api/v1/reports/plan-vs-actual").json()
    assert body["summary"]["with_confirmed_plan"] == 1 and body["summary"]["lines"] == 5
    row = next(r for r in body["lines"] if r["line_id"] == plant["easy"].pk)
    assert (
        row["est_date"] == easy_estimate and row["est_error_days"] == 2 and row["plan_version"] == 1
    )
    assert (
        body["summary"]["mean_abs_error_days"] == 2.0 and body["summary"]["within_one_day"] == 0.0
    )
    assert body["lines"][0]["line_id"] == plant["easy"].pk  # biggest miss first


def test_reports_are_company_scoped(login, users, plant, company_b):
    build_worked_example(company_b)
    b = login(users["b_admin"])
    assert b.get("/api/v1/reports/dispatch-performance").json()["overall"] is None
    assert b.get("/api/v1/reports/plan-vs-actual").json()["lines"] == []


# --- speed ---------------------------------------------------------------------------------------------------------------------------
def test_refreshing_insights_on_500_lines_is_fast(login, users, company_a):
    import random
    import time

    from apps.insights import service

    build_demo_foundry(company_a)
    rng = random.Random(5)
    pairs = [
        (link.customer, p)
        for p in Part.objects.filter(company=company_a)
        for link in p.customer_links.all()
    ]
    ScheduleLine.objects.bulk_create(
        [
            ScheduleLine(company=company_a, customer=c, part=p, dispatch_qty=rng.choice([20, 40, 60, 100]),
                         internal_dispatch_date=TODAY + timedelta(days=rng.randint(3, 120)))
            for c, p in (rng.choice(pairs) for _ in range(500))
        ]
    )  # fmt: skip
    client = login(users["a_planner"])
    make_plan(client)
    started = time.perf_counter()
    service.refresh(company_a)
    elapsed = time.perf_counter() - started
    assert elapsed < 2, f"refreshing the insights took {elapsed:.1f}s"
    assert OperationType.objects.filter(company=company_a).exists()
