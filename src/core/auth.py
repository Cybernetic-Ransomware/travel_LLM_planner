"""JWT RS256 authentication for FastAPI endpoints.

Verifies Auth0-issued RS256 JWTs by fetching the JWKS from the Auth0
domain and caching the key set in memory (TTL = 1 h).

When ``settings.auth_active`` is False (default), every dependency call
returns ``CurrentUser.anonymous()`` and no network request is made — this
allows local development and tests to run without Auth0 credentials.
"""

from __future__ import annotations

import time
from typing import Annotated

import httpx
from authlib.jose import JsonWebKey, jwt
from authlib.jose.errors import JoseError
from fastapi import Depends, Request
from pydantic import BaseModel

from src.config.config import settings
from src.core.exceptions import AuthenticationError

_JWKS_TTL_SECONDS = 3600


class _JwksCache:
    """In-memory cache for the Auth0 JWKS key set with a 1-hour TTL.

    On a cache miss (expired or empty) the key set is fetched over HTTPS.
    When JWT verification fails with the cached keys, the cache is refreshed
    once to handle key rotation before the error is propagated to the caller.
    """

    def __init__(self) -> None:
        self._keyset = None
        self._fetched_at: float = 0.0

    def _is_stale(self) -> bool:
        return time.monotonic() - self._fetched_at >= _JWKS_TTL_SECONDS

    async def _fetch(self, url: str) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
        self._keyset = JsonWebKey.import_key_set(data)
        self._fetched_at = time.monotonic()

    async def get(self, url: str, *, force_refresh: bool = False):
        if force_refresh or self._keyset is None or self._is_stale():
            await self._fetch(url)
        return self._keyset


_cache = _JwksCache()


class CurrentUser(BaseModel):
    """Minimal representation of an authenticated caller.

    Built from JWT claims (``sub``, ``email``, ``permissions``).
    ``anonymous()`` is returned when auth is disabled via ``AUTH_ENABLED=False``.
    """

    sub: str
    email: str | None = None
    permissions: list[str] = []

    @classmethod
    def anonymous(cls) -> CurrentUser:
        return cls(sub="anonymous")


def _decode_token(token: str, keyset) -> dict:
    """Decode and validate a JWT against the provided key set.

    Returns the claims dict on success.  Raises ``AuthenticationError`` on
    any verification failure (bad signature, expired, wrong audience/issuer).
    """
    claims_options = {
        "iss": {"essential": True, "value": settings.auth0_issuer},
        "aud": {"essential": True, "value": settings.auth0_audience},
    }
    claims = jwt.decode(token, keyset, claims_options=claims_options)
    claims.validate()
    return claims


async def get_current_user(request: Request) -> CurrentUser:
    """FastAPI dependency that verifies the Bearer token and returns the caller.

    Raises ``AuthenticationError`` (HTTP 401) when:
    - ``AUTH_ENABLED=True`` and the ``Authorization`` header is absent or malformed,
    - the JWT signature, expiry, audience, or issuer check fails.

    Returns ``CurrentUser.anonymous()`` when ``settings.auth_active`` is False,
    allowing development and testing without an Auth0 tenant.
    """
    if not settings.auth_active:
        return CurrentUser.anonymous()

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise AuthenticationError("Missing or invalid Authorization header")

    token = auth_header[len("Bearer ") :]
    jwks_url = f"https://{settings.auth0_domain}/.well-known/jwks.json"

    keyset = await _cache.get(jwks_url)
    try:
        claims = _decode_token(token, keyset)
    except JoseError, Exception:
        # Attempt a JWKS refresh in case the signing key was rotated.
        try:
            keyset = await _cache.get(jwks_url, force_refresh=True)
            claims = _decode_token(token, keyset)
        except AuthenticationError:
            raise
        except Exception as exc:
            raise AuthenticationError("Invalid or expired token") from exc

    return CurrentUser(
        sub=claims.get("sub", ""),
        email=claims.get("email"),
        permissions=claims.get("permissions", []),
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
