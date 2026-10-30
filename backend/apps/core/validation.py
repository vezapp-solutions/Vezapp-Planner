"""Bridges the engine's Issue objects to API behaviour: errors block, the rest are shown."""

from rest_framework.exceptions import ValidationError


def raise_on_errors(issues):
    errors: dict[str, list[str]] = {}
    for issue in issues:
        if issue.level == "error":
            errors.setdefault(issue.field, []).append(issue.message)
    if errors:
        raise ValidationError(errors)


def advisories(issues):
    return [i.as_dict() for i in issues if i.level != "error"]
