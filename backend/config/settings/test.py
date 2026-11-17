"""Test settings: in-memory SQLite, fast hashing, no throttling."""

from .base import *  # noqa: F401,F403

SECRET_KEY = "test-only-secret-key-not-for-any-real-use"
DEBUG = False
COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False  # the test client speaks plain http

# Tests never reach the real AI service, whatever key is in .env. They start in basic mode and the
# few tests of the Claude layer switch it on with a stand-in client.
ANTHROPIC_API_KEY = ""

# The long-standing plan tests exercise the full route with melting scheduled by the engine. The
# moulding-and-melting phase tests switch to the real defaults with the `phase_defaults` fixture.
PLANNED_OPERATIONS = [
    "core", "moulding", "melting", "knockout", "shot_blasting", "fettling", "grinding",
    "heat_treatment", "machining", "painting", "inspection", "packing", "dispatch",
]  # fmt: skip
MELTING_PLAN_MODE = "engine"

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
