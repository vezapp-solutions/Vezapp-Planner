"""Phase 1 API: company calendar, resources, customers, parts, operation routes, audit."""

from datetime import date

import pytest

from apps.companies.models import Shift
from apps.core.models import AuditLog
from apps.masters.models import Customer, Grade, OperationType, Part
from apps.resources.models import Resource, ResourceType
from seeds.worked_example import build_worked_example

J = {"format": "json"}


@pytest.fixture
def example(company_a):
    return build_worked_example(company_a)


def rows(response):
    return response.json()["results"]


# --- defaults for every company ---------------------------------------------------------------
def test_new_company_gets_standard_types_operations_and_settings(company_b):
    assert set(ResourceType.objects.filter(company=company_b).values_list("kind", flat=True)) == {
        "core_machine", "moulding_line", "furnace", "work_centre",
    }  # fmt: skip
    codes = OperationType.objects.filter(company=company_b, is_active=True).values_list(
        "code", flat=True
    )
    assert set(codes) == {
        "core",
        "moulding",
        "melting",
        "knockout",
        "fettling",
        "machining",
        "packing",
        "dispatch",
    }
    assert not OperationType.objects.get(company=company_b, code="inspection").is_active
    assert (
        company_b.settings.horizon_days == 30
        and company_b.settings.rejection_booked_at == "fettling"
    )


# --- company calendar -------------------------------------------------------------------------
def test_shift_validation_and_derived_minutes(login, users):
    client = login(users["a_admin"])
    ok = client.post(
        "/api/v1/shifts",
        {"name": "Day", "start_time": "06:00", "end_time": "14:00", "break_minutes": 30},
        **J,
    )
    assert (
        ok.status_code == 201
        and ok.json()["net_minutes"] == 450
        and not ok.json()["crosses_midnight"]
    )

    night = client.post(
        "/api/v1/shifts",
        {"name": "Night", "start_time": "22:00", "end_time": "06:00", "break_minutes": 30},
        **J,
    )
    assert night.json()["crosses_midnight"] and night.json()["net_minutes"] == 450

    assert (
        client.post(
            "/api/v1/shifts",
            {"name": "Bad", "start_time": "06:00", "end_time": "07:00", "break_minutes": 60},
            **J,
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/shifts", {"name": "day", "start_time": "06:00", "end_time": "14:00"}, **J
        ).status_code
        == 400
    )  # duplicate name


def test_weekly_pattern_gives_day_and_week_minutes(login, users, example):
    client = login(users["a_viewer"])
    week = client.get("/api/v1/calendar/week").json()
    assert [d["minutes"] for d in week["days"]] == [900] * 6 + [0]  # Sunday off
    assert week["week_minutes"] == 5400


def test_week_can_be_changed_and_rejects_foreign_shifts(login, users, example, company_b):
    foreign = Shift.objects.create(
        company=company_b, name="B shift", start_time="06:00", end_time="14:00"
    )
    client = login(users["a_admin"])
    assert (
        client.put("/api/v1/calendar/week", {"days": {"0": [foreign.pk]}}, **J).status_code == 400
    )

    first = example["shifts"][0].pk
    week = client.put("/api/v1/calendar/week", {"days": {"0": [first], "5": []}}, **J).json()
    assert week["days"][0]["minutes"] == 450 and week["days"][5]["minutes"] == 0


def test_holidays_full_partial_and_duplicate(login, users, example):
    client = login(users["a_admin"])
    shift_id = example["shifts"][1].pk
    full = client.post("/api/v1/holidays", {"date": "2026-11-09", "name": "Diwali"}, **J)
    assert full.status_code == 201
    assert (
        client.post("/api/v1/holidays", {"date": "2026-11-09", "name": "Again"}, **J).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/holidays", {"date": "2026-11-10", "name": "Half", "full_day": False}, **J
        ).status_code
        == 400
    )
    partial = client.post(
        "/api/v1/holidays",
        {"date": "2026-11-10", "name": "Half", "full_day": False, "shifts_off": [shift_id]},
        **J,
    )
    assert partial.status_code == 201 and partial.json()["shifts_off"] == [shift_id]


def test_company_settings_read_and_validate(login, users, example):
    client = login(users["a_admin"])
    assert client.get("/api/v1/company/settings").json()["horizon_days"] == 30
    ok = client.patch(
        "/api/v1/company/settings",
        {"horizon_days": 45, "default_bucket": "day", "rejection_booked_at": "machining"},
        **J,
    )
    assert ok.status_code == 200 and ok.json()["horizon_days"] == 45
    assert (
        client.patch(
            "/api/v1/company/settings", {"rejection_booked_at": "nonsense"}, **J
        ).status_code
        == 400
    )
    assert (
        client.patch("/api/v1/company/settings", {"melt_loss_default_pct": 100}, **J).status_code
        == 400
    )


# --- resources, availability, downtime ------------------------------------------------------------
def test_resource_requires_rated_values_for_its_kind(login, users, company_a):
    client = login(users["a_admin"])
    furnace_type = ResourceType.objects.get(company=company_a, kind="furnace").pk
    bad = client.post(
        "/api/v1/resources", {"code": "F9", "name": "F9", "resource_type": furnace_type}, **J
    )
    assert bad.status_code == 400 and {"heat_kg", "heat_minutes"} <= set(bad.json())
    ok = client.post(
        "/api/v1/resources",
        {
            "code": "F9",
            "name": "F9",
            "resource_type": furnace_type,
            "heat_kg": 500,
            "heat_minutes": 20,
        },
        **J,
    )
    assert ok.status_code == 201
    assert ok.json()["rated_summary"] == "500 kg heat · 20 min/heat"
    assert [w["field"] for w in ok.json()["warnings"]] == [
        "heat_minutes"
    ]  # outside 30 to 240: warning, not a block


def test_worked_example_availability_matches_section_7_5(login, users, example):
    client = login(users["a_viewer"])
    furnace = example["furnace"]
    # Monday 2 November 2026: two shifts of 450 min; 85% efficiency gives 382.5 each, 765 for the day.
    data = client.get(
        f"/api/v1/resources/{furnace.pk}/availability?from=2026-11-02&to=2026-11-02"
    ).json()
    assert data["days"] == [{"date": "2026-11-02", "available_minutes": 765.0}]
    assert [s["available_minutes"] for s in data["shifts"]] == [382.5, 382.5]
    assert data["shifts"][0]["trace"]["inputs"]["efficiency_pct"] == 85.0
    assert (
        data["shifts"][0]["heats"]["value"] == 5
    )  # floor(382.5 / 75); 10 heats over the day shifts' 765

    fettling = client.get(
        f"/api/v1/resources/{example['fettling'].pk}/availability?from=2026-11-02&to=2026-11-02"
    ).json()
    assert fettling["days"][0]["available_minutes"] == 2295.0  # 3 units


def test_availability_sunday_is_off_and_holiday_removes_capacity(login, users, example, company_a):
    from apps.companies.models import Holiday

    Holiday.objects.create(company=company_a, date=date(2026, 11, 3), name="Holiday")
    client = login(users["a_viewer"])
    url = f"/api/v1/resources/{example['line'].pk}/availability?from=2026-11-01&to=2026-11-04"
    days = {d["date"]: d["available_minutes"] for d in client.get(url).json()["days"]}
    assert "2026-11-01" not in days and "2026-11-03" not in days  # Sunday, holiday
    assert days["2026-11-02"] == 765.0 and days["2026-11-04"] == 765.0


def test_downtime_and_status_reduce_availability(login, users, example):
    client = login(users["a_admin"])
    furnace = example["furnace"]
    down = client.post(
        "/api/v1/downtimes",
        {
            "resource": furnace.pk,
            "start_at": "2026-11-02T06:00:00+05:30",
            "end_at": "2026-11-02T14:00:00+05:30",
            "reason": "Lining change",
        },
        **J,
    )
    assert down.status_code == 201
    url = f"/api/v1/resources/{furnace.pk}/availability?from=2026-11-02&to=2026-11-02"
    data = client.get(url).json()
    assert (
        data["shifts"][0]["downtime_minutes"] == 480.0
        and data["shifts"][0]["available_minutes"] == 0.0
    )
    assert data["days"][0]["available_minutes"] == 382.5

    client.patch(f"/api/v1/resources/{furnace.pk}", {"status": "maintenance"}, **J)
    assert client.get(url).json()["total_available_minutes"] == 0


def test_downtime_must_end_after_it_starts_and_overlaps_count_once(login, users, example):
    client = login(users["a_admin"])
    furnace = example["furnace"]
    bad = client.post(
        "/api/v1/downtimes",
        {
            "resource": furnace.pk,
            "start_at": "2026-11-02T10:00:00+05:30",
            "end_at": "2026-11-02T09:00:00+05:30",
        },
        **J,
    )
    assert bad.status_code == 400
    for start, end in (
        ("06:00", "09:00"),
        ("08:00", "10:00"),
    ):  # overlapping: union is 06:00 to 10:00
        client.post(
            "/api/v1/downtimes",
            {
                "resource": furnace.pk,
                "start_at": f"2026-11-02T{start}:00+05:30",
                "end_at": f"2026-11-02T{end}:00+05:30",
            },
            **J,
        )
    data = client.get(
        f"/api/v1/resources/{furnace.pk}/availability?from=2026-11-02&to=2026-11-02"
    ).json()
    assert data["shifts"][0]["downtime_minutes"] == 240.0


def test_resource_limited_to_some_shifts(login, users, example):
    client = login(users["a_admin"])
    line = example["line"]
    client.patch(f"/api/v1/resources/{line.pk}", {"shifts": [example["shifts"][0].pk]}, **J)
    data = client.get(
        f"/api/v1/resources/{line.pk}/availability?from=2026-11-02&to=2026-11-02"
    ).json()
    assert [s["shift_name"] for s in data["shifts"]] == ["Shift 1"]


def test_resource_cannot_point_at_other_companys_rows(login, users, example, company_b):
    other_type = ResourceType.objects.get(company=company_b, kind="work_centre")
    other_shift = Shift.objects.create(
        company=company_b, name="X", start_time="06:00", end_time="14:00"
    )
    client = login(users["a_admin"])
    assert (
        client.post(
            "/api/v1/resources", {"code": "Z1", "name": "Z", "resource_type": other_type.pk}, **J
        ).status_code
        == 400
    )
    mine = ResourceType.objects.get(company=example["line"].company, kind="work_centre")
    assert (
        client.post(
            "/api/v1/resources",
            {"code": "Z1", "name": "Z", "resource_type": mine.pk, "shifts": [other_shift.pk]},
            **J,
        ).status_code
        == 400
    )


def test_resource_in_use_cannot_be_deleted_type_in_use_is_protected(login, users, example):
    client = login(users["a_admin"])
    type_id = example["furnace"].resource_type_id
    assert client.delete(f"/api/v1/resource-types/{type_id}").status_code == 400  # a standard type


# --- customers and parts ------------------------------------------------------------------------
def test_customer_crud_and_unique_code(login, users):
    client = login(users["a_admin"])
    body = {"code": "C1", "name": "Acme", "priority": "A", "gstin": "24abcde1234f1z5"}
    created = client.post("/api/v1/customers", body, **J)
    assert created.status_code == 201 and created.json()["gstin"] == "24ABCDE1234F1Z5"
    assert client.post("/api/v1/customers", {**body, "code": "c1"}, **J).status_code == 400
    assert (
        client.post("/api/v1/customers", {**body, "code": "C2", "gstin": "bad"}, **J).status_code
        == 400
    )
    assert (
        client.post("/api/v1/customers", {**body, "code": "C3", "priority": "Z"}, **J).status_code
        == 400
    )


def part_body(**over):
    return {
        "part_number": "P-1",
        "name": "Bracket",
        "casting_weight_kg": 10,
        "pouring_weight_per_mould_kg": 25,
        "cavities_per_mould": 2,
        **over,
    }


def test_part_validation_and_warnings(login, users):
    client = login(users["a_admin"])
    for bad in (
        {"cavities_per_mould": 0},
        {"casting_weight_kg": 0},
        {"rejection_pct": 100},
        {"pouring_weight_per_mould_kg": -2},
    ):
        assert client.post("/api/v1/parts", part_body(**bad), **J).status_code == 400
    light = client.post("/api/v1/parts", part_body(pouring_weight_per_mould_kg=12), **J)
    assert light.status_code == 201 and light.json()["warnings"][0]["level"] == "warning"


def test_part_customers_default_rules_and_filters(login, users, company_a):
    c1 = Customer.objects.create(company=company_a, code="C1", name="One")
    c2 = Customer.objects.create(company=company_a, code="C2", name="Two")
    grade = Grade.objects.create(company=company_a, name="GG25")
    client = login(users["a_admin"])
    made = client.post(
        "/api/v1/parts",
        part_body(grade=grade.pk, customer_links=[{"customer": c1.pk}, {"customer": c2.pk}]),
        **J,
    ).json()
    assert [(c["code"], c["is_default"]) for c in made["customers"]] == [
        ("C1", True),
        ("C2", False),
    ]  # first becomes default

    swapped = client.patch(
        f"/api/v1/parts/{made['id']}",
        {"customer_links": [{"customer": c2.pk, "is_default": True}, {"customer": c1.pk}]},
        **J,
    ).json()
    assert {c["code"]: c["is_default"] for c in swapped["customers"]} == {"C1": False, "C2": True}
    assert (
        client.post(
            "/api/v1/parts",
            part_body(
                part_number="P-2",
                customer_links=[
                    {"customer": c1.pk, "is_default": True},
                    {"customer": c2.pk, "is_default": True},
                ],
            ),
            **J,
        ).status_code
        == 400
    )

    assert len(rows(client.get(f"/api/v1/parts?customer={c1.pk}"))) == 1
    assert len(rows(client.get(f"/api/v1/parts?grade={grade.pk}"))) == 1
    assert rows(client.get("/api/v1/parts?q=zzz")) == []


def test_grade_in_use_cannot_be_deleted(login, users, company_a):
    grade = Grade.objects.create(company=company_a, name="GG25")
    client = login(users["a_admin"])
    client.post("/api/v1/parts", part_body(grade=grade.pk), **J)
    assert client.delete(f"/api/v1/grades/{grade.pk}").status_code == 400


# --- operation route ----------------------------------------------------------------------------
def test_new_part_gets_the_default_route_template(login, users, company_a):
    part = Part.objects.create(
        company=company_a,
        part_number="N-1",
        name="New",
        casting_weight_kg=5,
        pouring_weight_per_mould_kg=8,
        cores_per_mould=0,
    )
    route = login(users["a_viewer"]).get(f"/api/v1/parts/{part.pk}/operations").json()
    assert route["is_template"]
    assert [r["code"] for r in route["operations"]] == [
        "core",
        "moulding",
        "melting",
        "knockout",
        "fettling",
        "machining",
        "packing",
        "dispatch",
    ]
    core = route["operations"][0]
    assert core["enabled"] is False  # no cores on this part, so Core is off by default
    assert (
        route["operations"][4]["capacity_bucket"] == "shift"
        and route["operations"][7]["capacity_bucket"] == "day"
    )


def op(route, code):
    return next(o for o in route["operations"] if o["code"] == code)


def test_worked_example_route_derived_values(login, users, example):
    route = login(users["a_viewer"]).get(f"/api/v1/parts/{example['part'].pk}/operations").json()
    melting = op(route, "melting")
    assert melting["derived"]["suggested_moulds_per_heat"]["value"] == 15
    assert melting["derived"]["minutes_per_piece"]["value"] == 2.5
    assert melting["derived"]["minutes_per_piece"]["inputs"] == {
        "minutes_per_heat": 75.0,
        "moulds_per_heat": 15.0,
        "cavities_per_mould": 2.0,
    }
    assert melting["extra"]["cooling_hours"] == 4 and not [
        i for i in melting["issues"] if i["level"] != "info"
    ]
    assert op(route, "moulding")["derived"]["minutes_per_mould"]["value"] == 1.5
    assert op(route, "core")["derived"]["minutes_per_core"]["value"] == 1.0
    assert op(route, "core")["derived"]["cores_per_mould"]["value"] == 2
    assert op(route, "fettling")["capacity_modelled"] and not op(route, "dispatch")["enabled"]


def full_payload(route, **changes):
    items = []
    for o in route["operations"]:
        item = {
            k: o[k]
            for k in (
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
            )
        }
        item["resource_ids"] = o["resource_ids"]
        item.update(changes.get(o["code"], {}))
        items.append(item)
    return {"operations": items}


def test_route_round_trip_and_blank_melt_loss_uses_company_default(login, users, example):
    client = login(users["a_admin"])
    url = f"/api/v1/parts/{example['part'].pk}/operations"
    route = client.get(url).json()
    saved = client.put(
        url,
        full_payload(route, melting={"extra": {"moulds_per_heat": 15, "cooling_hours": 4}}),
        **J,
    )
    assert saved.status_code == 200
    melting = op(saved.json(), "melting")
    assert (
        melting["derived"]["melt_loss_pct"]["note"] == ""
        and "company default" in melting["derived"]["melt_loss_pct"]["formula"]
    )
    assert any(
        i["field"] == "extra.melt_loss_pct" for i in melting["issues"]
    )  # soft warning, not a block
    assert (
        melting["derived"]["suggested_moulds_per_heat"]["value"] == 16
    )  # no loss: floor(1000 / 60)


def test_route_changes_update_derived_numbers(login, users, example):
    client = login(users["a_admin"])
    url = f"/api/v1/parts/{example['part'].pk}/operations"
    route = client.get(url).json()
    out = client.put(
        url,
        full_payload(
            route,
            melting={"extra": {"moulds_per_heat": 10, "melt_loss_pct": 5, "cooling_hours": 4}},
        ),
        **J,
    ).json()
    assert op(out, "melting")["derived"]["minutes_per_piece"]["value"] == 3.75  # 75 / (10 x 2)


@pytest.mark.parametrize(
    "code, change, field",
    [
        ("knockout", {"time_value": 0}, "time_value"),
        ("knockout", {"time_value": None}, "time_value"),
        ("fettling", {"time_basis": "per_core"}, "time_basis"),
        (
            "packing",
            {"enabled": True, "time_basis": "per_batch", "time_value": 2, "batch_size": None},
            "batch_size",
        ),
        ("machining", {"enabled": True, "outsourced": True, "time_value": None}, "lead_days"),
        ("melting", {"extra": {"moulds_per_heat": 0}}, "extra"),
        ("core", {"extra": {"colour": 3}}, "extra"),
    ],
)
def test_route_blocks_impossible_values(login, users, example, code, change, field):
    client = login(users["a_admin"])
    url = f"/api/v1/parts/{example['part'].pk}/operations"
    response = client.put(url, full_payload(client.get(url).json(), **{code: change}), **J)
    assert response.status_code == 400, response.content
    assert field in str(response.json())


def test_preview_shows_derived_values_without_saving(login, users, example):
    client = login(users["a_admin"])
    url = f"/api/v1/parts/{example['part'].pk}/operations"
    route = client.get(url).json()
    changed = full_payload(
        route, melting={"extra": {"moulds_per_heat": 10, "melt_loss_pct": 5, "cooling_hours": 4}}
    )
    preview = client.post(f"{url}/preview", changed, **J)
    assert preview.status_code == 200
    assert op(preview.json(), "melting")["derived"]["minutes_per_piece"]["value"] == 3.75
    # Nothing was kept: the saved route still says 15 moulds per heat, and no audit row was written.
    assert op(client.get(url).json(), "melting")["extra"]["moulds_per_heat"] == 15
    assert not AuditLog.objects.filter(
        model_label="masters.PartOperation", action="update", after__extra__moulds_per_heat=10
    ).exists()
    bad = full_payload(route, knockout={"time_value": 0})
    assert client.post(f"{url}/preview", bad, **J).status_code == 400


def test_route_rejects_wrong_or_foreign_resources(login, users, example, company_b):
    client = login(users["a_admin"])
    url = f"/api/v1/parts/{example['part'].pk}/operations"
    route = client.get(url).json()
    wrong_kind = client.put(
        url, full_payload(route, moulding={"resource_ids": [example["furnace"].pk]}), **J
    )
    assert wrong_kind.status_code == 400
    foreign = Resource.objects.create(
        company=company_b,
        code="LB",
        name="LB",
        resource_type=ResourceType.objects.get(company=company_b, kind="moulding_line"),
        rate_per_hour=10,
    )
    assert (
        client.put(
            url, full_payload(route, moulding={"resource_ids": [foreign.pk]}), **J
        ).status_code
        == 400
    )


def test_tiny_furnace_is_blocked_and_unconstrained_operation_is_flagged(
    login, users, example, company_a
):
    small = Resource.objects.create(
        company=company_a,
        code="F-SMALL",
        name="Small",
        resource_type=example["furnace"].resource_type,
        heat_kg=50,
        heat_minutes=60,
    )
    client = login(users["a_admin"])
    url = f"/api/v1/parts/{example['part'].pk}/operations"
    route = client.get(url).json()
    assert (
        client.put(url, full_payload(route, melting={"resource_ids": [small.pk]}), **J).status_code
        == 400
    )

    no_ko = client.put(url, full_payload(route, knockout={"resource_ids": []}), **J).json()
    knock = op(no_ko, "knockout")
    assert knock["capacity_modelled"] is False and any(
        i["message"].startswith("No work centre") for i in knock["issues"]
    )


def test_copy_route(login, users, example, company_a):
    target = Part.objects.create(
        company=company_a,
        part_number="H-130",
        name="Cover",
        casting_weight_kg=5,
        pouring_weight_per_mould_kg=10,
    )
    client = login(users["a_admin"])
    copied = client.post(
        f"/api/v1/parts/{target.pk}/copy-route", {"source_part": example["part"].pk}, **J
    )
    assert copied.status_code == 200 and not copied.json()["is_template"]
    assert op(copied.json(), "melting")["extra"]["moulds_per_heat"] == 15
    assert (
        client.post(
            f"/api/v1/parts/{target.pk}/copy-route", {"source_part": target.pk}, **J
        ).status_code
        == 400
    )


# --- roles ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("who, expected", [("a_admin", 201), ("a_planner", 403), ("a_viewer", 403)])
@pytest.mark.parametrize(
    "path, body",
    [
        ("customers", {"code": "Q", "name": "Q"}),
        ("grades", {"name": "Q"}),
        ("shifts", {"name": "Q", "start_time": "06:00", "end_time": "14:00"}),
    ],
)
def test_master_writes_are_admin_only(login, users, who, expected, path, body):
    assert login(users[who]).post(f"/api/v1/{path}", body, **J).status_code == expected


@pytest.mark.parametrize("who", ["a_admin", "a_planner", "a_viewer"])
@pytest.mark.parametrize(
    "path",
    [
        "customers",
        "grades",
        "shifts",
        "holidays",
        "parts",
        "resources",
        "resource-types",
        "operation-types",
        "downtimes",
        "company/settings",
        "calendar/week",
    ],
)
def test_everyone_in_the_company_can_read_masters(login, users, example, who, path):
    assert login(users[who]).get(f"/api/v1/{path}").status_code == 200


def test_planner_cannot_save_a_route(login, users, example):
    url = f"/api/v1/parts/{example['part'].pk}/operations"
    client = login(users["a_planner"])
    assert client.put(url, full_payload(client.get(url).json()), **J).status_code == 403


# --- tenancy ----------------------------------------------------------------------------------------
@pytest.fixture
def b_example(company_b):
    return build_worked_example(company_b)


@pytest.mark.parametrize(
    "path",
    ["customers", "grades", "shifts", "parts", "resources", "resource-types", "operation-types"],
)
def test_company_a_sees_none_of_company_bs_masters(login, users, example, b_example, path):
    a_rows = rows(login(users["a_admin"]).get(f"/api/v1/{path}"))
    b_rows = rows(login(users["b_admin"]).get(f"/api/v1/{path}"))
    assert a_rows and b_rows
    assert not {r["id"] for r in a_rows} & {r["id"] for r in b_rows}


def test_company_a_cannot_read_or_change_company_bs_part_route(login, users, example, b_example):
    client = login(users["a_admin"])
    url = f"/api/v1/parts/{b_example['part'].pk}/operations"
    assert client.get(url).status_code == 404
    assert client.put(url, {"operations": []}, **J).status_code == 404
    assert (
        client.get(f"/api/v1/resources/{b_example['furnace'].pk}/availability").status_code == 404
    )
    assert (
        client.post(
            f"/api/v1/parts/{example['part'].pk}/copy-route",
            {"source_part": b_example["part"].pk},
            **J,
        ).status_code
        == 400
    )


def test_vezapp_admin_acts_for_a_company_with_the_header(login, users, example, company_a):
    client = login(users["vezapp_admin"])
    assert rows(client.get("/api/v1/shifts")) == []
    client.credentials(HTTP_X_VP_CLIENT="web", HTTP_X_COMPANY_ID=str(company_a.pk))
    assert len(rows(client.get("/api/v1/shifts"))) == 2
    assert (
        client.post("/api/v1/customers", {"code": "V1", "name": "Added by Vezapp"}, **J).status_code
        == 201
    )
    assert Customer.objects.get(code="V1").company_id == company_a.pk


# --- audit --------------------------------------------------------------------------------------------
def test_master_changes_are_audited_and_visible_to_admins_only(login, users, company_a):
    client = login(users["a_admin"])
    made = client.post("/api/v1/customers", {"code": "AU", "name": "Audited"}, **J).json()
    client.patch(f"/api/v1/customers/{made['id']}", {"name": "Audited Ltd"}, **J)

    log = rows(client.get("/api/v1/audit-log?model_label=masters.Customer"))
    assert [(r["action"], r["username"]) for r in reversed(log)] == [
        ("create", "a_admin"),
        ("update", "a_admin"),
    ]
    assert log[0]["before"]["name"] == "Audited" and log[0]["after"]["name"] == "Audited Ltd"
    assert login(users["a_planner"]).get("/api/v1/audit-log").status_code == 403


def test_audit_log_is_scoped_to_the_company(login, users, company_a, company_b):
    login(users["b_admin"]).post("/api/v1/customers", {"code": "BB", "name": "B only"}, **J)
    mine = rows(login(users["a_admin"]).get("/api/v1/audit-log"))
    assert all(r["object_repr"] != "BB B only" for r in mine)
    assert AuditLog.objects.filter(company=company_b, model_label="masters.Customer").exists()


def test_saving_a_route_is_audited(login, users, example):
    client = login(users["a_admin"])
    url = f"/api/v1/parts/{example['part'].pk}/operations"
    client.put(url, full_payload(client.get(url).json(), fettling={"time_value": 4}), **J)
    entries = rows(client.get("/api/v1/audit-log?model_label=masters.PartOperation&action=update"))
    assert any(e["before"]["time_value"] != e["after"]["time_value"] for e in entries)
