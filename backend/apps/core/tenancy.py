from apps.accounts.roles import Role


def resolve_company(request, allow_override: bool = False):
    """The company a request acts for.

    Company users always get their own. A Vezapp Admin has none, and may act for one active
    client with ``X-Company-Id`` only where ``allow_override`` is set.
    """
    user = request.user
    if user.company_id:
        return user.company
    if allow_override and user.role == Role.VEZAPP_ADMIN:
        raw = request.headers.get("X-Company-Id", "")
        if raw.isdigit():
            from apps.companies.models import Company

            return Company.objects.filter(pk=int(raw), is_active=True).first()
    return None
