"""Synthetic demo data. Everything here is invented; no real client data."""

from apps.accounts.roles import Role

from .demo_a import build_demo_foundry
from .demo_gaps import ensure_demo_gaps
from .demo_machining import ensure_demo_machining
from .demo_scenarios import ensure_demo_scenarios
from .demo_schedule import build_demo_schedule
from .worked_example import build_worked_example, ensure_worked_example_line

DEMO_COMPANIES = [
    {
        "name": "Demo Foundry A (synthetic)",
        "address": "Plot 12, Demo Industrial Estate, Rajkot, Gujarat",
        "plants": ["Plant 1 - Iron", "Plant 2 - Steel"],
        "users": [
            ("a.admin", "Asha", "Admin", Role.COMPANY_ADMIN),
            ("a.planner", "Pradeep", "Planner", Role.PLANNER),
            ("a.viewer", "Vikram", "Viewer", Role.VIEWER),
        ],
        "builder": lambda company: (
            build_demo_foundry(company),
            build_demo_schedule(company),
            ensure_demo_machining(company),
            ensure_demo_gaps(company),
            ensure_demo_scenarios(company),
        ),
    },
    {
        "name": "Demo Foundry B (synthetic)",
        "address": "Survey 7, Demo Casting Park, Coimbatore, Tamil Nadu",
        "plants": ["Main Plant"],
        "users": [
            ("b.admin", "Bhavna", "Admin", Role.COMPANY_ADMIN),
            ("b.planner", "Bharat", "Planner", Role.PLANNER),
        ],
        # Foundry B holds the PROMPT.md section 7.5 worked example (part H-120) and its one order, exactly.
        "builder": lambda company: (
            build_worked_example(company),
            ensure_worked_example_line(company),
            ensure_demo_scenarios(company),
        ),
    },
]

VEZAPP_ADMINS = [("vezapp.admin", "Vezapp", "Admin")]
