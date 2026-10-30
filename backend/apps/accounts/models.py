from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q

from apps.core.audit import audited

from .roles import Role


@audited(exclude=("password", "last_login"))
class User(AbstractUser):
    """A person who signs in. Everyone belongs to one company except Vezapp's own admins."""

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VIEWER)
    company = models.ForeignKey(
        "companies.Company",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="users",
    )

    class Meta:
        ordering = ["username"]
        constraints = [
            models.CheckConstraint(
                condition=Q(role="vezapp_admin") | Q(company__isnull=False),
                name="user_company_required_unless_vezapp_admin",
            )
        ]

    @property
    def full_name(self):
        return self.get_full_name() or self.username
