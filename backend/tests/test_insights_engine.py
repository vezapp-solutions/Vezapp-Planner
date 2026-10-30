"""Each insight rule against hand-built fixture data: thresholds, wording, numbers and ranking."""

from datetime import date, timedelta

import pytest

from insights import digest as dg
from insights import health, performance, plan_cards
from insights.format import fmt_date, indian, month_name, pct, plural, tonnes
from insights.model import (
    BalanceCandidate,
    Card,
    DayBottleneck,
    DispatchRow,
    FurnaceDay,
    HealthItem,
    LineFact,
    LoadRow,
    MeltRow,
)

TODAY = date(2026, 11, 10)  # a Tuesday


def line(i, status="on_track", qty=100, internal=date(2026, 11, 20), est=None, slack=3, **kw):
    base = dict(
        line_id=i, customer_code="C1", customer_name="Customer One", part_id=1, part_number="H-120",
        part_name="Housing", grade="GG25", qty=qty, internal_date=internal, status=status,
        est_date=est or (None if slack is None else internal - timedelta(days=slack)),
        slack_working_days=slack, holding="",
        holding_text="", tonnes=qty * 0.025, price=None,
    )  # fmt: skip
    base.update(kw)
    return LineFact(**base)


# --- formatting -------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value, digits, text",
    [(0, 0, "0"), (999, 0, "999"), (1000, 0, "1,000"), (100000, 0, "1,00,000"), (1234567, 0, "12,34,567"),
     (-1234567, 0, "-12,34,567"), (1234.5, 1, "1,234.5"), (12345.678, 2, "12,345.68")],
)  # fmt: skip
def test_indian_grouping(value, digits, text):
    assert indian(value, digits) == text


def test_wording_helpers():
    assert fmt_date(date(2026, 1, 5)) == "05-01-2026" and fmt_date("2026-11-02") == "02-11-2026"
    assert (
        pct(0.456) == "46%" and tonnes(2500) == "2.5 t" and month_name(2026, 11) == "November 2026"
    )
    assert (
        plural(1, "line") == "1 line"
        and plural(2, "line") == "2 lines"
        and plural(2, "day", "days") == "2 days"
    )


# --- 1. at risk ----------------------------------------------------------------------------------------
def test_at_risk_none_is_a_calm_info_card():
    cards = plan_cards.at_risk([line(1), line(2, status="tight", slack=1)])
    assert [c.key for c in cards] == ["at_risk:none"] and cards[0].severity == "info"
    assert cards[0].numbers == {"lines": 2, "at_risk": 0, "tight": 1}
    assert "1 are tight" in cards[0].message


def test_at_risk_without_lines_gives_nothing():
    assert plan_cards.at_risk([]) == []


def test_at_risk_summary_and_worst_lines():
    lines = [
        line(
            1,
            "at_risk",
            qty=300,
            slack=-4,
            est=date(2026, 11, 26),
            holding="Fettling",
            holding_text="Fettling held it up.",
        ),
        line(2, "at_risk", qty=100, slack=-1, est=date(2026, 11, 23), holding="Fettling"),
        line(3, "at_risk", qty=50, slack=-2, est=date(2026, 11, 24), holding="Knockout"),
        line(4, "at_risk", qty=20, slack=-1, est=date(2026, 11, 23), holding="Knockout"),
        line(5, "on_track", qty=500),
    ]
    cards = plan_cards.at_risk(lines)
    summary = cards[0]
    assert (
        summary.key == "at_risk:summary" and summary.severity == "critical"
    )  # worst is 4 working days late
    assert summary.numbers["lines_at_risk"] == 4 and summary.numbers["pieces_late"] == 470
    assert summary.numbers["worst_working_days_late"] == 4
    assert summary.numbers["held_up_by"] == {"Fettling": 2, "Knockout": 2}
    assert summary.entities["lines"] == [1, 3, 2, 4]  # worst first
    assert "4 working days late" in summary.message and "held up by Fettling" in summary.message
    assert [c.key for c in cards[1:]] == ["at_risk:line:1", "at_risk:line:3", "at_risk:line:2"]
    assert cards[1].severity == "critical" and cards[2].severity == "warning"
    assert "Fettling held it up." in cards[1].message


def test_at_risk_unscheduled_is_critical_and_worse_than_late():
    cards = plan_cards.at_risk(
        [
            line(1, "at_risk", slack=-1, est=date(2026, 11, 21)),
            line(2, "unscheduled", est=None, slack=None),
        ]
    )
    assert cards[0].severity == "critical" and cards[0].numbers["unscheduled"] == 1
    assert cards[1].key == "at_risk:line:2" and "not scheduled" in cards[1].title


def test_at_risk_two_days_late_is_only_a_warning():
    assert (
        plan_cards.at_risk([line(1, "at_risk", slack=-2, est=date(2026, 11, 24))])[0].severity
        == "warning"
    )


# --- 2. bottleneck forecast ----------------------------------------------------------------------------------
def days(utils, code="F1"):
    return [
        DayBottleneck(TODAY + timedelta(days=i), code if u is not None else None, u or 0.0)
        for i, u in enumerate(utils)
    ]


def test_bottleneck_forecast_names_the_busiest_resource_and_peak():
    ds = days([0.6, 1.0, 0.9, 0.3])
    ds[3] = DayBottleneck(ds[3].day, "KO", 0.3)
    (card,) = plan_cards.bottleneck_forecast(ds)
    assert card.numbers["top_resource"] == "F1" and card.numbers["days_as_busiest"] == 3
    assert card.numbers["peak_date"] == "2026-11-11" and card.numbers["days_hot"] == 2
    assert (
        card.severity == "warning"
        and "F1 is the busiest resource on 3 of the next 4 working days, peaking at 100%"
        in card.message
        and "11-11-2026" in card.message
    )


def test_bottleneck_forecast_severity_levels():
    assert plan_cards.bottleneck_forecast(days([0.5, 0.6, 0.4]))[0].severity == "info"
    assert plan_cards.bottleneck_forecast(days([0.9, 0.5]))[0].severity == "warning"
    assert plan_cards.bottleneck_forecast(days([1.0, 1.0, 1.0, 0.2]))[0].severity == "critical"


def test_bottleneck_forecast_with_nothing_planned():
    assert plan_cards.bottleneck_forecast(days([None, None])) == []
    assert plan_cards.bottleneck_forecast([]) == []


# --- 3. capacity gap ------------------------------------------------------------------------------------------------
def week_rows(rid, code, name, week_start, cap, load, req, per_day=5):
    return [
        LoadRow(
            rid,
            code,
            name,
            week_start + timedelta(days=i),
            load / per_day,
            cap / per_day,
            req / per_day,
        )
        for i in range(per_day)
    ]


def test_capacity_gap_says_how_many_extra_shifts():
    mon = date(2026, 11, 16)
    rows = week_rows(2, "FT", "Fettling", mon, cap=1000, load=1000, req=1800)
    (card, *rest) = plan_cards.capacity_gap(rows, {2: 400.0})
    assert not rest
    assert card.key == "capacity_gap:2" and card.severity == "critical"  # 80% short of capacity
    assert (
        card.numbers["weeks"][0]["extra_shifts"] == 2
        and card.numbers["weeks"][0]["shortfall"] == 800.0
    )
    assert card.message == "Fettling needs about 2 extra shifts in the week of 16-11-2026."


def test_capacity_gap_small_shortfall_is_a_warning_and_counts_other_weeks():
    mon = date(2026, 11, 2)
    rows = week_rows(2, "FT", "Fettling", mon, 1000, 1000, 1100) + week_rows(
        2, "FT", "Fettling", mon + timedelta(days=7), 1000, 900, 1050
    )
    (card,) = plan_cards.capacity_gap(rows, {2: 500.0})
    assert card.severity == "warning" and card.numbers["weeks_short"] == 2
    assert "1 other week fall short too" in card.message and card.numbers["total_extra_shifts"] == 2


def test_capacity_gap_without_shift_length_reports_hours():
    rows = week_rows(2, "FT", "Fettling", date(2026, 11, 2), 1000, 1000, 1600)
    (card,) = plan_cards.capacity_gap(rows, {})
    assert (
        "short by about 10.0 hours" in card.message
        and card.numbers["weeks"][0]["extra_shifts"] is None
    )


def test_capacity_gap_reports_spare_capacity_lowest_first_and_capped():
    mon = date(2026, 11, 2)
    rows = []
    for rid, util in enumerate([0.4, 0.3, 0.2, 0.1, 0.8], start=1):
        rows += week_rows(rid, f"R{rid}", f"Res {rid}", mon, 1000, 1000 * util, 1000 * util)
    cards = plan_cards.capacity_gap(rows, {})
    assert [c.key for c in cards] == [
        "capacity_gap:spare:4",
        "capacity_gap:spare:3",
        "capacity_gap:spare:2",
    ]
    assert cards[0].message.startswith("Res 4 is at 10%") and cards[0].severity == "info"


def test_capacity_gap_ignores_resources_with_no_work():
    assert (
        plan_cards.capacity_gap(week_rows(9, "X", "Idle", date(2026, 11, 2), 1000, 0, 0), {}) == []
    )


# --- 4. melting ------------------------------------------------------------------------------------------------------------
def test_melting_tonnes_per_grade_per_day():
    melt = [
        MeltRow(date(2026, 11, 10), "GG25", 3000),
        MeltRow(date(2026, 11, 10), "SG500", 1000),
        MeltRow(date(2026, 11, 11), "GG25", 2000),
    ]
    (card,) = plan_cards.melting(melt, [])
    assert card.key == "melting:tonnes" and card.numbers["total_tonnes"] == 6.0
    assert (
        card.numbers["by_grade"] == {"GG25": 5.0, "SG500": 1.0}
        and card.numbers["peak_day"] == "2026-11-10"
    )
    assert "4.0 t on 10-11-2026 (GG25 3.0 t, SG500 1.0 t)" in card.message
    assert "heat" not in card.message.lower()  # heats stay inside (A48)


def furnace_week(utils, code="F1", start=date(2026, 11, 2)):
    return [FurnaceDay(code, start + timedelta(days=i), u * 100, 100) for i, u in enumerate(utils)]


def test_melting_flags_uneven_furnace_load():
    cards = plan_cards.melting([], furnace_week([1.0, 1.0, 0.1, 0.2, 1.0, 0.1]))
    (card,) = cards
    assert card.key == "melting:uneven:F1" and card.severity == "warning"
    assert card.numbers["full_days"] == 3 and card.numbers["quiet_days"] == 3


def test_melting_even_or_short_load_is_not_flagged():
    assert plan_cards.melting([], furnace_week([0.8, 0.85, 0.8, 0.9, 0.82])) == []
    assert (
        plan_cards.melting([], furnace_week([1.0, 0.1, 0.1])) == []
    )  # fewer than four working days


# --- 5. load balancing --------------------------------------------------------------------------------------------------------
def candidate(**kw):
    base = dict(part_id=1, part_number="H-120", op_code="moulding", op_name="Moulding", from_id=1, from_code="LINE-A",
                from_util=1.0, to_id=2, to_code="LINE-B", to_util=0.3, pieces=500)  # fmt: skip
    base.update(kw)
    return BalanceCandidate(**base)


def test_load_balancing_suggests_the_quiet_resource_with_a_dry_run_recipe():
    (card,) = plan_cards.load_balancing([candidate()])
    assert card.key == "load_balancing:1:moulding:2" and card.severity == "warning"
    assert card.entities["dry_run"] == {"part_id": 1, "op_code": "moulding", "resource_id": 2}
    assert "LINE-A is at 100% while LINE-B is at 30%" in card.message


def test_load_balancing_needs_a_real_gap_and_is_capped_largest_first():
    assert plan_cards.load_balancing([candidate(to_util=0.9)]) == []
    many = [candidate(part_id=i, part_number=f"P{i}", pieces=i * 100) for i in range(1, 6)]
    cards = plan_cards.load_balancing(many)
    assert [c.entities["parts"][0] for c in cards] == ["P5", "P4", "P3"]


# --- 7. month forecast ---------------------------------------------------------------------------------------------------------
def test_month_forecast_counts_what_slips_into_next_month():
    lines = [
        line(1, qty=100, internal=date(2026, 11, 20), est=date(2026, 11, 18), price=10.0),
        line(
            2,
            qty=100,
            internal=date(2026, 11, 28),
            est=date(2026, 12, 2),
            price=10.0,
            status="at_risk",
            slack=-2,
        ),
        line(3, qty=100, internal=date(2026, 11, 29), est=None, status="unscheduled", slack=None),
        line(4, qty=999, internal=date(2026, 12, 3)),  # next month: out of scope
    ]
    (card,) = plan_cards.month_forecast(lines, TODAY)
    n = card.numbers
    assert (n["planned_qty"], n["forecast_qty"], n["slipping_lines"]) == (300, 100, 2)
    assert (
        n["planned_value"] == 2000.0
        and n["forecast_value"] == 1000.0
        and n["lines_without_price"] == 1
    )
    assert n["planned_tonnes"] == 7.5 and n["forecast_tonnes"] == 2.5
    assert card.severity == "critical" and card.entities["lines"] == [2, 3]
    assert "100 of 300 pieces" in card.message and "2 lines slip into next month" in card.message


def test_month_forecast_on_course_is_info():
    (card,) = plan_cards.month_forecast(
        [line(1, internal=date(2026, 11, 20), est=date(2026, 11, 18))], TODAY
    )
    assert card.severity == "info" and card.numbers["slipping_lines"] == 0


def test_month_forecast_small_shortfall_is_a_warning():
    lines = [
        line(i, qty=100, internal=date(2026, 11, 20), est=date(2026, 11, 19)) for i in range(1, 10)
    ]
    lines.append(
        line(
            10,
            qty=100,
            internal=date(2026, 11, 30),
            est=date(2026, 12, 1),
            status="at_risk",
            slack=-1,
        )
    )
    assert (
        plan_cards.month_forecast(lines, TODAY)[0].severity == "warning"
    )  # 10% short, under the 15% line


def test_month_forecast_with_no_lines_in_the_month_gives_nothing():
    assert plan_cards.month_forecast([line(1, internal=date(2026, 12, 3))], TODAY) == []


# --- 8. concentration -------------------------------------------------------------------------------------------------------------
def test_concentration_flags_one_dominant_customer():
    lines = [
        line(1, qty=800, customer_code="BIG"),
        line(2, qty=100, customer_code="B2", part_id=2),
        line(3, qty=100, customer_code="B3", part_id=3, grade="SG500"),
    ]
    (card,) = plan_cards.concentration(lines, {}, TODAY)
    assert card.key == "concentration:mix" and card.severity == "warning"
    assert card.numbers["customers"][0] == {"code": "BIG", "tonnes": 20.0, "share": 0.8}
    assert card.numbers["grades"][0]["grade"] == "GG25" and "BIG alone is 80%" in card.message


def test_concentration_balanced_mix_is_info():
    lines = [line(i, qty=100, customer_code=f"C{i}") for i in range(1, 6)]
    assert plan_cards.concentration(lines, {}, TODAY)[0].severity == "info"


def test_concentration_flags_unusually_large_lines_against_history():
    lines = [line(1, qty=1000), line(2, qty=120, part_id=2, part_number="P2")]
    history = {1: [100, 120, 90, 110], 2: [100, 120]}  # part 2 has too little history to judge
    cards = plan_cards.concentration(lines, history, TODAY)
    large = [c for c in cards if c.key.startswith("concentration:large")]
    assert [c.key for c in large] == ["concentration:large:1"]
    assert large[0].numbers["ratio"] == 9.52 and "9.5 times the usual 105" in large[0].message


def test_concentration_outside_the_month_gives_nothing():
    assert plan_cards.concentration([line(1, internal=date(2026, 12, 3))], {}, TODAY) == []


# --- 6. dispatch performance -----------------------------------------------------------------------------------------------------
def row(i, internal, actual, customer="C1", part="H-120", qty=10):
    return DispatchRow(i, customer, f"Customer {customer}", part, internal, actual, qty)


def test_on_time_and_delay_definitions():
    on_time = row(1, date(2026, 11, 5), date(2026, 11, 5))
    late = row(2, date(2026, 11, 5), date(2026, 11, 8))
    early = row(3, date(2026, 11, 5), date(2026, 11, 1))
    assert on_time.on_time and early.on_time and not late.on_time
    assert (on_time.delay_days, late.delay_days, early.delay_days) == (0, 3, 0)


def test_group_stats_by_customer_part_and_month():
    rows = [
        row(1, date(2026, 10, 5), date(2026, 10, 5), "A"), row(2, date(2026, 10, 6), date(2026, 10, 9), "A"),
        row(3, date(2026, 10, 7), date(2026, 10, 11), "A", part="P2"), row(4, date(2026, 11, 3), date(2026, 11, 2), "B"),
    ]  # fmt: skip
    cust = {s["group"]: s for s in performance.by_customer(rows)}
    assert cust["A"]["lines"] == 3 and cust["A"]["late"] == 2 and cust["A"]["on_time_pct"] == 0.3333
    assert (
        cust["A"]["avg_delay_days"] == 3.5
        and cust["A"]["max_delay_days"] == 4
        and cust["A"]["name"] == "Customer A"
    )
    assert performance.by_customer(rows)[0]["group"] == "A"  # worst first
    assert {s["group"]: s["lines"] for s in performance.by_part(rows)} == {"H-120": 3, "P2": 1}
    assert [(m["group"], m["on_time_pct"]) for m in performance.by_month(rows)] == [
        ("2026-10", 0.3333),
        ("2026-11", 1.0),
    ]


def test_dispatch_cards_overall_with_trend_and_severity():
    rows = [row(i, date(2026, 10, 5), date(2026, 10, 5)) for i in range(1, 5)]  # last month: 100%
    rows += [
        row(10 + i, date(2026, 11, 3), date(2026, 11, 3 if i < 3 else 6)) for i in range(5)
    ]  # this month: 3 of 5
    card = performance.dispatch_cards(rows, TODAY)[0]
    assert card.key == "dispatch:overall" and card.severity == "warning"  # 60% is not under 60%
    assert card.numbers["on_time_pct"] == 0.6 and card.numbers["previous_on_time_pct"] == 1.0
    assert (
        "40 points down on 100% the month before" in card.message
        and card.numbers["avg_delay_days"] == 3.0
    )


def test_dispatch_cards_critical_below_sixty_percent():
    rows = [row(i, date(2026, 11, 3), date(2026, 11, 5)) for i in range(1, 5)]
    assert performance.dispatch_cards(rows, TODAY)[0].severity == "critical"


def test_dispatch_cards_flag_repeat_offenders_only_with_enough_lines():
    rows = [row(i, date(2026, 11, 3), date(2026, 11, 6), customer="SLOW") for i in range(1, 4)]
    rows += [
        row(10 + i, date(2026, 11, 3), date(2026, 11, 6), customer="FEW") for i in range(2)
    ]  # only 2 lines
    keys = [c.key for c in performance.dispatch_cards(rows, TODAY)]
    assert (
        "dispatch:customer:SLOW" in keys
        and "dispatch:customer:FEW" not in keys
        and "dispatch:part:H-120" in keys
    )


def test_dispatch_cards_without_actuals_give_nothing():
    assert performance.dispatch_cards([], TODAY) == []


# --- 9. data health --------------------------------------------------------------------------------------------------------------------
def test_data_health_groups_by_kind_and_ranks_by_effect():
    items = [
        HealthItem(
            "no_route",
            "P1",
            "has no operations",
            "Without a route the part cannot be planned.",
            "error",
            "/masters/parts/1",
            4,
        ),
        HealthItem(
            "no_route",
            "P2",
            "has no operations",
            "Without a route the part cannot be planned.",
            "error",
            "/masters/parts/2",
            1,
        ),
        HealthItem(
            "past_due",
            "L7",
            "internal date 01-10-2026, no actual date",
            "A past date makes the line late from today.",
            "warning",
            "/scheduler",
            1,
        ),
        HealthItem(
            "unrealistic", "KO", "efficiency 5%", "Very low efficiency hides real capacity.", "info"
        ),
    ]
    cards = {c.key: c for c in health.data_health(items)}
    assert cards["data_health:no_route"].severity == "critical" and cards[
        "data_health:no_route"
    ].numbers == {"items": 2, "lines_affected": 5}
    assert (
        cards["data_health:no_route"].entities["items"][0]["subject"] == "P1"
    )  # biggest effect first
    assert (
        cards["data_health:past_due"].severity == "warning"
        and cards["data_health:unrealistic"].severity == "info"
    )
    assert cards["data_health:no_route"].why == ("Without a route the part cannot be planned.",)


def test_data_health_error_without_scheduled_lines_is_only_a_warning():
    items = [
        HealthItem(
            "route_gap", "P3 Moulding", "no time", "The step takes no time in the plan.", "error"
        )
    ]
    assert health.data_health(items)[0].severity == "warning"


def test_data_health_with_no_items_is_clean():
    assert health.data_health([]) == []


# --- ranking, trend and the digest ------------------------------------------------------------------------------------------------------
def card(key, severity="info", impact=0.0, **kw):
    return Card(
        key=key,
        type="x",
        severity=severity,
        title=key,
        message=f"msg {key}",
        action="do",
        impact=impact,
        **kw,
    )


def test_rank_is_severity_times_impact():
    assert card("a", "critical", 0).rank == 1000 and card("a", "critical", 5).rank == 6000
    assert (
        card("a", "warning", 10).rank == 550 and card("a", "info", 99).rank == 44
    )  # impact is capped at 10
    assert card("a", "warning", 9).rank > card("b", "info", 10).rank
    assert (
        card("a", "critical", 0).rank > card("b", "warning", 10).rank
    )  # a critical beats any warning


def test_ranked_orders_and_breaks_ties_by_key():
    cards = [card("b", "warning", 1), card("a", "warning", 1), card("c", "critical")]
    assert [c.key for c in dg.ranked(cards)] == ["c", "a", "b"]


def test_trend_compares_with_the_previous_run():
    prev = {"a": 4.0, "b": 4.0, "c": 4.0}
    assert dg.trend(card("new"), prev) == "new"
    assert dg.trend(card("a", impact=7.0), prev) == "worse"
    assert dg.trend(card("b", impact=1.0), prev) == "better"
    assert dg.trend(card("c", impact=4.2), prev) == "same"
    assert dg.resolved([card("a")], prev) == ["b", "c"]


def test_digest_is_the_top_five_as_text():
    cards = [card(f"k{i}", "warning", i) for i in range(8)] + [card("boss", "critical", 0)]
    d = dg.digest(cards, TODAY, "Demo Foundry")
    assert d["title"] == "Daily digest, 10-11-2026, Demo Foundry" and len(d["items"]) == 5
    assert d["items"][0]["key"] == "boss" and d["items"][1]["key"] == "k7"
    assert d["text"].splitlines()[2] == "1. [Critical] boss" and "Next: do" in d["text"]


def test_digest_when_nothing_needs_attention():
    assert "Nothing needs attention today." in dg.digest([], TODAY)["text"]


def test_cards_serialise_to_plain_json():
    out = card("a", "warning", 2.456, numbers={"n": 1}, why=("because",)).as_dict()
    assert out["why"] == ["because"] and out["impact"] == 2.46 and out["rank"] == 172.8
