"""Request-scoped context used by the audit trail."""

from contextvars import ContextVar

_current_user: ContextVar = ContextVar("vezapp_current_user", default=None)


_audit_suppressed: ContextVar = ContextVar("vezapp_audit_suppressed", default=False)


class audit_suppressed:
    """Context manager for system seeding (standard types, defaults) that should not fill the log."""

    def __enter__(self):
        self._token = _audit_suppressed.set(True)

    def __exit__(self, *exc):
        _audit_suppressed.reset(self._token)


def is_audit_suppressed() -> bool:
    return _audit_suppressed.get()


def set_current_user(user):
    _current_user.set(user)


def get_current_user():
    return _current_user.get()
