"""What-if scenarios through the API: changes, run, diff, apply, roles and tenancy."""

import random
import time
from datetime import date, timedelta

import pytest

from apps.core.models import AuditLog
from apps.masters.models import Customer, OperationType, Part, PartCustomer, PartOperation
from apps.plans.models import Plan
from apps.resources.models import CapacityAdjustment, Downtime, Resource
from apps.scheduler.models import ScheduleLine
from seeds.demo_a import build_demo_foundry
from seeds.worked_example import build_worked_example

J = {"format": "json"}
TODAY = date(2026, 11, 2)  # a Monday
TUESDAY_BLOCK = {
    "resource": None,
    "start": "2026-11-03T00:00:00+05:30",
    "end": "2026-11-03T23:59:00+05:30",
}


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("django.utils.timezone.localdate", lambda *a, **k: TODAY)


@pytest.fixture
def plant(company_a):
    """The section 7.5 plant with two furnace lines and one finishing-only line."""
    built = build_worked_example(company_a)
    customer = Customer.objects.get(company=company_a, code="CUST-01")
    fet = Part.objects.create(
        company=company_a,
        part_number="H-FET",
        name="Finish only",
        casting_weight_kg=5,
        pouring_weight_per_mould_kg=10,
    )
    PartCustomer.objects.create(company=company_a, part=fet, customer=customer, is_default=True)
    ft_op = OperationType.objects.get(company=company_a, code="fettling")
    row = PartOperation.objects.create(
        company=company_a,
        part=fet,
        op_type=ft_op,
        sequence=50,
        time_value=3,
        time_basis="per_piece",
        capacity_bucket="shift",
    )
    row.resources.set([built["fettling"]])

    def add(part, qty, due):
        return ScheduleLine.objects.create(
            company=company_a,
            customer=customer,
            part=part,
            dispatch_qty=qty,
            internal_dispatch_date=due,
        )

    built["lines"] = [
        add(built["part"], 600, date(2026, 11, 20)),
        add(built["part"], 300, date(2026, 11, 30)),
        add(fet, 100, date(2026, 11, 20)),
    ]
    return built


def scenario(client, name="What if"):
    response = client.post("/api/v1/scenarios", {"name": name}, **J)
    assert response.status_code == 201, response.content
    return response.json()


def add(client, sid, kind, params, expect=201):
    response = client.post(
        f"/api/v1/scenarios/{sid}/changes", {"kind": kind, "params": params}, **J
    )
    assert response.status_code == expect, response.content
    return response.json()


def block_f1(plant, **over):
    return {**TUESDAY_BLOCK, "resource": plant["furnace"].pk, **over}


def run(client, sid):
    response = client.post(f"/api/v1/scenarios/{sid}/run", {}, **J)
    assert response.status_code == 200, response.content
    return response.json()


# --- the acceptance case ----------------------------------------------------------------------------------------
def test_blocking_a_furnace_for_a_day_shows_exactly_which_lines_move_and_their_new_dates(
    login, users, plant
):
    client = login(users["a_planner"])
    sid = scenario(client, "F1 down on Tuesday")["id"]
    change = add(client, sid, "block_resource", block_f1(plant))
    assert change["text"] == "Block F1 from 03-11-2026 00:00 to 03-11-2026 23:59"

    result = run(client, sid)["result"]
    moved = {d["line_id"]: d for d in result["diff"]["lines"]}
    first, second, finishing = (ln.pk for ln in plant["lines"])
    assert set(moved) == {first, second}  # the finishing-only line does not move
    assert (moved[first]["est_before"], moved[first]["est_after"]) == ("2026-11-05", "2026-11-06")
    assert (moved[second]["est_before"], moved[second]["est_after"]) == ("2026-11-06", "2026-11-07")
    assert moved[first]["part_number"] == "H-120" and moved[first]["customer_code"] == "CUST-01"
    assert moved[first]["tags"] == ["later"] and moved[first]["moved_working_days"] == 1
    assert (
        result["diff"]["counts"]["later"] == 2
        and result["resources"][str(plant["furnace"].pk)]["code"] == "F1"
    )


def test_a_scenario_changes_nothing_until_it_is_applied(login, users, plant):
    client = login(users["a_planner"])
    sid = scenario(client)["id"]
    add(client, sid, "block_resource", block_f1(plant))
    add(client, sid, "change_qty", {"line": plant["lines"][0].pk, "qty": 50})
    add(
        client,
        sid,
        "extra_shift",
        {
            "day_from": "2026-11-08",
            "day_to": "2026-11-08",
            "name": "Sunday",
            "start_time": "06:00",
            "end_time": "14:00",
        },
    )
    run(client, sid)
    assert Downtime.objects.count() == 0 and CapacityAdjustment.objects.count() == 0
    assert ScheduleLine.objects.get(pk=plant["lines"][0].pk).dispatch_qty == 600
    assert Plan.objects.count() == 0


def test_a_scenario_with_no_changes_cannot_be_run(login, users, plant):
    client = login(users["a_planner"])
    sid = scenario(client)["id"]
    assert client.post(f"/api/v1/scenarios/{sid}/run", {}, **J).status_code == 400


# --- changes: validation -----------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "kind, params",
    [
        (
            "block_resource",
            {"start": "2026-11-03T10:00:00+05:30", "end": "2026-11-03T08:00:00+05:30"},
        ),
        (
            "block_resource",
            {
                "resource": 999999,
                "start": "2026-11-03T00:00:00+05:30",
                "end": "2026-11-03T01:00:00+05:30",
            },
        ),
        ("change_qty", {"qty": 0}),
        ("change_qty", {"line": 999999, "qty": 5}),
        ("change_date", {"date": "not-a-date"}),
        (
            "extra_shift",
            {
                "day_from": "2026-11-08",
                "day_to": "2026-11-07",
                "name": "x",
                "start_time": "06:00",
                "end_time": "14:00",
            },
        ),
        (
            "extra_shift",
            {
                "day_from": "2026-11-02",
                "day_to": "2026-11-02",
                "name": "Clash",
                "start_time": "10:00",
                "end_time": "18:00",
            },
        ),
        (
            "extra_shift",
            {
                "day_from": "2026-01-01",
                "day_to": "2026-12-31",
                "name": "Long",
                "start_time": "23:00",
                "end_time": "23:30",
            },
        ),
        ("overtime", {"day_from": "2026-11-02", "day_to": "2026-11-02", "minutes": 0}),
        ("overtime", {"day_from": "2026-11-02", "day_to": "2026-11-02", "minutes": 999}),
        ("teleport", {}),
    ],
)
def test_bad_changes_are_refused(login, users, plant, kind, params):
    client = login(users["a_planner"])
    sid = scenario(client)["id"]
    body = dict(params)
    if kind == "block_resource" and "resource" not in body:
        body["resource"] = plant["furnace"].pk
    if kind in ("change_qty", "change_date") and "line" not in body:
        body["line"] = plant["lines"][0].pk
    assert (
        client.post(
            f"/api/v1/scenarios/{sid}/changes", {"kind": kind, "params": body}, **J
        ).status_code
        == 400
    )


def test_a_change_cannot_reference_another_companys_rows(login, users, plant, company_b):
    other = build_worked_example(company_b)
    client = login(users["a_planner"])
    sid = scenario(client)["id"]
    add(
        client,
        sid,
        "block_resource",
        {**TUESDAY_BLOCK, "resource": other["furnace"].pk},
        expect=400,
    )
    add(
        client,
        sid,
        "overtime",
        {
            "day_from": "2026-11-02",
            "day_to": "2026-11-02",
            "minutes": 60,
            "resources": [other["furnace"].pk],
        },
        expect=400,
    )
    add(
        client,
        sid,
        "overtime",
        {
            "day_from": "2026-11-02",
            "day_to": "2026-11-02",
            "minutes": 60,
            "shift": other["shifts"][0].pk,
        },
        expect=400,
    )


def test_dispatched_or_cancelled_lines_cannot_be_what_if_targets(login, users, plant):
    line = plant["lines"][0]
    ScheduleLine.objects.filter(pk=line.pk).update(status="cancelled")
    client = login(users["a_planner"])
    sid = scenario(client)["id"]
    add(client, sid, "change_qty", {"line": line.pk, "qty": 5}, expect=400)


def test_changes_can_be_listed_described_and_removed(login, users, plant):
    client = login(users["a_planner"])
    sid = scenario(client)["id"]
    a = add(client, sid, "change_qty", {"line": plant["lines"][0].pk, "qty": 1500})
    b = add(
        client,
        sid,
        "overtime",
        {
            "day_from": "2026-11-02",
            "day_to": "2026-11-06",
            "minutes": 60,
            "resources": [plant["furnace"].pk],
        },
    )
    detail = client.get(f"/api/v1/scenarios/{sid}").json()
    assert [c["text"] for c in detail["changes"]] == [
        "Make H-120 for CUST-01 (due 20-11-2026) 1,500 pieces",
        "Overtime of 60 min on 02-11-2026 to 06-11-2026 for F1",
    ]
    assert client.delete(f"/api/v1/scenarios/{sid}/changes/{a['id']}").status_code == 204
    assert [c["id"] for c in client.get(f"/api/v1/scenarios/{sid}").json()["changes"]] == [b["id"]]
    assert client.delete(f"/api/v1/scenarios/{sid}/changes/999999").status_code == 404


# --- freshness ---------------------------------------------------------------------------------------------------------
def test_the_result_goes_out_of_date_when_changes_or_data_change(login, users, plant):
    client = login(users["a_planner"])
    sid = scenario(client)["id"]
    assert client.get(f"/api/v1/scenarios/{sid}").json()["state"] == "never_run"
    first = add(client, sid, "change_qty", {"line": plant["lines"][0].pk, "qty": 100})
    assert run(client, sid)["state"] == "fresh"

    add(client, sid, "change_date", {"line": plant["lines"][1].pk, "date": "2026-12-15"})
    assert client.get(f"/api/v1/scenarios/{sid}").json()["state"] == "changes_edited"
    assert run(client, sid)["state"] == "fresh"

    ScheduleLine.objects.get(pk=plant["lines"][2].pk).save()
    assert client.get(f"/api/v1/scenarios/{sid}").json()["state"] == "data_changed"
    client.delete(f"/api/v1/scenarios/{sid}/changes/{first['id']}")


# --- apply ----------------------------------------------------------------------------------------------------------------
def test_applying_makes_every_change_real_and_the_recalculated_plan_matches_the_simulation(
    login, users, plant
):
    client = login(users["a_planner"])
    sid = scenario(client, "Busy week")["id"]
    add(client, sid, "block_resource", block_f1(plant, reason="Lining change"))
    add(client, sid, "change_qty", {"line": plant["lines"][1].pk, "qty": 450})
    add(client, sid, "change_date", {"line": plant["lines"][2].pk, "date": "2026-11-12"})
    add(
        client,
        sid,
        "extra_shift",
        {
            "day_from": "2026-11-08",
            "day_to": "2026-11-08",
            "name": "Sunday",
            "start_time": "06:00",
            "end_time": "14:00",
            "break_minutes": 30,
        },
    )
    add(
        client,
        sid,
        "overtime",
        {
            "day_from": "2026-11-04",
            "day_to": "2026-11-05",
            "minutes": 60,
            "resources": [plant["furnace"].pk],
        },
    )
    simulated = {d["line_id"]: d for d in run(client, sid)["result"]["diff"]["lines"]}

    response = client.post(f"/api/v1/scenarios/{sid}/apply", {}, **J)
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["status"] == "applied" and body["applied_by_name"] == "a_planner"
    assert (
        body["applied_summary"]["downtimes"] == 1
        and body["applied_summary"]["line_edits"] == 2
        and body["applied_summary"]["adjustments"] == 2
    )

    down = Downtime.objects.get()
    assert (down.resource_id, down.reason) == (plant["furnace"].pk, "Lining change")
    assert ScheduleLine.objects.get(pk=plant["lines"][1].pk).dispatch_qty == 450
    assert ScheduleLine.objects.get(pk=plant["lines"][2].pk).internal_dispatch_date == date(
        2026, 11, 12
    )
    kinds = sorted(CapacityAdjustment.objects.values_list("kind", flat=True))
    assert kinds == ["extra_shift", "overtime"]

    # The plan that was recalculated from the real data gives the dates the scenario promised.
    plan = Plan.objects.get()
    assert body["applied_summary"]["plan"] == {"id": plan.pk, "version": 1, "new": True}
    lines = {pl.schedule_line_id: pl for pl in plan.lines.all()}
    for line_id, diff in simulated.items():
        assert str(lines[line_id].est_dispatch_date) == diff["est_after"], line_id

    who = set(
        AuditLog.objects.filter(
            model_label__in=[
                "resources.Downtime",
                "scheduler.ScheduleLine",
                "resources.CapacityAdjustment",
            ],
            action__in=["create", "update"],
        ).values_list("username", flat=True)
    )
    assert "a_planner" in who


def test_apply_can_skip_the_recalculation_and_reuses_an_existing_draft(login, users, plant):
    client = login(users["a_planner"])
    first = client.post("/api/v1/plans", {}, **J).json()
    sid = scenario(client)["id"]
    add(client, sid, "change_qty", {"line": plant["lines"][0].pk, "qty": 100})
    run(client, sid)
    done = client.post(f"/api/v1/scenarios/{sid}/apply", {"recalculate": False}, **J).json()
    assert done["applied_summary"]["plan"] is None and Plan.objects.count() == 1
    assert client.get(f"/api/v1/plans/{first['id']}").json()["stale"]

    sid2 = scenario(client, "Second")["id"]
    add(client, sid2, "change_qty", {"line": plant["lines"][1].pk, "qty": 100})
    run(client, sid2)
    again = client.post(f"/api/v1/scenarios/{sid2}/apply", {}, **J).json()
    assert again["applied_summary"]["plan"] == {
        "id": first["id"],
        "version": 1,
        "new": False,
    }  # the draft was recalculated


def test_applying_when_the_latest_plan_is_confirmed_starts_a_new_plan(login, users, plant):
    client = login(users["a_planner"])
    plan = client.post("/api/v1/plans", {}, **J).json()
    client.post(f"/api/v1/plans/{plan['id']}/confirm", {}, **J)
    sid = scenario(client)["id"]
    add(client, sid, "change_qty", {"line": plant["lines"][0].pk, "qty": 100})
    run(client, sid)
    summary = client.post(f"/api/v1/scenarios/{sid}/apply", {}, **J).json()["applied_summary"]
    assert summary["plan"]["new"] and summary["plan"]["version"] == 2
    assert Plan.objects.get(pk=plan["id"]).status == "confirmed"  # the baseline is untouched


@pytest.mark.parametrize("stage", ["never_run", "changes_edited", "data_changed", "twice"])
def test_apply_is_refused_unless_the_result_is_fresh_and_unapplied(login, users, plant, stage):
    client = login(users["a_planner"])
    sid = scenario(client)["id"]
    add(client, sid, "change_qty", {"line": plant["lines"][0].pk, "qty": 100})
    if stage != "never_run":
        run(client, sid)
    if stage == "changes_edited":
        add(client, sid, "change_qty", {"line": plant["lines"][1].pk, "qty": 100})
    if stage == "data_changed":
        ScheduleLine.objects.get(pk=plant["lines"][2].pk).save()
    if stage == "twice":
        assert (
            client.post(f"/api/v1/scenarios/{sid}/apply", {"recalculate": False}, **J).status_code
            == 200
        )
    response = client.post(f"/api/v1/scenarios/{sid}/apply", {}, **J)
    assert response.status_code == 400
    if stage != "twice":
        assert (
            ScheduleLine.objects.get(pk=plant["lines"][0].pk).dispatch_qty == 600
        )  # nothing was changed


def test_a_failed_apply_changes_nothing(login, users, plant, monkeypatch):
    client = login(users["a_planner"])
    sid = scenario(client)["id"]
    add(client, sid, "block_resource", block_f1(plant))
    add(client, sid, "change_qty", {"line": plant["lines"][0].pk, "qty": 100})
    run(client, sid)

    original = ScheduleLine.save

    def boom(self, *args, **kwargs):
        raise RuntimeError("database trouble")

    monkeypatch.setattr(ScheduleLine, "save", boom)
    with pytest.raises(RuntimeError):
        client.post(f"/api/v1/scenarios/{sid}/apply", {}, **J)
    monkeypatch.setattr(ScheduleLine, "save", original)
    assert Downtime.objects.count() == 0  # the block was rolled back with the rest


def test_applied_scenarios_are_kept_and_frozen(login, users, plant):
    client = login(users["a_planner"])
    sid = scenario(client)["id"]
    add(client, sid, "change_qty", {"line": plant["lines"][0].pk, "qty": 100})
    run(client, sid)
    client.post(f"/api/v1/scenarios/{sid}/apply", {"recalculate": False}, **J)
    assert client.delete(f"/api/v1/scenarios/{sid}").status_code == 400
    assert client.patch(f"/api/v1/scenarios/{sid}", {"name": "New name"}, **J).status_code == 400
    add(client, sid, "change_qty", {"line": plant["lines"][1].pk, "qty": 5}, expect=400)
    assert client.post(f"/api/v1/scenarios/{sid}/run", {}, **J).status_code == 400


def test_a_draft_can_be_renamed_and_deleted(login, users, plant):
    client = login(users["a_planner"])
    sid = scenario(client, "Old")["id"]
    assert (
        client.patch(f"/api/v1/scenarios/{sid}", {"name": "New", "notes": "Why"}, **J).json()[
            "name"
        ]
        == "New"
    )
    assert client.delete(f"/api/v1/scenarios/{sid}").status_code == 204


# --- roles and tenancy ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("who, expected", [("a_admin", 201), ("a_planner", 201), ("a_viewer", 403)])
def test_roles_for_scenarios(login, users, plant, who, expected):
    assert login(users[who]).post("/api/v1/scenarios", {"name": "x"}, **J).status_code == expected


def test_viewers_cannot_even_read_scenarios(login, users, plant):
    sid = scenario(login(users["a_planner"]))["id"]
    viewer = login(users["a_viewer"])
    assert viewer.get("/api/v1/scenarios").status_code == 403
    assert viewer.get(f"/api/v1/scenarios/{sid}").status_code == 403


def test_company_a_never_sees_or_runs_company_bs_scenarios(login, users, plant, company_b):
    b_plant = build_worked_example(company_b)
    b_client = login(users["b_admin"])
    theirs = scenario(b_client, "B only")["id"]
    add(b_client, theirs, "block_resource", {**TUESDAY_BLOCK, "resource": b_plant["furnace"].pk})
    client = login(users["a_planner"])
    mine = scenario(client, "A only")["id"]
    assert [s["id"] for s in client.get("/api/v1/scenarios").json()["results"]] == [mine]
    for path, method in (
        (f"/api/v1/scenarios/{theirs}", "get"),
        (f"/api/v1/scenarios/{theirs}/run", "post"),
        (f"/api/v1/scenarios/{theirs}/apply", "post"),
        (f"/api/v1/scenarios/{theirs}/changes", "post"),
    ):
        assert (
            getattr(client, method)(
                path, **({} if method == "get" else {"data": {}, "format": "json"})
            ).status_code
            == 404
        ), path


def test_scenarios_are_audited(login, users, plant):
    sid = scenario(login(users["a_planner"]), "Audited")["id"]
    assert AuditLog.objects.filter(
        model_label="scenarios.Scenario", object_pk=str(sid), username="a_planner"
    ).exists()


# --- capacity adjustments as real masters ------------------------------------------------------------------------------------------
def test_company_admin_manages_extra_shifts_and_overtime_and_everyone_reads(login, users, plant):
    admin = login(users["a_admin"])
    shift = admin.post(
        "/api/v1/capacity-adjustments",
        {
            "kind": "extra_shift",
            "day_from": "2026-11-08",
            "day_to": "2026-11-08",
            "name": "Sunday",
            "start_time": "06:00",
            "end_time": "14:00",
            "break_minutes": 30,
        },
        **J,
    )
    assert shift.status_code == 201 and shift.json()["summary"] == "Sunday, 06:00-14:00, 08-11-2026"
    ot = admin.post(
        "/api/v1/capacity-adjustments",
        {"kind": "overtime", "day_from": "2026-11-02", "day_to": "2026-11-06", "minutes": 60},
        **J,
    )
    assert ot.status_code == 201 and ot.json()["summary"].startswith("Overtime of 60 min")
    assert len(login(users["a_viewer"]).get("/api/v1/capacity-adjustments").json()["results"]) == 2
    assert (
        login(users["a_planner"])
        .post(
            "/api/v1/capacity-adjustments",
            {"kind": "overtime", "day_from": "2026-11-02", "day_to": "2026-11-02", "minutes": 30},
            **J,
        )
        .status_code
        == 403
    )


@pytest.mark.parametrize(
    "body",
    [
        {
            "kind": "extra_shift",
            "day_from": "2026-11-02",
            "day_to": "2026-11-02",
            "name": "Clash",
            "start_time": "10:00",
            "end_time": "18:00",
        },
        {
            "kind": "extra_shift",
            "day_from": "2026-11-08",
            "day_to": "2026-11-08",
            "start_time": "06:00",
            "end_time": "14:00",
        },
        {
            "kind": "extra_shift",
            "day_from": "2026-11-08",
            "day_to": "2026-11-08",
            "name": "Bad",
            "start_time": "06:00",
            "end_time": "06:00",
        },
        {"kind": "overtime", "day_from": "2026-11-02", "day_to": "2026-11-02"},
        {"kind": "overtime", "day_from": "2026-11-02", "day_to": "2026-11-02", "minutes": 600},
        {"kind": "overtime", "day_from": "2026-11-09", "day_to": "2026-11-02", "minutes": 30},
    ],
)
def test_bad_adjustments_are_refused(login, users, plant, body):
    assert (
        login(users["a_admin"]).post("/api/v1/capacity-adjustments", body, **J).status_code == 400
    )


def test_two_extra_shifts_cannot_overlap(login, users, plant):
    admin = login(users["a_admin"])
    body = {
        "kind": "extra_shift",
        "day_from": "2026-11-08",
        "day_to": "2026-11-08",
        "name": "A",
        "start_time": "06:00",
        "end_time": "14:00",
    }
    assert admin.post("/api/v1/capacity-adjustments", body, **J).status_code == 201
    assert (
        admin.post(
            "/api/v1/capacity-adjustments",
            {**body, "name": "B", "start_time": "12:00", "end_time": "18:00"},
            **J,
        ).status_code
        == 400
    )


def test_every_real_plan_honours_extra_shifts_and_overtime(login, users, plant):
    planner, admin = login(users["a_planner"]), login(users["a_admin"])
    ScheduleLine.objects.filter(pk=plant["lines"][0].pk).update(dispatch_qty=1800)
    base = planner.post("/api/v1/plans", {}, **J).json()
    base_line = planner.get(f"/api/v1/plans/{base['id']}/lines?q=H-120").json()["results"][0]

    admin.post(
        "/api/v1/capacity-adjustments",
        {
            "kind": "overtime",
            "day_from": "2026-11-02",
            "day_to": "2026-11-30",
            "minutes": 120,
            "resources": [plant["furnace"].pk],
        },
        **J,
    )
    assert planner.get(f"/api/v1/plans/{base['id']}").json()["stale"]  # the master changed
    planner.post(f"/api/v1/plans/{base['id']}/recalculate", {}, **J)
    after = planner.get(f"/api/v1/plans/{base['id']}/lines?q=H-120").json()["results"][0]
    assert after["est_dispatch_date"] < base_line["est_dispatch_date"]


# --- speed ----------------------------------------------------------------------------------------------------------------------------
def test_running_a_scenario_on_500_lines_is_fast_enough_to_use(login, users, company_a):
    build_demo_foundry(company_a)
    rng = random.Random(3)
    pairs = [
        (link.customer, p)
        for p in Part.objects.filter(company=company_a)
        for link in p.customer_links.all()
    ]
    ScheduleLine.objects.bulk_create(
        [
            ScheduleLine(
                company=company_a,
                customer=c,
                part=p,
                dispatch_qty=rng.choice([20, 40, 60, 100]),
                internal_dispatch_date=TODAY + timedelta(days=rng.randint(3, 120)),
            )
            for c, p in (rng.choice(pairs) for _ in range(500))
        ]
    )
    client = login(users["a_planner"])
    sid = scenario(client)["id"]
    furnace = Resource.objects.get(company=company_a, code="F1")
    add(client, sid, "block_resource", {**TUESDAY_BLOCK, "resource": furnace.pk})
    started = time.perf_counter()
    result = run(client, sid)["result"]
    elapsed = time.perf_counter() - started
    assert result["lines_planned"] == 500 and elapsed < 10, (
        f"running the scenario took {elapsed:.1f}s"
    )
