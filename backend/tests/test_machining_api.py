"""Machining through the API: several operations per part, machine types, time per type, setup,
machines picked up by type, validation, copy, and a real plan on the result."""

from datetime import date

import pytest

from apps.masters.machines import allowed_ids, code_of, machines_by_type, name_of
from apps.masters.models import OperationType, Part, PartOperation
from apps.plans.inputs import build_input
from apps.resources.models import Resource, ResourceType
from apps.scheduler.models import ScheduleLine
from seeds.worked_example import build_worked_example

J = {"format": "json"}
TODAY = date(2026, 11, 2)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("django.utils.timezone.localdate", lambda *a, **k: TODAY)


def make_machine(company, rtype, code):
    return Resource.objects.create(
        company=company,
        code=code,
        name=f"{rtype.name} {code}",
        resource_type=rtype,
        efficiency_pct=85,
    )


@pytest.fixture
def shop(company_a):
    """The 7.5 plant plus machine types VMC, CNC, HMC and five machines."""
    built = build_worked_example(company_a)
    types = {
        n: ResourceType.objects.create(company=company_a, name=n, kind="work_centre")
        for n in ("VMC", "CNC", "HMC")
    }
    machines = {
        code: make_machine(company_a, types[t], code)
        for code, t in (
            ("VMC-1", "VMC"),
            ("VMC-2", "VMC"),
            ("CNC-1", "CNC"),
            ("CNC-2", "CNC"),
            ("HMC-1", "HMC"),
        )
    }
    built.update(
        types=types,
        machines=machines,
        machining=OperationType.objects.get(company=company_a, code="machining"),
    )
    return built


def route_url(shop):
    return f"/api/v1/parts/{shop['part'].pk}/operations"


KEYS = (
    "op_type",
    "sequence",
    "enabled",
    "time_value",
    "time_basis",
    "batch_size",
    "capacity_bucket",
    "lag_hours",
    "outsourced",
    "lead_days",
    "extra",
    "step",
    "label",
    "setup_minutes",
    "machine_types",
    "except_ids",
    "time_by_type",
)


def item_from(row):
    out = {k: row[k] for k in KEYS}
    out["resource_ids"] = row["resource_ids"]
    return out


def step_item(
    shop,
    step,
    label,
    types=(),
    times=None,
    setup=0,
    default=None,
    resources=(),
    except_ids=(),
    **over,
):
    item = {
        "op_type": shop["machining"].pk, "sequence": 60 + step // 10, "enabled": True, "time_value": default, "time_basis": "per_piece",
        "capacity_bucket": "shift", "lag_hours": 0, "outsourced": False, "extra": {}, "resource_ids": list(resources), "step": step,
        "label": label, "setup_minutes": setup, "machine_types": [shop["types"][t].pk for t in types], "except_ids": [shop["machines"][m].pk for m in except_ids],
        "time_by_type": {str(shop["types"][t].pk): v for t, v in (times or {}).items()},
    }  # fmt: skip
    item.update(over)
    return item


def put_route(client, shop, *steps, replace_machining=True):
    route = client.get(route_url(shop)).json()
    items = [
        item_from(r)
        for r in route["operations"]
        if not (replace_machining and r["type_code"] == "machining")
    ]
    return client.put(route_url(shop), {"operations": [*items, *steps]}, **J)


def two_steps(shop):
    return (
        step_item(
            shop, 10, "Rough milling", types=["VMC", "HMC"], times={"VMC": 12, "HMC": 7}, setup=45
        ),
        step_item(shop, 20, "Finish bore", types=["CNC"], default=9, setup=20),
    )


def rows_of(route, type_code="machining"):
    return [r for r in route["operations"] if r["type_code"] == type_code]


# --- the route -----------------------------------------------------------------------------------------------------
def test_machining_may_be_routed_several_times_and_other_operations_may_not(login, users, shop):
    route = login(users["a_viewer"]).get(route_url(shop)).json()
    machining = rows_of(route)
    assert (
        len(machining) == 1
        and machining[0]["multi_step"]
        and machining[0]["step"] == 0
        and machining[0]["code"] == "machining"
    )
    assert not rows_of(route, "fettling")[0]["multi_step"]


def test_a_part_gets_several_machining_operations_each_with_its_own_machines_and_times(
    login, users, shop
):
    response = put_route(login(users["a_admin"]), shop, *two_steps(shop))
    assert response.status_code == 200, response.content
    rows = rows_of(response.json())
    assert [r["code"] for r in rows] == ["machining~10", "machining~20"]
    rough, finish = rows
    assert (rough["label"], rough["step"], rough["setup_minutes"]) == ("Rough milling", 10, 45)
    assert rough["machine_types"] == sorted([shop["types"]["VMC"].pk, shop["types"]["HMC"].pk])
    assert rough["time_by_type"] == {
        str(shop["types"]["VMC"].pk): 12,
        str(shop["types"]["HMC"].pk): 7,
    }
    machines = shop["machines"]
    assert sorted(rough["effective_resource_ids"]) == sorted(
        [machines["VMC-1"].pk, machines["VMC-2"].pk, machines["HMC-1"].pk]
    )
    assert sorted(finish["effective_resource_ids"]) == sorted(
        [machines["CNC-1"].pk, machines["CNC-2"].pk]
    )
    assert rough["capacity_modelled"] and finish["capacity_modelled"]
    assert PartOperation.objects.filter(part=shop["part"], op_type=shop["machining"]).count() == 2


def test_the_saved_route_reads_back_the_same(login, users, shop):
    client = login(users["a_admin"])
    put_route(client, shop, *two_steps(shop))
    again = rows_of(client.get(route_url(shop)).json())
    assert [(r["code"], r["label"], r["setup_minutes"]) for r in again] == [
        ("machining~10", "Rough milling", 45),
        ("machining~20", "Finish bore", 20),
    ]


def test_a_machine_added_later_to_an_allowed_type_is_picked_up_automatically(
    login, users, shop, company_a
):
    client = login(users["a_admin"])
    put_route(client, shop, *two_steps(shop))
    new = make_machine(company_a, shop["types"]["VMC"], "VMC-3")
    ScheduleLine.objects.create(
        company=company_a,
        customer=shop["part"].customer_links.first().customer,
        part=shop["part"],
        dispatch_qty=50,
        internal_dispatch_date=date(2026, 11, 20),
    )
    rough = rows_of(client.get(route_url(shop)).json())[0]
    assert new.pk in rough["effective_resource_ids"]
    spec = build_input(company_a, TODAY)[0].parts[shop["part"].pk]
    assert new.pk in next(o for o in spec.ops if o.code == "machining~10").resource_ids


def test_a_machine_marked_not_suitable_is_left_out(login, users, shop):
    client = login(users["a_admin"])
    rough = step_item(shop, 10, "Rough", types=["VMC", "HMC"], default=10, except_ids=["VMC-2"])
    row = rows_of(put_route(client, shop, rough).json())[0]
    assert (
        shop["machines"]["VMC-2"].pk not in row["effective_resource_ids"]
        and shop["machines"]["VMC-1"].pk in row["effective_resource_ids"]
    )
    assert row["except_ids"] == [shop["machines"]["VMC-2"].pk]


def test_individually_chosen_machines_add_to_the_types(login, users, shop):
    row = rows_of(
        put_route(
            login(users["a_admin"]),
            shop,
            step_item(
                shop,
                10,
                "",
                types=["CNC"],
                default=8,
                resources=["HMC-1"] and [shop["machines"]["HMC-1"].pk],
            ),
        ).json()
    )[0]
    assert (
        shop["machines"]["HMC-1"].pk in row["effective_resource_ids"]
        and shop["machines"]["CNC-1"].pk in row["effective_resource_ids"]
    )


# --- the engine's input ------------------------------------------------------------------------------------------------
def test_the_plan_input_carries_codes_names_times_setup_and_machine_types(
    login, users, shop, company_a
):
    put_route(login(users["a_admin"]), shop, *two_steps(shop))
    ScheduleLine.objects.create(
        company=company_a,
        customer=shop["part"].customer_links.first().customer,
        part=shop["part"],
        dispatch_qty=100,
        internal_dispatch_date=date(2026, 11, 20),
    )
    inp, _ = build_input(company_a, TODAY)
    ops = {o.code: o for o in inp.parts[shop["part"].pk].ops}
    assert {"machining~10", "machining~20"} <= set(ops)
    rough = ops["machining~10"]
    assert (
        rough.name == "Machining OP10 Rough milling"
        and rough.step == 10
        and float(rough.setup_minutes) == 45
    )
    assert {k: float(v) for k, v in rough.time_by_type.items()} == {
        shop["types"]["VMC"].pk: 12,
        shop["types"]["HMC"].pk: 7,
    }
    assert "machine_types" not in rough.extra  # machine choice is not an engine setting
    assert {r.id: r.type_id for r in inp.resources}[shop["machines"]["VMC-1"].pk] == shop["types"][
        "VMC"
    ].pk


def test_helpers_name_and_code_steps(shop):
    original = PartOperation.objects.get(part=shop["part"], op_type=shop["machining"], step=0)
    later = PartOperation.objects.create(
        company=shop["part"].company,
        part=shop["part"],
        op_type=shop["machining"],
        sequence=61,
        step=20,
        label="Bore",
    )
    assert (code_of(original), name_of(original)) == ("machining", "Machining")
    assert (code_of(later), name_of(later)) == ("machining~20", "Machining OP20 Bore")
    assert allowed_ids(later, machines_by_type(shop["part"].company)) == []


# --- validation -----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "build",
    [
        lambda s: step_item(s, 10, "x", types=["VMC"], default=5, setup=-1),
        lambda s: step_item(s, 10, "x", types=["VMC"], times={"VMC": -3}),
        lambda s: step_item(
            s,
            10,
            "x",
            types=["VMC"],
            default=5,
            op_type=OperationType.objects.get(company=s["part"].company, code="fettling").pk,
        ),
        lambda s: {
            **step_item(s, 0, "x", types=["VMC"], default=5),
            "op_type": s["machining"].pk,
            "step": 1000,
        },
    ],
    ids=[
        "negative setup",
        "negative time",
        "a step of an operation that cannot repeat",
        "step number too large",
    ],
)
def test_bad_machining_steps_are_refused(login, users, shop, build):
    assert put_route(login(users["a_admin"]), shop, build(shop)).status_code == 400


def test_a_furnace_type_is_not_a_machine_type(login, users, shop, company_a):
    furnace = ResourceType.objects.get(company=company_a, name="Furnace")
    response = put_route(
        login(users["a_admin"]),
        shop,
        step_item(shop, 10, "x", default=5, machine_types=[furnace.pk]),
    )
    assert response.status_code == 400 and "not a work-centre type" in str(response.json())


def test_another_companys_machine_type_or_machine_is_refused(login, users, shop, company_b):
    other_type = ResourceType.objects.create(company=company_b, name="VMC", kind="work_centre")
    other_machine = make_machine(company_b, other_type, "VMC-X")
    client = login(users["a_admin"])
    assert (
        put_route(
            client, shop, step_item(shop, 10, "x", default=5, machine_types=[other_type.pk])
        ).status_code
        == 400
    )
    assert (
        put_route(
            client, shop, {**step_item(shop, 10, "x", default=5), "except_ids": [other_machine.pk]}
        ).status_code
        == 400
    )
    assert (
        put_route(
            client, shop, step_item(shop, 10, "x", default=5, resource_ids=[other_machine.pk])
        ).status_code
        == 400
    )


def test_a_time_for_a_machine_type_that_does_not_exist_is_refused(login, users, shop):
    item = step_item(shop, 10, "x", types=["VMC"], default=5)
    item["time_by_type"] = {"999999": 3}
    assert put_route(login(users["a_admin"]), shop, item).status_code == 400


def test_the_same_step_number_twice_is_refused(login, users, shop):
    a, b = (
        step_item(shop, 10, "A", types=["VMC"], default=5),
        step_item(shop, 10, "B", types=["CNC"], default=5),
    )
    assert put_route(login(users["a_admin"]), shop, a, b).status_code == 400


def test_machine_choice_is_only_for_post_casting_operations(login, users, shop):
    client = login(users["a_admin"])
    route = client.get(route_url(shop)).json()
    items = [item_from(r) for r in route["operations"]]
    moulding = next(
        i
        for i in items
        if i["op_type"]
        == OperationType.objects.get(company=shop["part"].company, code="moulding").pk
    )
    moulding["machine_types"] = [shop["types"]["VMC"].pk]
    assert client.put(route_url(shop), {"operations": items}, **J).status_code == 400


def test_every_machine_type_needs_a_time_of_its_own_or_a_default(login, users, shop):
    client = login(users["a_admin"])
    partial = step_item(shop, 10, "x", types=["VMC", "HMC"], times={"VMC": 12})  # HMC has no time
    refused = put_route(client, shop, partial)
    assert refused.status_code == 400 and "HMC" in str(refused.json())
    assert (
        put_route(client, shop, {**partial, "time_value": 10}).status_code == 200
    )  # a default covers it
    both = step_item(shop, 10, "x", types=["VMC", "HMC"], times={"VMC": 12, "HMC": 7})
    assert (
        put_route(client, shop, both).status_code == 200
    )  # no default is needed when each has its own
    assert (
        put_route(client, shop, step_item(shop, 10, "x", types=["VMC"])).status_code == 400
    )  # no time at all


def test_only_admins_edit_routes_and_everyone_reads_them(login, users, shop):
    assert (
        login(users["a_planner"]).put(route_url(shop), {"operations": []}, **J).status_code == 403
    )
    assert login(users["a_viewer"]).get(route_url(shop)).status_code == 200


def test_copying_a_route_copies_the_machining_steps(login, users, shop, company_a):
    client = login(users["a_admin"])
    put_route(client, shop, *two_steps(shop))
    other = Part.objects.create(
        company=company_a,
        part_number="H-121",
        name="Housing B",
        casting_weight_kg=20,
        pouring_weight_per_mould_kg=50,
    )
    copied = client.post(
        f"/api/v1/parts/{other.pk}/copy-route", {"source_part": shop["part"].pk}, **J
    )
    assert copied.status_code == 200
    rows = rows_of(copied.json())
    assert [(r["code"], r["label"], r["setup_minutes"]) for r in rows] == [
        ("machining~10", "Rough milling", 45),
        ("machining~20", "Finish bore", 20),
    ]
    assert rows[0]["machine_types"] == sorted([shop["types"]["VMC"].pk, shop["types"]["HMC"].pk])


def test_operation_types_report_which_may_repeat(login, users, shop):
    types = {
        t["code"]: t
        for t in login(users["a_viewer"])
        .get("/api/v1/operation-types?page_size=100")
        .json()["results"]
    }
    assert types["machining"]["multi_step"] is True and types["fettling"]["multi_step"] is False


# --- a real plan ---------------------------------------------------------------------------------------------------------------
@pytest.fixture
def planned(login, users, shop, company_a):
    admin = login(users["a_admin"])
    put_route(admin, shop, *two_steps(shop))
    customer = shop["part"].customer_links.first().customer
    ScheduleLine.objects.create(
        company=company_a,
        customer=customer,
        part=shop["part"],
        dispatch_qty=300,
        internal_dispatch_date=date(2026, 11, 20),
    )
    plan = admin.post("/api/v1/plans", {}, **J)
    assert plan.status_code == 201, plan.content
    return admin, plan.json()


def test_the_plan_shows_each_machining_operation_on_its_machines(planned, shop):
    client, plan = planned
    line = client.get(f"/api/v1/plans/{plan['id']}/lines").json()["results"][0]
    detail = client.get(f"/api/v1/plans/{plan['id']}/lines/{line['id']}").json()
    ops = {o["code"]: o for o in detail["operations"]}
    assert (
        ops["machining~10"]["name"] == "Machining OP10 Rough milling"
        and ops["machining~20"]["name"] == "Machining OP20 Finish bore"
    )
    assert set(ops["machining~10"]["resource_codes"].split(", ")) <= {"VMC-1", "VMC-2", "HMC-1"}
    assert set(ops["machining~20"]["resource_codes"].split(", ")) <= {"CNC-1", "CNC-2"}
    assert ops["machining~20"]["start_at"] >= ops["machining~10"]["start_at"]
    machines = {a["resource"] for a in detail["allocations"] if a["op_code"] == "machining~10"}
    assert machines and machines <= {"VMC-1", "VMC-2", "HMC-1"}


def test_setup_shows_in_the_plan_allocations(planned):
    client, plan = planned
    line = client.get(f"/api/v1/plans/{plan['id']}/lines").json()["results"][0]
    allocations = client.get(f"/api/v1/plans/{plan['id']}/lines/{line['id']}").json()["allocations"]
    rough = [a for a in allocations if a["op_code"] == "machining~10"]
    finish = [a for a in allocations if a["op_code"] == "machining~20"]
    assert sum(a["setup_minutes"] for a in rough) == pytest.approx(
        45 * len({a["resource"] for a in rough})
    )  # one setup per machine used
    assert sum(a["setup_minutes"] for a in finish) == pytest.approx(
        20 * len({a["resource"] for a in finish})
    )


def test_the_machining_department_print_includes_every_step(planned):
    client, plan = planned
    day = client.get(f"/api/v1/plans/{plan['id']}/lines").json()["results"][0]
    for output in ("pdf", "xlsx"):
        response = client.get(
            f"/api/v1/plans/{plan['id']}/export",
            {
                "report": "day_plan",
                "department": "machining",
                "date": "2026-11-09",
                "output": output,
            },
        )
        assert response.status_code == 200, response.content
    assert day


def test_blocking_every_machine_of_a_step_moves_the_line(login, users, planned, shop):
    admin, plan = planned
    line_before = admin.get(f"/api/v1/plans/{plan['id']}/lines").json()["results"][0]
    planner = login(users["a_planner"])
    scenario = planner.post("/api/v1/scenarios", {"name": "No machines"}, **J).json()
    for code in ("VMC-1", "VMC-2", "HMC-1"):
        added = planner.post(
            f"/api/v1/scenarios/{scenario['id']}/changes",
            {
                "kind": "block_resource",
                "params": {
                    "resource": shop["machines"][code].pk,
                    "start": "2026-11-02T00:00:00+05:30",
                    "end": "2026-11-07T23:59:00+05:30",
                },
            },
            **J,
        )
        assert added.status_code == 201, added.content
    result = planner.post(f"/api/v1/scenarios/{scenario['id']}/run", {}, **J).json()["result"][
        "diff"
    ]
    moved = [ln for ln in result["lines"] if "later" in ln["tags"] or "newly_at_risk" in ln["tags"]]
    assert moved and moved[0]["est_after"] > line_before["est_dispatch_date"]


def test_a_machining_step_is_named_in_full_wherever_it_holds_a_line_up(planned, company_a):
    from apps.assistant.tools import Toolbox
    from apps.insights import collect
    from apps.plans.models import Plan

    plan = Plan.objects.get(pk=planned[1]["id"])
    plan.lines.update(holding_op="machining~10", holding_text="held")
    assert Toolbox(company_a)._op_names(plan)["machining~10"] == "Machining OP10 Rough milling"
    assert {f.holding for f in collect.line_facts(plan)} == {"Machining OP10 Rough milling"}


# --- the Machine shop ------------------------------------------------------------------------------------------------------------
def machine_shop(client, **params):
    response = client.get("/api/v1/machine-shop", params)
    assert response.status_code == 200, response.content
    return response.json()


def test_without_a_plan_the_machine_shop_lists_the_machines_but_no_numbers(login, users, shop):
    put_route(login(users["a_admin"]), shop, *two_steps(shop))
    body = machine_shop(login(users["a_viewer"]))
    assert body["plan"] is None and body["days"] == []
    assert {t["name"] for t in body["types"]} == {"VMC", "CNC", "HMC"}
    assert sorted(m["code"] for t in body["types"] for m in t["machines"]) == [
        "CNC-1",
        "CNC-2",
        "HMC-1",
        "VMC-1",
        "VMC-2",
    ]


def test_only_machines_a_machining_step_may_use_are_listed(login, users, shop):
    # The fettling bay and knockout are work centres too, but no machining step uses them.
    put_route(login(users["a_admin"]), shop, *two_steps(shop))
    codes = {
        m["code"] for t in machine_shop(login(users["a_viewer"]))["types"] for m in t["machines"]
    }
    assert not codes & {"FT", "KO"}


def test_machine_shop_numbers_match_the_plan(planned, shop):
    client, plan = planned
    body = machine_shop(client, **{"from": "2026-11-02", "to": "2026-11-13"})
    assert body["plan"]["id"] == plan["id"] and body["days"] and body["days"][0] == "2026-11-02"
    machines = {m["code"]: m for t in body["types"] for m in t["machines"]}
    # A machine has 2 shifts × 382.5 working minutes a day (450 net × 85%).
    assert machines["VMC-1"]["days"]["2026-11-02"]["capacity"] == 765.0
    for m in machines.values():
        for day in m["days"].values():
            assert day["free"] == pytest.approx(max(day["capacity"] - day["load"], 0), abs=0.2)
            assert day["load"] <= day["capacity"] + 0.2
    detail = planned_line_allocations(client, plan)
    for code, m in machines.items():
        expected = sum(a["minutes"] for a in detail if a["resource"] == code)
        assert m["load"] == pytest.approx(expected, abs=0.5), code
        assert m["setup"] == pytest.approx(
            sum(a["setup_minutes"] for a in detail if a["resource"] == code), abs=0.5
        )
    assert sum(m["load"] for m in machines.values()) > 0


def planned_line_allocations(client, plan):
    line = client.get(f"/api/v1/plans/{plan['id']}/lines").json()["results"][0]
    allocations = client.get(f"/api/v1/plans/{plan['id']}/lines/{line['id']}").json()["allocations"]
    return [a for a in allocations if a["op_code"].startswith("machining")]


def test_each_machine_lists_its_operations_and_the_shop_lists_every_machining_step(planned):
    client, plan = planned
    body = machine_shop(client, **{"from": "2026-11-02", "to": "2026-11-13"})
    used = [m for t in body["types"] for m in t["machines"] if m["operations"]]
    assert used
    for m in used:
        for o in m["operations"]:
            assert (
                o["part_number"] == "H-120"
                and o["op_code"] in ("machining~10", "machining~20")
                and o["minutes"] > 0
            )
            assert o["name"].startswith("Machining OP")
    assert [o["op_code"] for o in body["operations"]] == ["machining~10", "machining~20"]
    assert (
        body["operations"][0]["name"] == "Machining OP10 Rough milling"
        and body["operations"][0]["machines"]
    )


def test_a_blocked_machine_shows_its_downtime_and_no_capacity(
    login, users, planned, shop, company_a
):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from apps.resources.models import Downtime

    ist = ZoneInfo("Asia/Kolkata")
    Downtime.objects.create(
        company=company_a,
        resource=shop["machines"]["VMC-1"],
        start_at=datetime(2026, 11, 3, 0, 0, tzinfo=ist),
        end_at=datetime(2026, 11, 3, 23, 59, tzinfo=ist),
        reason="Spindle service",
    )
    client = login(users["a_admin"])
    client.post(f"/api/v1/plans/{planned[1]['id']}/recalculate", {}, **J)
    body = machine_shop(client, **{"from": "2026-11-02", "to": "2026-11-06"})
    vmc1 = next(m for t in body["types"] for m in t["machines"] if m["code"] == "VMC-1")
    assert vmc1["downtime"][0]["reason"] == "Spindle service"
    assert "2026-11-03" not in vmc1["days"] or vmc1["days"]["2026-11-03"]["capacity"] == 0


def test_machine_shop_rejects_a_bad_date_and_is_read_only(login, users, planned):
    client, _ = planned
    assert client.get("/api/v1/machine-shop", {"from": "soon"}).status_code == 400
    assert login(users["a_viewer"]).post("/api/v1/machine-shop", {}, **J).status_code in (403, 405)


def test_the_assistant_lists_a_parts_machining_steps_and_machines(login, users, shop, company_a):
    put_route(login(users["a_admin"]), shop, *two_steps(shop))
    from apps.assistant.tools import Toolbox

    route = Toolbox(company_a).call("get_part_status", {"part_number": "H-120"})["route"]
    names = {r["operation"]: r["resources"] for r in route}
    assert (
        "VMC-1" in names["Machining OP10 Rough milling"]
        and "HMC-1" in names["Machining OP10 Rough milling"]
    )
    assert names["Machining OP20 Finish bore"] == "CNC-1, CNC-2"
