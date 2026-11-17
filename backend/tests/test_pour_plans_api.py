"""The mould plan and melt plan endpoints, their Excel export, the day view and the planning config."""

import io
from datetime import date

import pytest
from openpyxl import load_workbook

from apps.masters.models import Customer
from apps.scheduler.models import ScheduleLine
from seeds.worked_example import build_worked_example

J = {"format": "json"}
TODAY = date(2026, 11, 2)  # a Monday
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
WINDOW = "from=2026-11-02&to=2026-11-14"


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("django.utils.timezone.localdate", lambda *a, **k: TODAY)


@pytest.fixture
def example(company_a, phase_defaults):
    built = build_worked_example(company_a)
    customer = Customer.objects.get(company=company_a, code="CUST-01")
    ScheduleLine.objects.create(
        company=company_a, customer=customer, part=built["part"], dispatch_qty=600,
        internal_dispatch_date=date(2026, 11, 20),
    )  # fmt: skip
    return built


@pytest.fixture
def plan(login, users, example):
    response = login(users["a_planner"]).post("/api/v1/plans", {}, **J)
    assert response.status_code == 201
    return response.json()


def test_the_mould_plan_lists_moulds_per_day_shift_and_machine(login, users, plan):
    data = login(users["a_viewer"]).get(f"/api/v1/plans/{plan['id']}/mould-plan?{WINDOW}").json()
    moulds = castings = 0.0
    for day in data["days"]:
        for shift in day["shifts"]:
            for machine in shift["machines"]:
                assert machine["code"] == "LINE-A"
                assert 0 < machine["used_pct"] <= 100 and machine["capacity_minutes"] > 0
                for item in machine["items"]:
                    assert item["part_number"] == "H-120" and item["customer_code"] == "CUST-01"
                    moulds += item["moulds"]
                    castings += item["castings"]
    assert moulds == pytest.approx(315, abs=1)  # 630 pieces to pour / 2 cavities
    assert castings == pytest.approx(630, abs=2)
    assert data["warnings"] == []


def test_an_order_that_cannot_make_its_date_is_a_warning(login, users, example, company_a):
    customer = Customer.objects.get(company=company_a, code="CUST-01")
    ScheduleLine.objects.create(
        company=company_a, customer=customer, part=example["part"], dispatch_qty=9000,
        internal_dispatch_date=date(2026, 11, 4),
    )  # fmt: skip
    client = login(users["a_planner"])
    plan = client.post("/api/v1/plans", {}, **J).json()
    data = client.get(f"/api/v1/plans/{plan['id']}/mould-plan?{WINDOW}").json()
    assert data["warnings"] and "late" in data["warnings"][0]["text"]
    assert data["warnings"][0]["status"] in ("at_risk", "unscheduled")


def test_the_melt_plan_lists_heats_with_grade_kg_fill_and_pours(login, users, plan):
    data = login(users["a_viewer"]).get(f"/api/v1/plans/{plan['id']}/melt-plan?{WINDOW}").json()
    assert data["enabled"] and data["summary"]["heats"] >= 1
    kg = 0.0
    for day in data["days"]:
        assert day["furnaces"] and all(0 < f["used_pct"] <= 100 for f in day["furnaces"])
        for heat in day["heats"]:
            assert heat["grade"] == "GG25" and heat["furnace"] in ("F1", None)
            assert heat["kg"] <= heat["capacity_kg"] and heat["pours"][0]["part_number"] == "H-120"
            assert (heat["furnace"] is None) == any(
                "No furnace capacity" in w for w in heat["warnings"]
            )
            kg += heat["kg"]
    assert kg == pytest.approx(315 * 60, abs=1)


def test_the_melt_plan_is_off_when_the_engine_plans_melting(login, users, company_a, settings):
    build_worked_example(company_a)
    settings.MELTING_PLAN_MODE = "engine"
    client = login(users["a_planner"])
    plan = client.post("/api/v1/plans", {}, **J).json()
    data = client.get(f"/api/v1/plans/{plan['id']}/melt-plan?{WINDOW}").json()
    assert data["enabled"] is False and data["days"] == []


def test_the_day_view_shows_melting_as_heats(login, users, plan):
    data = login(users["a_viewer"]).get(f"/api/v1/plans/{plan['id']}/day?date=2026-11-02").json()
    work = {w["op_code"]: w for w in data["work"]}
    assert "moulding" in work and work["melting"]["qty"] > 0 and work["melting"]["lines"] == 1


@pytest.mark.parametrize("kind, title", [("mould_plan", "Mould plan"), ("melt_plan", "Melt plan")])
def test_each_plan_exports_to_excel(login, users, plan, kind, title):
    response = login(users["a_viewer"]).get(
        f"/api/v1/plans/{plan['id']}/export?report={kind}&output=xlsx&{WINDOW}"
    )
    assert response.status_code == 200 and response["Content-Type"] == XLSX
    text = " ".join(
        str(c.value)
        for row in load_workbook(io.BytesIO(response.content)).active.iter_rows()
        for c in row
        if c.value
    )
    assert title in text and "H-120" in text


def test_the_planning_pack_holds_both_plans_in_one_workbook(login, users, plan):
    response = login(users["a_viewer"]).get(
        f"/api/v1/plans/{plan['id']}/export?report=planning_pack&output=xlsx&{WINDOW}"
    )
    text = " ".join(
        str(c.value)
        for row in load_workbook(io.BytesIO(response.content)).active.iter_rows()
        for c in row
        if c.value
    )
    assert "Mould plan" in text and "Melt plan" in text and "H261102-01" in text
    assert "mould-and-melt" not in response["Content-Disposition"]
    assert "planning-pack" in response["Content-Disposition"]


def test_the_shift_plan_lists_the_heats_for_melting(login, users, plan):
    response = login(users["a_viewer"]).get(
        f"/api/v1/plans/{plan['id']}/export?report=day_plan&department=melting&date=2026-11-02&output=xlsx"
    )
    text = " ".join(
        str(c.value)
        for row in load_workbook(io.BytesIO(response.content)).active.iter_rows()
        for c in row
        if c.value
    )
    assert response.status_code == 200 and "H261102-01" in text


def test_a_window_longer_than_62_days_is_refused(login, users, plan):
    response = login(users["a_viewer"]).get(
        f"/api/v1/plans/{plan['id']}/mould-plan?from=2026-11-02&to=2027-03-01"
    )
    assert response.status_code == 400


def test_the_planning_config_tells_the_screens_what_is_planned(login, users, example):
    data = login(users["a_viewer"]).get("/api/v1/planning-config").json()
    assert data["planned_operations"] == ["moulding", "melting"]
    assert data["melting_plan_mode"] == "grade_heats" and data["min_heat_fill_pct"] == 70
    assert (
        data["post_pour_days"] == 0 and data["max_lead_days"] is None
    )  # the test company's own values


def test_the_insights_read_the_heats_and_report_a_furnace_shortfall(login, users, plan):
    cards = login(users["a_viewer"]).get("/api/v1/insights").json()["results"]
    melting = {c["key"]: c for c in cards if c["type"] == "melting"}
    assert (
        "melting:tonnes" in melting and "melting:shortfall" in melting
    )  # the line outruns one furnace
    assert melting["melting:shortfall"]["numbers"]["heats"] >= 1
    tonnes = melting["melting:tonnes"]["numbers"]["total_tonnes"]
    assert tonnes == pytest.approx(18.9, abs=0.05)


def test_an_order_with_a_heat_no_furnace_can_take_is_at_risk(login, users, plan):
    client = login(users["a_planner"])
    line = ScheduleLine.objects.get()
    data = client.get(f"/api/v1/schedule-lines/{line.pk}").json()
    assert data["plan_state"] == "at_risk"
    assert any("No furnace room" in reason for reason in data["plan_reasons"])
