from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import SAFE_METHODS
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.core.context import set_current_user

ACCESS_COOKIE = "vp_access"
REFRESH_COOKIE = "vp_refresh"
CLIENT_HEADER = "X-VP-Client"
CLIENT_HEADER_VALUE = "web"


def require_client_header(request):
    """Cookie-authenticated writes must carry a custom header.

    A custom header cannot be sent cross-site without a CORS preflight (we allow none), so this
    closes CSRF on top of SameSite=Lax.
    """
    if request.headers.get(CLIENT_HEADER) != CLIENT_HEADER_VALUE:
        raise PermissionDenied(f"Missing {CLIENT_HEADER} header.")


class CookieJWTAuthentication(JWTAuthentication):
    """Reads the access token from the httpOnly cookie (or an Authorization header)."""

    def authenticate(self, request):
        header = self.get_header(request)
        from_cookie = header is None
        raw = request.COOKIES.get(ACCESS_COOKIE) if from_cookie else self.get_raw_token(header)
        if raw is None:
            return None

        validated = self.get_validated_token(raw)
        if from_cookie and request.method not in SAFE_METHODS:
            require_client_header(request)

        user = self.get_user(validated)
        if user.company_id and not user.company.is_active:
            raise AuthenticationFailed("This company is inactive.", code="company_inactive")

        set_current_user(user)
        return user, validated
