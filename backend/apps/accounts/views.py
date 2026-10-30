from django.conf import settings
from django.contrib.auth import authenticate
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.roles import Role
from apps.core.permissions import AdminOnly

from .authentication import ACCESS_COOKIE, REFRESH_COOKIE, require_client_header
from .models import User
from .serializers import LoginSerializer, MeSerializer, UserSerializer

REFRESH_COOKIE_PATH = "/api/v1/auth/"


def _set_cookie(response, name, value, lifetime, path="/"):
    response.set_cookie(
        name,
        value,
        max_age=int(lifetime.total_seconds()),
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="Lax",
        path=path,
    )


def _set_auth_cookies(response, access, refresh):
    lifetimes = settings.SIMPLE_JWT
    _set_cookie(response, ACCESS_COOKIE, access, lifetimes["ACCESS_TOKEN_LIFETIME"])
    _set_cookie(
        response, REFRESH_COOKIE, refresh, lifetimes["REFRESH_TOKEN_LIFETIME"], REFRESH_COOKIE_PATH
    )


def _clear_auth_cookies(response):
    response.delete_cookie(ACCESS_COOKIE, path="/", samesite="Lax")
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, samesite="Lax")


class LoginRateThrottle(AnonRateThrottle):
    scope = "login"


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        invalid = Response(
            {"detail": "Invalid username or password."}, status=status.HTTP_401_UNAUTHORIZED
        )
        if user is None or not user.is_active:
            return invalid
        if user.company_id and not user.company.is_active:
            return Response(
                {"detail": "This company is inactive. Contact Vezapp support."},
                status=status.HTTP_403_FORBIDDEN,
            )

        refresh = RefreshToken.for_user(user)
        response = Response(MeSerializer(user).data)
        _set_auth_cookies(response, str(refresh.access_token), str(refresh))
        return response


class RefreshView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        require_client_header(request)
        raw = request.COOKIES.get(REFRESH_COOKIE)
        unauthorised = Response(
            {"detail": "Session expired. Please sign in again."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
        if not raw:
            return unauthorised
        serializer = TokenRefreshSerializer(data={"refresh": raw})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError:
            _clear_auth_cookies(unauthorised)
            return unauthorised
        except Exception:  # noqa: BLE001 - invalid, blacklisted or inactive-user tokens
            _clear_auth_cookies(unauthorised)
            return unauthorised

        data = serializer.validated_data
        response = Response({"detail": "refreshed"})
        _set_auth_cookies(response, data["access"], data.get("refresh", raw))
        return response


class LogoutView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        require_client_header(request)
        raw = request.COOKIES.get(REFRESH_COOKIE)
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                pass
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_auth_cookies(response)
        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(MeSerializer(request.user).data)


class UserViewSet(viewsets.ModelViewSet):
    """Vezapp Admin manages everyone; a Company Admin manages their own company's users."""

    serializer_class = UserSerializer
    permission_classes = [AdminOnly]
    queryset = User.objects.select_related("company")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role == Role.VEZAPP_ADMIN:
            return qs
        return qs.filter(company_id=user.company_id)

    def perform_destroy(self, instance):
        if instance.pk == self.request.user.pk:
            raise PermissionDenied("You cannot delete your own account.")
        instance.delete()
