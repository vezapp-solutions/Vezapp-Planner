"""Orders with stock: balance, Open/Closed, covered by stock, cannot plan, history, staleness, the upload,
and a plan that covers moulding and melting only."""

from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.masters.models import Customer, Grade
from apps.plans.models import Plan, PlanHeat
from apps.scheduler.models import ScheduleLine
from seeds.worked_example import build_worked_example

J = {"format": "json"}
TODAY = date(2026, 11, 2)  # a Monday
CSV = "text/csv"


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("django.utils.timezone.localdate", lambda *a, **k: TODAY)


@pytest.fixture
def example(company_a, phase_defaults):
    return build_worked_example(company_a)


def order(company, part, qty=600, day=date(2026, 11, 20), **extra):
    customer = Customer.objects.get(company=company, code="CUST-01")
    return ScheduleLine.objects.create(
        company=company, customer=customer, part=part, dispatch_qty=qty,
        internal_dispatch_date=day, **extra,
    )  # fmt: skip


def new_plan(client):
    response = client.post("/api/v1/plans", {}, **J)
    assert response.status_code == 201, response.content
    return response.json()


def plan_lines(client, plan):
    return client.get(f"/api/v1/plans/{plan['id']}/lines").json()["results"]


def get_line(client, pk):
    return client.get(f"/api/v1/schedule-lines/{pk}").json()


# --- balance --------------------------------------------------------------------------------------------
def test_balance_is_the_order_less_wip_fg_and_dispatched(login, users, example, company_a):
    obj = order(
        company_a, example["part"], qty=600, wip_qty=100, fg_qty=50, actual_dispatched_qty=50
    )
    data = get_line(login(users["a_planner"]), obj.pk)
    assert (data["wip_qty"], data["fg_qty"], data["actual_dispatched_qty"], data["balance"]) == (
        100,
        50,
        50,
        400,
    )
    assert obj.balance == 400


def test_balance_never_goes_below_zero(company_a, example):
    assert order(company_a, example["part"], qty=100, wip_qty=80, fg_qty=80).balance == 0


def test_a_planner_edits_stock_inline_and_the_balance_follows(login, users, example, company_a):
    client = login(users["a_planner"])
    obj = order(company_a, example["part"], qty=600)
    done = client.patch(
        f"/api/v1/schedule-lines/{obj.pk}", {"wip_qty": 200, "fg_qty": 100}, **J
    ).json()
    assert done["balance"] == 300
    assert client.patch(f"/api/v1/schedule-lines/{obj.pk}", {"wip_qty": -1}, **J).status_code == 400


def test_a_viewer_cannot_change_stock(login, users, example, company_a):
    obj = order(company_a, example["part"])
    response = login(users["a_viewer"]).patch(
        f"/api/v1/schedule-lines/{obj.pk}", {"fg_qty": 5}, **J
    )
    assert response.status_code == 403


def test_a_partial_dispatch_keeps_the_order_open(login, users, example, company_a):
    client = login(users["a_planner"])
    obj = order(company_a, example["part"], qty=600)
    partial = client.patch(
        f"/api/v1/schedule-lines/{obj.pk}",
        {"actual_dispatch_date": "2026-11-01", "actual_dispatched_qty": 200},
        **J,
    ).json()
    assert partial["status"] == "in_progress" and partial["is_open"] and partial["balance"] == 400
    whole = client.patch(
        f"/api/v1/schedule-lines/{obj.pk}", {"actual_dispatched_qty": 600}, **J
    ).json()
    assert whole["balance"] == 0


# --- what is planned ----------------------------------------------------------------------------------------
def test_only_the_balance_is_planned_with_the_rejection_allowance(login, users, example, company_a):
    client = login(users["a_planner"])
    obj = order(company_a, example["part"], qty=600, wip_qty=200, fg_qty=100)  # balance 300
    plan = new_plan(client)
    lines = plan_lines(client, plan)
    assert len(lines) == 1
    detail = client.get(f"/api/v1/plans/{plan['id']}/lines/{lines[0]['id']}").json()
    assert detail["requirement"]["pieces_to_pour"] == 315  # ceil(300 x 1.05)
    assert detail["requirement"]["moulds"] == 158  # ceil(315 / 2 cavities)
    assert get_line(client, obj.pk)["plan_state"] in ("planned", "at_risk")


def test_an_order_covered_by_stock_gets_no_plan(login, users, example, company_a):
    client = login(users["a_planner"])
    covered = order(company_a, example["part"], qty=300, wip_qty=100, fg_qty=200)
    needs = order(company_a, example["part"], qty=100, day=date(2026, 11, 21))
    plan = new_plan(client)
    assert [ln["part_number"] for ln in plan_lines(client, plan)] == ["H-120"]
    assert plan["summary"]["excluded"] == {"covered": 1, "cannot_plan": 0}
    assert get_line(client, covered.pk)["plan_state"] == "covered"
    assert get_line(client, needs.pk)["plan_state"] != "covered"


def test_closed_orders_are_visible_but_never_planned(login, users, example, company_a):
    client = login(users["a_planner"])
    closed = order(company_a, example["part"], status="closed")
    plan = new_plan(client)
    assert plan_lines(client, plan) == []
    data = get_line(client, closed.pk)
    assert data["plan_state"] == "closed" and not data["is_open"]
    listed = client.get("/api/v1/schedule-lines?month=2026-11").json()["results"]
    assert [ln["id"] for ln in listed] == [closed.pk]


def test_missing_master_data_says_what_to_fill_in(login, users, example, company_a):
    client = login(users["a_planner"])
    part = example["part"]
    part.grade = None
    part.save()
    obj = order(company_a, part)
    plan = new_plan(client)
    assert plan_lines(client, plan) == []
    assert plan["summary"]["excluded"]["cannot_plan"] == 1
    data = get_line(client, obj.pk)
    assert data["plan_state"] == "cannot_plan"
    assert any("grade" in reason for reason in data["plan_reasons"])


def test_the_plan_covers_moulding_and_the_melt_plan_follows(login, users, example, company_a):
    client = login(users["a_planner"])
    order(company_a, example["part"], qty=600)
    plan = new_plan(client)
    line = plan_lines(client, plan)[0]
    detail = client.get(f"/api/v1/plans/{plan['id']}/lines/{line['id']}").json()
    assert [o["code"] for o in detail["operations"]] == [
        "moulding"
    ]  # core, knockout, fettling stay out
    heats = PlanHeat.objects.filter(plan_id=plan["id"])
    assert heats.exists()
    assert sum(h.kg for h in heats) == pytest.approx(315 * 60)  # every mould poured: 18,900 kg
    assert plan["summary"]["melt"]["heats"] == heats.count()
    assert Plan.objects.get(pk=plan["id"]).settings_snapshot["planned_operations"] == [
        "melting",
        "moulding",
    ]


# --- re-planning ------------------------------------------------------------------------------------------------
def test_a_stock_edit_makes_the_plan_stale_and_running_it_again_clears_that(
    login, users, example, company_a
):
    client = login(users["a_planner"])
    obj = order(company_a, example["part"])
    plan = new_plan(client)
    assert not plan["stale"]
    client.patch(f"/api/v1/schedule-lines/{obj.pk}", {"fg_qty": 50}, **J)
    stale = client.get(f"/api/v1/plans/{plan['id']}").json()
    assert stale["stale"] and stale["stale_reasons"]
    again = client.post(f"/api/v1/plans/{plan['id']}/recalculate", {}, **J).json()
    assert not again["stale"]


# --- history -----------------------------------------------------------------------------------------------------
def test_stock_changes_keep_who_when_and_old_to_new(login, users, example, company_a):
    client = login(users["a_planner"])
    obj = order(company_a, example["part"])
    client.patch(f"/api/v1/schedule-lines/{obj.pk}", {"wip_qty": 40}, **J)
    client.patch(f"/api/v1/schedule-lines/{obj.pk}", {"wip_qty": 90, "fg_qty": 10}, **J)
    history = client.get(f"/api/v1/schedule-lines/{obj.pk}/history").json()["results"]
    wip = [h for h in history if h["field"] == "WIP stock"]
    assert [(h["old"], h["new"], h["user"]) for h in wip] == [
        (40, 90, "a_planner"),
        (0, 40, "a_planner"),
    ]
    assert any(h["field"] == "FG stock" and h["new"] == 10 for h in history)


def test_history_of_another_companys_order_is_not_reachable(
    login, users, example, company_a, company_b
):
    obj = order(company_a, example["part"])
    assert (
        login(users["b_admin"]).get(f"/api/v1/schedule-lines/{obj.pk}/history").status_code == 404
    )


# --- the upload -------------------------------------------------------------------------------------------------
HEADER = "Part Number,Order Qty,Dispatch Date,Month,Customer Code,Status,WIP Stock,FG Stock,Dispatched Qty\n"


def upload(client, body, path="preview", **extra):
    file = SimpleUploadedFile("orders.csv", body.encode(), content_type=CSV)
    return client.post(f"/api/v1/uploads/{path}", {"file": file, **extra}, format="multipart")


def test_unmatched_parts_are_listed_and_the_other_rows_still_load(login, users, example, company_a):
    client = login(users["a_planner"])
    body = HEADER + (
        "H-120,500,15-05-2027,May,CUST-01,Open,50,0,0\n"
        "H-120,400,10-06-2027,June,,Closed,0,0,400\n"  # customer blank: the part's default
        "NEW-77,300,20-05-2027,May,CUST-01,Open,0,0,0\n"
        "NEW-77,100,25-05-2027,May,CUST-01,Open,0,0,0\n"
    )
    preview = upload(client, body).json()
    assert preview["summary"]["error"] == 2 and preview["summary"]["insert"] == 2
    assert preview["unmatched_parts"] == [
        {"part_number": "NEW-77", "rows": [4, 5], "qty": 400, "customer_code": "CUST-01"}
    ]

    blocked = upload(client, body, "commit")
    assert blocked.status_code == 400  # without skip_errors the file is refused whole
    ok = upload(client, body, "commit", skip_errors="true")
    assert ok.status_code == 201 and ok.json()["rows_inserted"] == 2

    open_line = ScheduleLine.objects.get(internal_dispatch_date=date(2027, 5, 15))
    assert (open_line.wip_qty, open_line.status, open_line.customer.code) == (
        50,
        "planned",
        "CUST-01",
    )
    closed = ScheduleLine.objects.get(internal_dispatch_date=date(2027, 6, 10))
    assert (
        closed.status == "closed"
        and closed.actual_dispatched_qty == 400
        and closed.customer.code == "CUST-01"
    )


def test_uploading_the_same_file_again_updates_stock_and_blank_cells_keep_it(
    login, users, example, company_a
):
    client = login(users["a_planner"])
    upload(client, HEADER + "H-120,500,15-05-2027,May,CUST-01,Open,50,20,0\n", "commit")
    again = HEADER + "H-120,500,15-05-2027,May,CUST-01,,80,,\n"
    result = upload(client, again, "commit", mode="upsert")
    assert result.status_code == 201 and result.json()["rows_updated"] == 1
    line = ScheduleLine.objects.get(internal_dispatch_date=date(2027, 5, 15))
    assert (line.wip_qty, line.fg_qty) == (80, 20)  # FG was left blank, so it was kept


def test_a_month_that_disagrees_with_the_date_warns(login, users, example):
    body = HEADER + "H-120,500,15-05-2027,June,CUST-01,Open,0,0,0\n"
    row = upload(login(users["a_planner"]), body).json()["rows"][0]
    assert row["status"] == "warning" and "month" in row["messages"][0]["text"].lower()


def test_the_template_has_the_new_columns(login, users, example):
    response = login(users["a_planner"]).get("/api/v1/uploads/template")
    assert response.status_code == 200
    from io import BytesIO

    from openpyxl import load_workbook

    headers = [c.value for c in load_workbook(BytesIO(response.content)).worksheets[0][1]]
    assert headers[:3] == ["Part Number", "Order Qty", "Dispatch Date"]
    assert {"Status", "WIP Stock", "FG Stock", "Dispatched Qty"} <= set(headers)


def test_a_grade_is_needed_to_create_the_part_the_upload_reported(
    login, users, company_a, phase_defaults
):
    Grade.objects.create(company=company_a, name="GG25")
    client = login(users["a_admin"])
    made = client.post(
        "/api/v1/parts",
        {
            "part_number": "NEW-77", "name": "New part", "grade": Grade.objects.get(name="GG25").pk,
            "casting_weight_kg": 12, "pouring_weight_per_mould_kg": 30, "cavities_per_mould": 2,
        },
        **J,
    )  # fmt: skip
    assert made.status_code == 201, made.content


# --- the part's own mould rate on a machine ---------------------------------------------------------------------
ROUTE_KEYS = (
    "op_type sequence enabled time_value time_basis batch_size capacity_bucket lag_hours outsourced "
    "lead_days extra step label setup_minutes machine_types except_ids time_by_type rate_by_machine"
).split()


def test_a_moulding_rate_per_machine_is_saved_and_used_by_the_plan(
    login, users, example, company_a
):
    client = login(users["a_admin"])
    order(company_a, example["part"], qty=600)
    url = f"/api/v1/parts/{example['part'].pk}/operations"
    rows = client.get(url).json()["operations"]
    items = []
    for row in rows:
        item = {k: row[k] for k in ROUTE_KEYS}
        item["resource_ids"] = row["resource_ids"]
        if row["type_code"] == "moulding":
            item["rate_by_machine"] = {
                str(example["line"].pk): 20
            }  # 20 moulds an hour: 3 minutes each
        items.append(item)
    saved = client.put(url, {"operations": items}, **J)
    assert saved.status_code == 200, saved.content
    moulding = next(r for r in saved.json()["operations"] if r["type_code"] == "moulding")
    assert moulding["rate_by_machine"] == {str(example["line"].pk): 20.0}

    plan = new_plan(login(users["a_planner"]))
    line = plan_lines(login(users["a_planner"]), plan)[0]
    detail = login(users["a_planner"]).get(f"/api/v1/plans/{plan['id']}/lines/{line['id']}").json()
    assert detail["requirement"]["minutes"]["moulding"] == pytest.approx(315 * 3)  # not 315 x 1.5


def test_a_rate_for_a_machine_that_is_not_a_moulding_line_is_refused(login, users, example):
    client = login(users["a_admin"])
    url = f"/api/v1/parts/{example['part'].pk}/operations"
    items = []
    for row in client.get(url).json()["operations"]:
        item = {k: row[k] for k in ROUTE_KEYS}
        item["resource_ids"] = row["resource_ids"]
        if row["type_code"] == "moulding":
            item["rate_by_machine"] = {str(example["furnace"].pk): 20}
        items.append(item)
    assert client.put(url, {"operations": items}, **J).status_code == 400
