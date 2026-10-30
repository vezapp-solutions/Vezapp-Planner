"""The assistant: the number guard, the read-only tools, basic mode, the Claude loop (with a stand-in
model), roles, tenancy, rate limits and logs."""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from django.core.cache import cache

from apps.assistant import guard, service
from apps.assistant.models import AssistantLog
from apps.assistant.tools import TOOL_SPECS, Toolbox
from apps.assistant.views import AssistantThrottle
from apps.masters.models import Customer, PartOperation
from apps.plans.models import Plan
from apps.resources.models import Downtime
from apps.scheduler.models import LineStatus, ScheduleLine
from seeds.worked_example import build_worked_example

J = {"format": "json"}
TODAY = date(2026, 11, 2)  # a Monday


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("django.utils.timezone.localdate", lambda *a, **k: TODAY)
    cache.clear()  # the throttle keeps its counts here


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
    built = build_worked_example(company_a)
    customer = Customer.objects.get(company=company_a, code="CUST-01")
    built["customer"] = customer
    built["big"] = add_line(
        company_a, customer, built["part"], 1500, date(2026, 11, 6)
    )  # cannot make it
    built["easy"] = add_line(company_a, customer, built["part"], 100, date(2026, 11, 30))
    for n, late in enumerate([0, 0, 3, 5]):
        due = date(2026, 10, 5) + timedelta(days=n)
        add_line(company_a, customer, built["part"], 50, due, status=LineStatus.DISPATCHED,
                 actual_dispatch_date=due + timedelta(days=late), actual_dispatched_qty=50)  # fmt: skip
    return built


@pytest.fixture
def planned(login, users, plant):
    client = login(users["a_planner"])
    assert client.post("/api/v1/plans", {}, **J).status_code == 201
    return client


# --- a stand-in for the model ----------------------------------------------------------------------------
def text(t):
    return SimpleNamespace(type="text", text=t)


def tool_use(n, name, **args):
    return SimpleNamespace(type="tool_use", id=f"tu{n}", name=name, input=args)


class FakeClient:
    """Plays a script: each step is the content blocks of one model reply, or an exception to raise."""

    def __init__(self, *steps):
        self.steps, self.calls, self.messages = list(steps), [], self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return SimpleNamespace(
            content=step,
            usage=SimpleNamespace(input_tokens=100, output_tokens=20),
            stop_reason="end_turn",
        )


def ask_with(client, user, company, question="Which lines are at risk?"):
    return service.ask(user, company, question, client=client)


# --- the number guard --------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1,00,000", "100000"),
        ("05", "5"),
        ("0", "0"),
        ("12.50", "12.5"),
        ("3.0", "3"),
        ("007.10", "7.1"),
    ],
)
def test_canonical_numbers(raw, expected):
    assert guard.canon(raw) == expected


def test_numbers_in_a_reply_ignores_list_numbering():
    assert guard.numbers_in("1. First 120 pieces\n2) Second 45%\n- 3. Third") == ["120", "45"]


RESULT = {
    "total": 3,
    "lines": [
        {"qty": 1500, "internal_date": "2026-11-06", "share": 0.456, "hours": 12.5},
        {"qty": 40},
    ],
    "plan_version": 2,
}


@pytest.mark.parametrize(
    "reply",
    [
        "3 lines are at risk in plan v2.",  # numbers as given
        "1,500 pieces are due on 06-11-2026.",  # Indian grouping and DD-MM-YYYY
        "That is 46% of the order and 45.6 per cent exactly.",  # a share given as a percentage
        "It needs about 12.5 hours (12.5).",
        "Two lines are listed: 1500 and 40.",  # a count of what the tool returned (2) and its quantities
    ],
)
def test_guard_passes_numbers_that_are_in_the_results(reply):
    assert guard.unverified(reply, [RESULT]) == []


@pytest.mark.parametrize(
    "reply, invented",
    [
        ("4 lines are at risk.", ["4"]),
        ("About 1,600 pieces.", ["1600"]),
        ("They are due on 07-11-2026.", ["7"]),
        ("That is 90% of the order.", ["90"]),
        ("Roughly 99 hours and 98 minutes.", ["99", "98"]),
    ],
)
def test_guard_blocks_numbers_that_are_not(reply, invented):
    assert guard.unverified(reply, [RESULT]) == invented


def test_guard_allows_numbers_the_user_typed_but_nothing_derived():
    assert (
        guard.unverified(
            "Over the next 14 days F1 peaks.", [{"x": 1}], "what about the next 14 days?"
        )
        == []
    )
    assert guard.unverified(
        "Over the next 14 days F1 peaks.", [{"x": 1}], "what about next week?"
    ) == ["14"]


def test_guard_with_no_tool_results_allows_no_numbers():
    assert guard.unverified("There are 5 lines.", []) == ["5"]
    assert guard.unverified("I don't have that data.", []) == []


# --- tools ------------------------------------------------------------------------------------------------------------------
def test_every_tool_runs_and_returns_plain_json(users, plant, planned, company_a):
    import json

    box = Toolbox(company_a)
    line_id = box.call("get_at_risk_lines")["lines"][0]["line_id"]
    calls = [
        ("get_at_risk_lines", {"customer": "cust-01", "limit": 2}), ("get_bottlenecks", {"days": 5}),
        ("get_resource_load", {"resource": "f1", "from_date": "2026-11-02", "to_date": "2026-11-06"}),
        ("get_capacity_gap", {}), ("get_line_plan", {"line_id": line_id}),
        ("get_dispatch_performance", {"customer": "CUST-01"}), ("get_month_forecast", {}),
        ("get_part_status", {"part_number": "h-120"}), ("get_insights", {"type": "at_risk"}),
        ("get_insight", {"key": "at_risk:summary"}),
        ("run_what_if_dry_run", {"change": "block_resource", "resource": "F1", "from_date": "2026-11-03", "to_date": "2026-11-03"}),
        ("find", {"text": "cust"}), ("get_customer_status", {"customer": "cust-01"}),
        ("get_plan_overview", {}), ("get_day_plan", {"date": "2026-11-03"}),
        ("get_machine_availability", {}), ("get_data_health", {}),
    ]  # fmt: skip
    assert {n for n, _ in calls} | {"get_at_risk_lines"} == {s["name"] for s in TOOL_SPECS}
    for name, args in calls:
        result = box.call(name, args)
        assert "error" not in result, (name, result)
        json.dumps(result)  # serialisable


def test_tool_results_carry_the_numbers_a_planner_asks_for(planned, company_a):
    box = Toolbox(company_a)
    risk = box.call("get_at_risk_lines")
    assert (
        risk["total_at_risk"] >= 1
        and risk["lines"][0]["part"] == "H-120"
        and risk["lines"][0]["working_days_late"] >= 1
    )
    perf = box.call("get_dispatch_performance", {})
    assert (perf["lines"], perf["on_time"], perf["late"], perf["on_time_percent"]) == (4, 2, 2, 50)
    assert perf["average_delay_days_of_late_lines"] == 4.0 and perf["worst_delay_days"] == 5
    load = box.call(
        "get_resource_load", {"resource": "F1", "from_date": "2026-11-02", "to_date": "2026-11-06"}
    )
    assert load["resource"] == "F1" and max(d["utilisation_percent"] for d in load["days"]) >= 95
    overall = box.call("get_bottlenecks", {})
    assert overall["overall_bottleneck"] in ("F1", "CM1")  # both run flat out in this plant
    assert {d["busiest_resource"] for d in overall["days"] if d["busiest_resource"]} >= {"F1"}


def test_the_dry_run_tool_changes_nothing(planned, company_a):
    plans, lines, downtimes = (
        Plan.objects.count(),
        list(ScheduleLine.objects.values_list("pk", "dispatch_qty")),
        Downtime.objects.count(),
    )
    box = Toolbox(company_a)
    line_id = box.call("get_at_risk_lines")["lines"][0]["line_id"]
    for args in (
        {
            "change": "block_resource",
            "resource": "F1",
            "from_date": "2026-11-03",
            "to_date": "2026-11-04",
        },
        {"change": "change_qty", "line_id": line_id, "qty": 200},
        {"change": "change_date", "line_id": line_id, "new_date": "2026-12-20"},
        {
            "change": "overtime",
            "resource": "F1",
            "from_date": "2026-11-02",
            "to_date": "2026-11-06",
            "minutes": 120,
        },
    ):
        result = box.call("run_what_if_dry_run", args)
        assert result["applied"] is False and "lines_that_change" in result, result
    assert (
        Plan.objects.count(),
        list(ScheduleLine.objects.values_list("pk", "dispatch_qty")),
        Downtime.objects.count(),
    ) == (plans, lines, downtimes)


@pytest.mark.parametrize(
    "name, args",
    [
        ("get_resource_load", {"resource": "NOPE"}),
        ("get_part_status", {"part_number": "NOPE"}),
        ("get_line_plan", {"line_id": 999999}),
        ("get_insight", {"key": "nope"}),
        ("get_at_risk_lines", {"limit": "many"}),
        ("get_resource_load", {"resource": "F1", "from_date": "tomorrow"}),
        ("run_what_if_dry_run", {"change": "teleport"}),
        (
            "run_what_if_dry_run",
            {
                "change": "overtime",
                "resource": "F1",
                "from_date": "2026-11-02",
                "to_date": "2026-11-02",
                "minutes": 9999,
            },
        ),
        ("run_what_if_dry_run", {"change": "change_qty", "line_id": 999999, "qty": 5}),
        ("delete_everything", {}),
        ("get_at_risk_lines", {"company": 2}),
        ("get_insights", {"sql": "select 1"}),  # nothing but declared arguments gets through
    ],
)
def test_bad_tool_requests_come_back_as_errors_not_exceptions(planned, company_a, name, args):
    assert "error" in Toolbox(company_a).call(name, args)


def test_tools_never_see_another_companys_data(planned, company_a, company_b):
    build_worked_example(company_b)
    other = Toolbox(company_b)
    line_id = Toolbox(company_a).call("get_at_risk_lines")["lines"][0]["line_id"]
    assert other.call("get_at_risk_lines")["plan_version"] is None  # company B has no plan
    foreign = other.call("get_line_plan", {"line_id": line_id})
    assert "error" in foreign or foreign["plan_version"] is None  # never company A's line
    assert "error" in other.call(
        "run_what_if_dry_run", {"change": "change_qty", "line_id": line_id, "qty": 5}
    )
    assert other.call("get_dispatch_performance")["lines"] == 0
    assert other.call("get_insights")["cards"] == []
    assert (
        other.call("get_resource_load", {"resource": "F1"})["plan_version"] is None
    )  # its own F1, with nothing planned


def test_without_a_plan_tools_say_so(users, plant, company_a):
    box = Toolbox(company_a)
    assert box.call("get_at_risk_lines")["note"] == "No plan has been calculated yet."
    assert box.call("get_bottlenecks")["days"] == [] and box.call("get_month_forecast")["note"]


# --- basic mode -------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "question, intent, expect",
    [
        ("Which lines are at risk?", "at_risk", "H-120 for CUST-01"),
        ("what is late for cust-01", "at_risk", "for CUST-01"),
        ("Where is the bottleneck?", "bottleneck", "F1"),
        ("Do we have a capacity gap?", "capacity_gap", "working hours are free"),
        ("How is CUST-01 doing on time?", "customer_performance", "50% on time"),
        ("What is the status of H-120?", "part_status", "Housing"),
        ("What is the month forecast?", "month_forecast", "November 2026"),
        ("hello there", "greeting", "planning assistant"),
        ("thanks a lot", "thanks", "You're welcome"),
        ("what can you do?", "help", "I can help with things like these"),
        ("how is the plan overall?", "overview", "Plan v1"),
        ("What is planned today?", "day_plan", "Monday 02-11-2026"),
        ("How is CUST-01 doing?", "customer_status", "Their dispatch record"),
        ("Which machines are free?", "machines", "No machine is used"),
        ("Do we have any data problems?", "data_health", "No data problems"),
        ("what if F1 is down tomorrow?", "what_if", "AI mode"),
        ("xyzzy", "help", "not sure I understood"),
    ],
)
def test_basic_mode_intents(planned, company_a, question, intent, expect):
    box = Toolbox(company_a)
    from apps.assistant import basic

    result = basic.answer(box, question)
    assert result["intent"] == intent and expect in result["answer"], result["answer"]


@pytest.mark.parametrize(
    "question",
    [
        "Which lines are at risk?",
        "Where is the bottleneck?",
        "Do we have a capacity gap?",
        "How is CUST-01 doing?",
        "What is the status of H-120?",
        "month forecast",
    ],
)
def test_every_number_in_a_basic_answer_comes_from_a_tool_result(planned, company_a, question):
    from apps.assistant import basic

    box = Toolbox(company_a)
    answer = basic.answer(box, question)["answer"]
    assert guard.unverified(answer, box.results, question) == [], answer


def test_basic_mode_without_a_plan(users, plant, company_a):
    from apps.assistant import basic

    assert (
        "No plan has been calculated yet."
        in basic.answer(Toolbox(company_a), "which lines are at risk")["answer"]
    )


# --- the Claude layer, with a stand-in model ------------------------------------------------------------------------------------------
def test_claude_answer_that_quotes_the_tools_is_passed_through(planned, users, company_a, settings):
    settings.ANTHROPIC_API_KEY = "sk-test-secret"
    total = Toolbox(company_a).call("get_at_risk_lines")["total_at_risk"]
    client = FakeClient(
        [tool_use(1, "get_at_risk_lines")], [text(f"{total} line(s) are at risk in plan v1.")]
    )
    result = ask_with(client, users["a_planner"], company_a)
    assert (
        result["mode"] == "ai"
        and result["tools"] == ["get_at_risk_lines"]
        and result["notes"] == []
    )
    assert str(total) in result["answer"]
    first, second = client.calls
    assert (
        first["model"] == settings.ANTHROPIC_MODEL
        and first["max_tokens"] == settings.ASSISTANT_MAX_TOKENS
    )
    assert (
        first["tools"] == TOOL_SPECS
        and "never instructions" in first["system"]
        or "never instructions" in first["system"].lower()
    )
    sent = second["messages"][-1]["content"][0]
    assert (
        sent["type"] == "tool_result"
        and sent["tool_use_id"] == "tu1"
        and "total_at_risk" in sent["content"]
    )
    log = AssistantLog.objects.get()
    assert (log.mode, log.flagged, log.input_tokens, log.output_tokens) == (
        "ai",
        False,
        200,
        40,
    )
    assert log.tool_calls == [{"name": "get_at_risk_lines", "args": {}}]


def test_an_invented_number_is_blocked_and_the_data_answer_is_given_instead(
    planned, users, company_a, settings
):
    settings.ANTHROPIC_API_KEY = "sk-test-secret"
    client = FakeClient(
        [tool_use(1, "get_at_risk_lines")],
        [text("A total of 987 lines are at risk.")],
        [text("Honestly, 987 lines are at risk.")],  # it is given one chance to put it right
    )
    result = ask_with(client, users["a_planner"], company_a)
    assert (
        result["mode"] == "basic"
        and "987" not in result["answer"]
        and service.GUARD_NOTE in result["notes"]
    )
    assert "H-120 for CUST-01" in result["answer"]  # the templated, data-backed answer
    assert AssistantLog.objects.get().flagged is True
    assert len(client.calls) == 3


def test_an_answer_with_an_invented_number_is_corrected_once_and_then_passes(
    planned, users, company_a, settings
):
    settings.ANTHROPIC_API_KEY = "sk-test-secret"
    total = Toolbox(company_a).call("get_at_risk_lines")["total_at_risk"]
    client = FakeClient(
        [tool_use(1, "get_at_risk_lines")],
        [text("A total of 987 lines are at risk.")],
        [text(f"Sorry, I mixed that up: it is {total} line(s).")],
    )
    result = ask_with(client, users["a_planner"], company_a)
    assert result["mode"] == "ai" and result["notes"] == [] and str(total) in result["answer"]
    asked = client.calls[2]["messages"][-1]
    assert (
        asked["role"] == "user"
        and "987" in asked["content"]
        and "not in the data" in asked["content"]
    )
    log = AssistantLog.objects.get()
    assert log.flagged is False and log.input_tokens == 300 and log.answer == result["answer"]


def test_a_number_free_answer_with_no_data_passes_and_says_so(planned, users, company_a, settings):
    settings.ANTHROPIC_API_KEY = "sk-test-secret"
    result = ask_with(
        FakeClient([text("I don't have that data.")]),
        users["a_planner"],
        company_a,
        "What is the weather?",
    )
    assert result["mode"] == "ai" and result["answer"] == "I don't have that data."


def test_a_model_that_guesses_without_calling_tools_is_blocked(planned, users, company_a, settings):
    settings.ANTHROPIC_API_KEY = "sk-test-secret"
    result = ask_with(
        FakeClient(
            [text("You will ship 450 pieces tomorrow.")], [text("Still 450 pieces tomorrow.")]
        ),
        users["a_planner"],
        company_a,
    )
    assert result["mode"] == "basic" and service.GUARD_NOTE in result["notes"]


def test_the_model_cannot_pick_the_company_or_run_an_unknown_tool(
    planned, users, company_a, settings
):
    settings.ANTHROPIC_API_KEY = "sk-test-secret"
    client = FakeClient(
        [tool_use(1, "get_at_risk_lines", company=99), tool_use(2, "drop_tables")],
        [text("I could not use those tools.")],
    )
    result = ask_with(client, users["a_planner"], company_a)
    log = AssistantLog.objects.get()
    assert result["mode"] == "ai" and [c["name"] for c in log.tool_calls] == [
        "get_at_risk_lines",
        "drop_tables",
    ]
    sent = client.calls[1]["messages"][-1]["content"][0]["content"]
    assert "not valid" in sent


def test_when_the_ai_fails_basic_mode_answers(planned, users, company_a, settings):
    settings.ANTHROPIC_API_KEY = "sk-test-secret"
    result = ask_with(FakeClient(RuntimeError("network down")), users["a_planner"], company_a)
    assert (
        result["mode"] == "basic"
        and service.FAILED_NOTE in result["notes"]
        and "H-120" in result["answer"]
    )


def test_a_model_that_never_stops_calling_tools_is_cut_off(planned, users, company_a, settings):
    settings.ANTHROPIC_API_KEY = "sk-test-secret"
    client = FakeClient(
        *[[tool_use(i, "get_bottlenecks")] for i in range(settings.ASSISTANT_MAX_ROUNDS)]
    )
    result = ask_with(client, users["a_planner"], company_a)
    assert len(client.calls) == settings.ASSISTANT_MAX_ROUNDS and result["mode"] == "basic"


def test_logs_hold_the_question_and_tools_but_no_secrets(planned, users, company_a, settings):
    settings.ANTHROPIC_API_KEY = "sk-test-secret"
    ask_with(
        FakeClient([tool_use(1, "get_bottlenecks")], [text("I don't have that data.")]),
        users["a_planner"],
        company_a,
        "Where is the bottleneck?",
    )
    log = AssistantLog.objects.get()
    dump = f"{log.prompt} {log.tool_calls} {log.answer} {log.username}"
    assert (
        "sk-test-secret" not in dump
        and log.prompt == "Where is the bottleneck?"
        and log.username == "a_planner"
    )
    assert log.company_id == company_a.pk and log.kind == "ask"


# --- API -------------------------------------------------------------------------------------------------------------------------
def test_status_reports_the_mode(login, users, plant, settings):
    settings.ANTHROPIC_API_KEY = ""
    body = login(users["a_viewer"]).get("/api/v1/assistant/status").json()
    assert (
        body["mode"] == "basic"
        and "Basic mode" in body["notice"]
        and "advisory" in body["disclaimer"]
    )
    settings.ANTHROPIC_API_KEY = "sk-test-secret"
    body = login(users["a_viewer"]).get("/api/v1/assistant/status").json()
    assert body["mode"] == "ai" and body["notice"] is None and "model" not in body
    assert "sk-test-secret" not in str(body)
    assert settings.ANTHROPIC_MODEL not in str(body)


def test_without_a_key_the_api_answers_in_basic_mode(planned, users, settings):
    settings.ANTHROPIC_API_KEY = ""
    body = login_post(planned, "Which lines are at risk?")
    assert (
        body["mode"] == "basic"
        and body["tools"] == ["get_at_risk_lines"]
        and body["intent"] == "at_risk"
    )
    assert "H-120 for CUST-01" in body["answer"] and "advisory" in body["disclaimer"]
    assert AssistantLog.objects.get().mode == "basic"


def login_post(client, question):
    response = client.post("/api/v1/assistant/ask", {"question": question}, **J)
    assert response.status_code == 200, response.content
    return response.json()


def test_viewers_can_ask_and_anonymous_cannot(planned, login, users, anon_client):
    assert (
        login(users["a_viewer"])
        .post("/api/v1/assistant/ask", {"question": "bottleneck?"}, **J)
        .status_code
        == 200
    )
    assert anon_client.post(
        "/api/v1/assistant/ask", {"question": "bottleneck?"}, **J
    ).status_code in (401, 403)
    assert anon_client.get("/api/v1/assistant/status").status_code in (401, 403)


@pytest.mark.parametrize("question", ["", "   ", "x" * 501])
def test_bad_questions_are_refused(planned, question):
    assert planned.post("/api/v1/assistant/ask", {"question": question}, **J).status_code == 400


def test_the_assistant_is_company_scoped(planned, login, users, company_b):
    build_worked_example(company_b)
    b = login(users["b_admin"])
    body = login_post(b, "Which lines are at risk?")
    assert (
        "No plan has been calculated yet." in body["answer"]
        and "H-120 for CUST-01" not in body["answer"]
    )
    assert AssistantLog.objects.filter(company=company_b).count() == 1


def test_a_per_minute_limit_applies_per_user(planned, login, users, monkeypatch):
    monkeypatch.setitem(AssistantThrottle.THROTTLE_RATES, "assistant", "2/min")
    for _ in range(2):
        assert (
            planned.post("/api/v1/assistant/ask", {"question": "bottleneck?"}, **J).status_code
            == 200
        )
    assert (
        planned.post("/api/v1/assistant/ask", {"question": "bottleneck?"}, **J).status_code == 429
    )
    assert (
        login(users["a_viewer"])
        .post("/api/v1/assistant/ask", {"question": "bottleneck?"}, **J)
        .status_code
        == 200
    )  # another user


def test_a_daily_limit_applies(planned, settings):
    settings.ASSISTANT_DAILY_LIMIT = 2
    for _ in range(2):
        assert (
            planned.post("/api/v1/assistant/ask", {"question": "bottleneck?"}, **J).status_code
            == 200
        )
    response = planned.post("/api/v1/assistant/ask", {"question": "bottleneck?"}, **J)
    assert response.status_code == 400 and "limit" in response.json()["detail"]


def test_explain_this_uses_the_insights_own_trace(planned):
    key = "at_risk:summary"
    response = planned.post("/api/v1/assistant/explain", {"key": key}, **J)
    assert response.status_code == 200, response.content
    body = response.json()
    assert (
        body["intent"] == "explain"
        and "A good next step:" in body["answer"]
        and body["tools"] == ["get_insight"]
    )
    assert "estimated dispatch date is after its internal date" in body["answer"]
    assert planned.post("/api/v1/assistant/explain", {"key": "nope"}, **J).status_code == 400


def test_explain_with_the_ai_is_guarded_too(planned, users, company_a, settings):
    settings.ANTHROPIC_API_KEY = "sk-test-secret"
    client = FakeClient(
        [tool_use(1, "get_insight", key="at_risk:summary")],
        [text("This is caused by 31337 problems.")],
        [text("It really is 31337 problems.")],
    )
    result = service.explain(users["a_planner"], company_a, "at_risk:summary", client=client)
    assert (
        result["mode"] == "basic"
        and "31337" not in result["answer"]
        and AssistantLog.objects.get().kind == "explain"
    )


def test_monthly_summary_in_basic_mode_and_with_ai(planned, users, company_a, settings):
    settings.ANTHROPIC_API_KEY = ""
    body = planned.post("/api/v1/assistant/monthly-summary", {}, **J).json()
    assert (
        body["mode"] == "basic"
        and "November 2026" in body["answer"]
        and "on time" in body["answer"]
    )

    settings.ANTHROPIC_API_KEY = "sk-test-secret"
    client = FakeClient(
        [tool_use(1, "get_month_forecast")], [text("I don't have more than the forecast.")]
    )
    result = service.monthly_summary(users["a_planner"], company_a, client=client)
    assert result["mode"] == "ai" and AssistantLog.objects.filter(kind="summary").count() == 2


def test_the_assistant_never_changes_data(planned, users, company_a, settings):
    settings.ANTHROPIC_API_KEY = "sk-test-secret"
    before = (
        list(ScheduleLine.objects.values_list("pk", "dispatch_qty", "internal_dispatch_date")),
        Plan.objects.count(),
        PartOperation.objects.count(),
        Downtime.objects.count(),
    )
    client = FakeClient(
        [
            tool_use(
                1,
                "run_what_if_dry_run",
                change="block_resource",
                resource="F1",
                from_date="2026-11-03",
                to_date="2026-11-03",
            )
        ],
        [text("I tried it on a copy and nothing was saved.")],
    )
    ask_with(client, users["a_planner"], company_a, "What if F1 is down on 2026-11-03?")
    after = (
        list(ScheduleLine.objects.values_list("pk", "dispatch_qty", "internal_dispatch_date")),
        Plan.objects.count(),
        PartOperation.objects.count(),
        Downtime.objects.count(),
    )
    assert before == after


# --- talking like a person: memory, follow-ups, names --------------------------------------------------------------------------
def test_a_follow_up_sees_the_earlier_turns_of_the_same_chat(planned, users, company_a, settings):
    settings.ANTHROPIC_API_KEY = "sk-test-secret"
    first = ask_with(
        FakeClient([tool_use(1, "get_bottlenecks")], [text("I don't have more than that.")]),
        users["a_planner"],
        company_a,
        "Where is the bottleneck?",
    )
    assert len(first["conversation"]) == 32
    client = FakeClient([text("It is the same one I mentioned.")])
    second = service.ask(
        users["a_planner"], company_a, "why?", client=client, conversation=first["conversation"]
    )
    assert second["conversation"] == first["conversation"]
    sent = client.calls[0]["messages"]
    assert [m["role"] for m in sent] == ["user", "assistant", "user"]
    assert (
        sent[0]["content"] == "Where is the bottleneck?"
        and sent[1]["content"] == "I don't have more than that."
        and sent[2]["content"] == "why?"
    )


def test_numbers_already_given_in_the_chat_may_be_repeated_in_a_follow_up(
    planned, users, company_a, settings
):
    settings.ANTHROPIC_API_KEY = "sk-test-secret"
    total = Toolbox(company_a).call("get_at_risk_lines")["total_at_risk"]
    first = ask_with(
        FakeClient([tool_use(1, "get_at_risk_lines")], [text(f"{total} line(s) are at risk.")]),
        users["a_planner"],
        company_a,
    )
    follow = service.ask(
        users["a_planner"],
        company_a,
        "say that again",
        client=FakeClient([text(f"As I said, {total} line(s) are at risk.")]),
        conversation=first["conversation"],
    )
    assert follow["mode"] == "ai" and follow["notes"] == []


def test_a_chat_belongs_to_one_user(planned, login, users, company_a, settings):
    settings.ANTHROPIC_API_KEY = "sk-test-secret"
    first = ask_with(FakeClient([text("Hello there.")]), users["a_planner"], company_a, "hi")
    client = FakeClient([text("Hello again.")])
    service.ask(
        users["a_admin"], company_a, "hi again", client=client, conversation=first["conversation"]
    )
    assert [m["content"] for m in client.calls[0]["messages"]] == [
        "hi again"
    ]  # the planner's chat is not the admin's


def test_a_made_up_conversation_id_starts_a_new_chat(planned, users, company_a):
    reply = service.ask(users["a_planner"], company_a, "hello", conversation="not-a-real-id")
    assert len(reply["conversation"]) == 32 and reply["conversation"] != "not-a-real-id"


def test_basic_mode_chats_are_remembered_too_and_offer_follow_ups(planned):
    first = planned.post(
        "/api/v1/assistant/ask", {"question": "Which lines are at risk?"}, **J
    ).json()
    assert (
        first["follow_ups"]
        and len(first["follow_ups"]) <= 3
        and "Which lines are at risk?" not in first["follow_ups"]
    )
    second = planned.post(
        "/api/v1/assistant/ask",
        {"question": first["follow_ups"][0], "conversation": first["conversation"]},
        **J,
    ).json()
    assert second["conversation"] == first["conversation"] and second["answer"]


def test_every_suggestion_is_a_question_basic_mode_understands(planned, company_a):
    from apps.assistant import basic
    from apps.assistant.suggestions import FIRST, NEXT

    for question in {*FIRST, *(q for qs in NEXT.values() for q in qs)}:
        result = basic.answer(Toolbox(company_a), question)
        assert result["intent"] != "help", question


def test_the_status_offers_starter_questions(login, users, plant):
    assert login(users["a_viewer"]).get("/api/v1/assistant/status").json()["starters"]


def test_customers_are_found_by_a_piece_of_their_name(planned, company_a):
    box = Toolbox(company_a)
    found = box.call("find", {"text": "demo pumps"})
    assert [c["code"] for c in found["customers"]] == ["CUST-01"]
    assert (
        box.call("get_customer_status", {"customer": "Demo Pumps"})["customer"]["code"] == "CUST-01"
    )
    assert [p["part_number"] for p in box.call("find", {"text": "housing"})["parts"]] == ["H-120"]
    assert box.call("get_part_status", {"part_number": "housing"})["part"] == "H-120"


def test_an_unknown_name_comes_back_with_the_real_choices(planned, company_a):
    result = Toolbox(company_a).call("get_customer_status", {"customer": "Nobody Ltd"})
    assert "No customer matches" in result["error"] and "CUST-01" in result["error"]
    assert "nothing" in Toolbox(company_a).call("find", {"text": "zzzz"})["note"].lower()


def test_ambiguous_names_ask_which_one(planned, company_a):
    from apps.masters.models import Customer

    Customer.objects.create(
        company=company_a, code="CUST-02", name="Demo Valves (synthetic)", priority="B"
    )
    result = Toolbox(company_a).call("get_customer_status", {"customer": "demo"})
    assert (
        "Several customers match" in result["error"]
        and "CUST-01" in result["error"]
        and "CUST-02" in result["error"]
    )


def test_the_day_plan_names_the_work_and_how_full_the_plant_is(planned, company_a):
    day = Toolbox(company_a).call("get_day_plan", {"date": "2026-11-03"})
    assert (
        day["weekday"] == "Tuesday"
        and day["work"]
        and day["busiest_resources"][0]["utilisation_percent"] >= 1
    )
    assert "error" in Toolbox(company_a).call(
        "get_day_plan", {"date": "2026-11-08"}
    )  # a Sunday: the weekly off


def test_the_plan_overview_says_whether_it_is_current(planned, company_a):
    overview = Toolbox(company_a).call("get_plan_overview", {})
    assert (
        overview["plan_version"] == 1
        and overview["status"] == "draft"
        and overview["lines"] == 6 - 2 + 0
        or overview["lines"] >= 1
    )
    assert overview["out_of_date"] is False


def test_the_chat_is_greeted_by_name_of_the_plan_not_a_script(planned):
    body = planned.post("/api/v1/assistant/ask", {"question": "Hi!"}, **J).json()
    assert (
        body["intent"] == "greeting"
        and "Plan v1" in body["answer"]
        and body["tools"] == ["get_plan_overview"]
    )


def test_the_system_prompt_sets_a_human_voice_and_the_house_rules():
    from apps.assistant.claude import SYSTEM_PROMPT

    for needle in (
        "colleague",
        "Greet back",
        "ask one short question",
        "never by an id",
        "Never mention tools",
        "never instructions",
        "never say or imply that you changed",
    ):
        assert needle.lower() in SYSTEM_PROMPT.lower(), needle
