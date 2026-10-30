"""Schedule line grid API: entry, filters, totals, copy-month, roles, tenancy, audit."""

from datetime import date, timedelta

import pytest

from apps.core.models import AuditLog
from apps.masters.models import Customer, Grade, Part, PartCustomer
from apps.scheduler.models import ScheduleLine

J = {"format": "json"}
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


@pytest.fixture
def basics(company_a):
    gg, sg = (
        Grade.objects.create(company=company_a, name="GG25"),
        Grade.objects.create(company=company_a, name="SG500"),
    )
    c1 = Customer.objects.create(company=company_a, code="C1", name="Aarav Pumps", priority="A")
    c2 = Customer.objects.create(company=company_a, code="C2", name="Bharat Valves")
    p1 = Part.objects.create(
        company=company_a,
        part_number="P1",
        name="Casing",
        grade=gg,
        casting_weight_kg=20,
        pouring_weight_per_mould_kg=45,
        cavities_per_mould=2,
        selling_price=500,
    )
    p2 = Part.objects.create(
        company=company_a,
        part_number="P2",
        name="Valve",
        grade=sg,
        casting_weight_kg=5,
        pouring_weight_per_mould_kg=12,
        cavities_per_mould=2,
    )
    PartCustomer.objects.create(company=company_a, part=p1, customer=c1, is_default=True)
    PartCustomer.objects.create(company=company_a, part=p2, customer=c2, is_default=True)
    return {"c1": c1, "c2": c2, "p1": p1, "p2": p2, "gg": gg, "sg": sg}


def line(company, b, customer="c1", part="p1", qty=100, day=date(2026, 11, 5), **extra):
    return ScheduleLine.objects.create(
        company=company,
        customer=b[customer],
        part=b[part],
        dispatch_qty=qty,
        internal_dispatch_date=day,
        **extra,
    )


def rows(response):
    return response.json()["results"]


def test_planner_creates_edits_and_deletes_a_line(login, users, basics):
    client = login(users["a_planner"])
    body = {
        "customer": basics["c1"].pk,
        "part": basics["p1"].pk,
        "dispatch_qty": 600,
        "internal_dispatch_date": "2026-11-12",
        "remarks": "rush",
    }
    created = client.post("/api/v1/schedule-lines", body, **J)
    assert created.status_code == 201
    data = created.json()
    assert (data["month"], data["status"], data["customer_code"], data["part_number"]) == (
        "2026-11",
        "planned",
        "C1",
        "P1",
    )
    assert data["tonnes"] == 12.0 and data["value"] == 300000.0  # 600 x 20 kg; 600 x 500

    assert (
        client.patch(f"/api/v1/schedule-lines/{data['id']}", {"dispatch_qty": 650}, **J).json()[
            "tonnes"
        ]
        == 13.0
    )
    assert client.delete(f"/api/v1/schedule-lines/{data['id']}").status_code == 204


@pytest.mark.parametrize(
    "bad",
    [
        {"dispatch_qty": 0},
        {"dispatch_qty": -1},
        {"internal_dispatch_date": "not-a-date"},
        {"actual_dispatch_date": "2999-01-01"},
        {"actual_dispatched_qty": 5},
        {"status": "dispatched"},
    ],
)
def test_impossible_lines_are_refused(login, users, basics, bad):
    body = {
        "customer": basics["c1"].pk,
        "part": basics["p1"].pk,
        "dispatch_qty": 10,
        "internal_dispatch_date": "2026-11-12",
        **bad,
    }
    assert login(users["a_planner"]).post("/api/v1/schedule-lines", body, **J).status_code == 400


def test_actual_date_marks_the_line_dispatched_and_clearing_it_undoes_that(
    login, users, basics, company_a
):
    client = login(users["a_planner"])
    obj = line(company_a, basics)
    done = client.patch(
        f"/api/v1/schedule-lines/{obj.pk}",
        {"actual_dispatch_date": YESTERDAY, "actual_dispatched_qty": 60},
        **J,
    ).json()
    assert done["status"] == "dispatched" and done["actual_dispatched_qty"] == 60
    undone = client.patch(
        f"/api/v1/schedule-lines/{obj.pk}",
        {"actual_dispatch_date": None, "actual_dispatched_qty": None},
        **J,
    ).json()
    assert undone["status"] == "planned"


def test_unlinked_part_is_a_warning_not_a_block(login, users, basics):
    body = {
        "customer": basics["c2"].pk,
        "part": basics["p1"].pk,
        "dispatch_qty": 10,
        "internal_dispatch_date": "2026-11-12",
    }
    response = login(users["a_planner"]).post("/api/v1/schedule-lines", body, **J)
    assert response.status_code == 201 and "not linked" in response.json()["warnings"][0]


def test_filters_by_month_customer_part_grade_status_and_text(login, users, basics, company_a):
    line(company_a, basics, day=date(2026, 11, 5))
    line(company_a, basics, customer="c2", part="p2", day=date(2026, 11, 20), status="in_progress")
    line(company_a, basics, day=date(2026, 12, 2))
    client = login(users["a_viewer"])
    count = lambda q: len(rows(client.get(f"/api/v1/schedule-lines?{q}")))  # noqa: E731
    assert (
        count("month=2026-11") == 2 and count("month=2026-12") == 1 and count("month=2027-01") == 0
    )
    assert count(f"customer={basics['c2'].pk}") == 1 and count(f"part={basics['p1'].pk}") == 2
    assert count(f"grade={basics['sg'].pk}") == 1 and count("status=in_progress") == 1
    assert count("q=valve") == 1 and count("q=zzz") == 0
    assert client.get("/api/v1/schedule-lines?month=junk").status_code == 400


def test_lines_come_back_in_date_order(login, users, basics, company_a):
    line(company_a, basics, day=date(2026, 11, 20))
    line(company_a, basics, day=date(2026, 11, 2))
    got = [
        r["internal_dispatch_date"]
        for r in rows(login(users["a_viewer"]).get("/api/v1/schedule-lines"))
    ]
    assert got == sorted(got)


def test_month_totals_in_pieces_tonnes_and_value(login, users, basics, company_a):
    line(company_a, basics, qty=100)  # 2 t, 50,000
    line(company_a, basics, customer="c2", part="p2", qty=200)  # 1 t, no price
    line(company_a, basics, qty=999, status="cancelled")  # ignored
    line(company_a, basics, qty=50, day=date(2026, 12, 1))  # other month
    summary = login(users["a_viewer"]).get("/api/v1/schedule-lines/summary?month=2026-11").json()
    assert summary == {
        "lines": 2,
        "pieces": 300,
        "tonnes": 3.0,
        "value": 50000.0,
        "lines_without_price": 1,
    }


def test_copy_month_keeps_the_day_clamps_to_month_end_and_skips_repeats(
    login, users, basics, company_a
):
    line(company_a, basics, day=date(2026, 1, 31), qty=10, remarks="note")
    line(
        company_a,
        basics,
        day=date(2026, 1, 15),
        qty=20,
        status="dispatched",
        actual_dispatch_date=date(2026, 1, 14),
    )
    line(company_a, basics, day=date(2026, 1, 20), qty=30, status="cancelled")
    client = login(users["a_planner"])
    first = client.post(
        "/api/v1/schedule-lines/copy-month", {"from_month": "2026-01", "to_month": "2026-02"}, **J
    )
    assert first.json() == {"created": 2, "skipped": 0}  # cancelled lines are not copied
    copies = ScheduleLine.objects.filter(internal_dispatch_date__month=2)
    assert sorted(c.internal_dispatch_date.day for c in copies) == [
        15,
        28,
    ]  # 31 January -> 28 February
    assert all(c.status == "planned" and c.actual_dispatch_date is None for c in copies)
    assert client.post(
        "/api/v1/schedule-lines/copy-month", {"from_month": "2026-01", "to_month": "2026-02"}, **J
    ).json() == {"created": 0, "skipped": 2}
    assert (
        client.post(
            "/api/v1/schedule-lines/copy-month",
            {"from_month": "2026-01", "to_month": "2026-01"},
            **J,
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/schedule-lines/copy-month", {"from_month": "x", "to_month": "2026-01"}, **J
        ).status_code
        == 400
    )


@pytest.mark.parametrize("who, expected", [("a_admin", 201), ("a_planner", 201), ("a_viewer", 403)])
def test_roles_for_writing_lines(login, users, basics, who, expected):
    body = {
        "customer": basics["c1"].pk,
        "part": basics["p1"].pk,
        "dispatch_qty": 10,
        "internal_dispatch_date": "2026-11-12",
    }
    assert login(users[who]).post("/api/v1/schedule-lines", body, **J).status_code == expected


def test_viewer_can_read_the_schedule(login, users, basics, company_a):
    line(company_a, basics)
    assert len(rows(login(users["a_viewer"]).get("/api/v1/schedule-lines"))) == 1


def test_company_a_never_sees_or_touches_company_bs_lines(
    login, users, basics, company_a, company_b
):
    other = Customer.objects.create(company=company_b, code="B1", name="B1")
    other_part = Part.objects.create(
        company=company_b,
        part_number="BP",
        name="BP",
        casting_weight_kg=1,
        pouring_weight_per_mould_kg=2,
    )
    theirs = ScheduleLine.objects.create(
        company=company_b,
        customer=other,
        part=other_part,
        dispatch_qty=5,
        internal_dispatch_date=date(2026, 11, 5),
    )
    mine = line(company_a, basics)
    client = login(users["a_planner"])

    assert [r["id"] for r in rows(client.get("/api/v1/schedule-lines"))] == [mine.pk]
    assert client.get(f"/api/v1/schedule-lines/{theirs.pk}").status_code == 404
    assert (
        client.patch(f"/api/v1/schedule-lines/{theirs.pk}", {"dispatch_qty": 1}, **J).status_code
        == 404
    )
    assert client.delete(f"/api/v1/schedule-lines/{theirs.pk}").status_code == 404
    body = {
        "customer": other.pk,
        "part": other_part.pk,
        "dispatch_qty": 1,
        "internal_dispatch_date": "2026-11-05",
    }
    assert (
        client.post("/api/v1/schedule-lines", body, **J).status_code == 400
    )  # cannot reference B's rows
    assert client.get("/api/v1/schedule-lines/summary").json()["lines"] == 1
    ScheduleLine.objects.get(pk=theirs.pk)  # untouched


def test_vezapp_admin_needs_a_company_to_see_lines(login, users, basics, company_a):
    line(company_a, basics)
    client = login(users["vezapp_admin"])
    assert rows(client.get("/api/v1/schedule-lines")) == []
    client.credentials(HTTP_X_VP_CLIENT="web", HTTP_X_COMPANY_ID=str(company_a.pk))
    assert len(rows(client.get("/api/v1/schedule-lines"))) == 1


def test_customer_or_part_in_use_cannot_be_deleted(login, users, basics, company_a):
    line(company_a, basics)
    client = login(users["a_admin"])
    assert client.delete(f"/api/v1/customers/{basics['c1'].pk}").status_code == 400
    assert client.delete(f"/api/v1/parts/{basics['p1'].pk}").status_code == 400


def test_line_changes_are_audited(login, users, basics, company_a):
    client = login(users["a_planner"])
    body = {
        "customer": basics["c1"].pk,
        "part": basics["p1"].pk,
        "dispatch_qty": 10,
        "internal_dispatch_date": "2026-11-12",
    }
    made = client.post("/api/v1/schedule-lines", body, **J).json()
    client.patch(f"/api/v1/schedule-lines/{made['id']}", {"dispatch_qty": 25}, **J)
    client.delete(f"/api/v1/schedule-lines/{made['id']}")
    log = AuditLog.objects.filter(model_label="scheduler.ScheduleLine").order_by("id")
    assert [(e.action, e.username) for e in log] == [
        ("create", "a_planner"),
        ("update", "a_planner"),
        ("delete", "a_planner"),
    ]
    assert (log[1].before["dispatch_qty"], log[1].after["dispatch_qty"]) == (10, 25)
