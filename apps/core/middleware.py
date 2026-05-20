"""
Request-scoped context for audit logging.

Stashes the current actor and client IP in a thread-local so that model
signals (which have no request object) can attribute changes to a user.
"""
import threading

_state = threading.local()


def get_current_actor():
    return getattr(_state, "actor", None)


def get_current_ip():
    return getattr(_state, "ip", None)


class AuditContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _state.actor = getattr(request, "user", None)
        if _state.actor is not None and not _state.actor.is_authenticated:
            _state.actor = None
        _state.ip = self._client_ip(request)
        try:
            return self.get_response(request)
        finally:
            _state.actor = None
            _state.ip = None

    @staticmethod
    def _client_ip(request):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")
