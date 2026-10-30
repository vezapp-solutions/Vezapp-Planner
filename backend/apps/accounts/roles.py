from django.db import models


class Role(models.TextChoices):
    VEZAPP_ADMIN = "vezapp_admin", "Vezapp Admin"
    COMPANY_ADMIN = "company_admin", "Company Admin"
    PLANNER = "planner", "Planner"
    VIEWER = "viewer", "Viewer"


ALL_ROLES = frozenset(Role.values)
ADMIN_ROLES = frozenset({Role.VEZAPP_ADMIN, Role.COMPANY_ADMIN})
PLANNER_ROLES = frozenset({Role.VEZAPP_ADMIN, Role.COMPANY_ADMIN, Role.PLANNER})
