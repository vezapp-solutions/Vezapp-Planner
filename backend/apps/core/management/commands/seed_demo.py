from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.accounts.roles import Role
from apps.companies.models import Company, Plant
from seeds.demo_foundry import DEMO_COMPANIES, VEZAPP_ADMINS


class Command(BaseCommand):
    help = "Create the synthetic demo foundries and one user per role. Safe to re-run."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DJANGO_DEBUG=true (demo data).")
        password = settings.DEMO_PASSWORD
        if not password:
            raise CommandError("Set DEMO_PASSWORD in .env before seeding demo users.")

        for username, first, last in VEZAPP_ADMINS:
            self._user(username, first, last, Role.VEZAPP_ADMIN, None, password)

        for spec in DEMO_COMPANIES:
            company, _ = Company.objects.get_or_create(
                name=spec["name"], defaults={"address": spec["address"]}
            )
            for plant in spec["plants"]:
                Plant.objects.get_or_create(company=company, name=plant)
            for username, first, last, role in spec["users"]:
                self._user(username, first, last, role, company, password)
            builder = spec.get("builder")
            if builder:
                builder(company)

        self.stdout.write(self.style.SUCCESS("Demo data ready. Users:"))
        for user in User.objects.order_by("username"):
            company = user.company.name if user.company else "(all companies)"
            self.stdout.write(f"  {user.username:<14} {user.get_role_display():<14} {company}")

    def _user(self, username, first, last, role, company, password):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"first_name": first, "last_name": last, "role": role, "company": company},
        )
        if created:
            user.set_password(password)
            user.save()
