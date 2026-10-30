"""The Insight Engine: pure functions from plan and schedule facts to ranked insight cards.

No Django and no database here, so every rule can be tested with hand-built fixtures. The adapter
in apps/insights turns real rows into these facts.
"""
