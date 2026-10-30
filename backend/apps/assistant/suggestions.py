"""What to offer the user to ask next, from what they just asked about. Every suggestion is a question
basic mode understands too, so a click always works."""

FIRST = ["How is the plan overall?", "Which lines are at risk?", "Which machines are free?"]

NEXT = {
    "get_at_risk_lines": [
        "Where is the bottleneck?",
        "Do we have any data problems?",
        "What is the month forecast?",
    ],
    "get_bottlenecks": [
        "Which machines are free?",
        "Do we have a capacity gap?",
        "Which lines are at risk?",
    ],
    "get_resource_load": [
        "Where is the bottleneck?",
        "Which machines are free?",
        "Which lines are at risk?",
    ],
    "get_capacity_gap": [
        "Where is the bottleneck?",
        "Which machines are free?",
        "Which lines are at risk?",
    ],
    "get_dispatch_performance": [
        "Which lines are at risk?",
        "How is the plan overall?",
        "What is the month forecast?",
    ],
    "get_customer_status": [
        "Which lines are at risk?",
        "How was the dispatch record?",
        "What is the month forecast?",
    ],
    "get_month_forecast": [
        "Which lines are at risk?",
        "How was the dispatch record?",
        "Summarise this month",
    ],
    "get_part_status": [
        "Which lines are at risk?",
        "Which machines are free?",
        "Do we have any data problems?",
    ],
    "get_machine_availability": [
        "What is planned today?",
        "Where is the bottleneck?",
        "Which lines are at risk?",
    ],
    "get_day_plan": [
        "Which machines are free?",
        "Where is the bottleneck?",
        "What is planned tomorrow?",
    ],
    "get_data_health": [
        "Which lines are at risk?",
        "How is the plan overall?",
        "What is the month forecast?",
    ],
    "get_plan_overview": [
        "Which lines are at risk?",
        "Where is the bottleneck?",
        "What is planned today?",
    ],
}


def follow_ups(tools: list[str], asked: str = "") -> list[str]:
    """Up to three questions to offer next, based on the last thing looked at."""
    pool = FIRST
    for name in reversed(tools):
        if name in NEXT:
            pool = NEXT[name]
            break
    asked_key = " ".join(asked.lower().split())
    return [q for q in pool if q.lower() != asked_key][:3]
