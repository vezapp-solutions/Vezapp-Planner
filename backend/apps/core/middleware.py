from .context import _current_user


class AuditContextMiddleware:
    """Clears the audit user for every request; authentication sets it again once known."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _current_user.set(None)
        try:
            return self.get_response(request)
        finally:
            _current_user.reset(token)
