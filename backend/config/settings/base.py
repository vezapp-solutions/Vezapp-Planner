"""Vezapp Planner settings. Secrets and environment switches come from the repo-root .env."""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
REPO_DIR = BASE_DIR.parent

load_dotenv(REPO_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


# The one place the product name lives on the backend. The frontend mirrors it as
# NEXT_PUBLIC_APP_NAME.
APP_NAME = "Vezapp Planner"

# The Vezapp logo for printed plans. It lives with the frontend brand files.
BRAND_LOGO_PATH = REPO_DIR / "frontend" / "public" / "brand" / "vezapp-logo.jpg"

DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "insecure-dev-only-key-do-not-use-in-production"
    else:
        raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false.")

if not DEBUG and (len(SECRET_KEY) < 32 or SECRET_KEY.startswith("change-me")):
    # SimpleJWT signs tokens with this key: a short or placeholder key lets anyone forge a login.
    raise RuntimeError("DJANGO_SECRET_KEY must be a random string of at least 32 characters.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# --- Transport and browser protections ----------------------------------------------------------
# Behind the HTTPS proxy of a real deployment: redirect to HTTPS, tell browsers to keep using it,
# and trust the proxy's forwarded-protocol header. Set SECURE_SSL_REDIRECT=false only if the proxy
# itself does the redirect.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024  # uploads are limited to 5 MB; this is the body cap

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "apps.core",
    "apps.companies",
    "apps.accounts",
    "apps.resources",
    "apps.masters",
    "apps.scheduler",
    "apps.plans",
    "apps.scenarios",
    "apps.insights",
    "apps.assistant",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.AuditContextMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

AUTH_USER_MODEL = "accounts.User"

# --- Database: PostgreSQL by default, SQLite only through an explicit env flag -------------
DB_ENGINE = os.environ.get("DB_ENGINE", "postgres").lower()
if DB_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "vezapp_planner"),
            "USER": os.environ.get("POSTGRES_USER", "vezapp"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Locale: Indian context ---------------------------------------------------------------
LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Cookie-carried JWT -------------------------------------------------------------------
# Tokens live in httpOnly cookies set by Django. The browser reaches the API through the
# Next.js /api rewrite, so it is same-origin and SameSite=Lax is enough.
COOKIE_SECURE = env_bool("COOKIE_SECURE", not DEBUG)

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.authentication.CookieJWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 100,
    # A generous ceiling for everything; sign-in and the assistant have their own, lower limits.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "login": "10/min",
        "assistant": "20/min",
        "anon": "120/min",
        "user": "1500/min",
    },
}

# --- AI (Phase 5). The app must work fully without a key. -----------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "") or "claude-sonnet-5-5"
ASSISTANT_MAX_TOKENS = int(os.environ.get("ASSISTANT_MAX_TOKENS", "800"))  # per model call
ASSISTANT_MAX_ROUNDS = 5  # model calls per question (tool-use rounds)
ASSISTANT_DAILY_LIMIT = int(
    os.environ.get("ASSISTANT_DAILY_LIMIT", "200")
)  # questions per user per day
ASSISTANT_MAX_QUESTION_CHARS = 500

# Seed command guard rail: demo data is only created when DEBUG is on.
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
