"""
JWT authentication for WebSocket connections.

Browsers can't set Authorization headers on a WebSocket handshake, so the
access token is passed as a `?token=` query param (or a `Bearer` header for
non-browser clients). This middleware validates it and attaches the user to
the connection scope before the consumer runs.
"""
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def _user_from_token(token: str):
    from rest_framework_simplejwt.exceptions import TokenError
    from rest_framework_simplejwt.tokens import AccessToken

    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        access = AccessToken(token)
        return User.objects.get(id=access["user_id"], is_active=True)
    except (TokenError, KeyError, User.DoesNotExist):
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        token = self._extract_token(scope)
        scope["user"] = await _user_from_token(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)

    @staticmethod
    def _extract_token(scope) -> str | None:
        # 1) query string ?token=...
        qs = parse_qs(scope.get("query_string", b"").decode())
        if "token" in qs:
            return qs["token"][0]
        # 2) Authorization: Bearer <token> header (non-browser clients)
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                parts = value.decode().split()
                if len(parts) == 2 and parts[0].lower() == "bearer":
                    return parts[1]
        return None
