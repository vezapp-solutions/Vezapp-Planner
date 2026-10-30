from apps.accounts.models import User
from apps.companies.models import Plant
from apps.core.models import AuditLog


def test_create_update_delete_are_logged_with_user_and_values(login, users, company_a):
    client = login(users["a_admin"])

    created = client.post("/api/v1/plants", {"name": "Foundry Shop"}, format="json").json()
    client.patch(f"/api/v1/plants/{created['id']}", {"name": "Foundry Shop 1"}, format="json")
    client.delete(f"/api/v1/plants/{created['id']}")

    logs = list(AuditLog.objects.filter(model_label="companies.Plant").order_by("id"))
    assert [log.action for log in logs] == ["create", "update", "delete"]
    assert all(log.username == "a_admin" and log.company_id == company_a.pk for log in logs)
    assert logs[0].before is None and logs[0].after["name"] == "Foundry Shop"
    assert logs[1].before["name"] == "Foundry Shop" and logs[1].after["name"] == "Foundry Shop 1"
    assert logs[2].after is None


def test_unchanged_save_writes_no_update_row(db, company_a):
    plant = Plant.objects.create(company=company_a, name="P")
    before = AuditLog.objects.count()
    plant.save()
    assert AuditLog.objects.count() == before


def test_user_passwords_never_reach_the_audit_log(login, users):
    login(users["a_admin"]).post(
        "/api/v1/users",
        {"username": "audited", "password": "Str0ng-pass-99", "role": "viewer"},
        format="json",
    )
    log = AuditLog.objects.get(model_label="accounts.User", after__username="audited")
    assert "password" not in log.after and "last_login" not in log.after
    assert User.objects.get(username="audited").check_password("Str0ng-pass-99")


def test_audit_rows_are_append_only(db, company_a):
    import pytest

    Plant.objects.create(company=company_a, name="P")
    row = AuditLog.objects.first()
    with pytest.raises(RuntimeError):
        row.save()
