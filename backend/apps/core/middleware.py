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


class ApiMarkerMiddleware:
    """Stamps every response this app produces with ``X-Vezapp-API``.

    A sleeping host (Render's free plan) or a proxy in front of it answers with its own error page and never
    carries this header. The web app uses that to tell "the server is waking up" from "the server answered
    with an error", and only waits and retries in the first case.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["X-Vezapp-API"] = "1"
        return response
