"""Test settings: in-memory SQLite, fast hashing, no throttling."""

from .base import *  # noqa: F401,F403

SECRET_KEY = "test-only-secret-key-not-for-any-real-use"
DEBUG = False
COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False  # the test client speaks plain http

# Tests never reach the real AI service, whatever key is in .env. They start in basic mode and the
# few tests of the Claude layer switch it on with a stand-in client.
ANTHROPIC_API_KEY = ""

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        "login": "100000/min",
        "assistant": "100000/min",
        "anon": "100000/min",
        "user": "100000/min",
    },
}

LOGGING = {"version": 1, "disable_existing_loggers": True}
