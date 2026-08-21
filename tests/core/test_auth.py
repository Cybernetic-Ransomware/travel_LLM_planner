"""Unit tests for src/core/auth.py (JWT RS256 verification).

All tests are marked ``unit`` and make no real network calls.  The JWKS cache
is patched in each test so the HTTP fetch to Auth0 is never executed.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.auth import CurrentUser, _cache, _decode_token, get_current_user
from src.core.exceptions import AuthenticationError


def _generate_rsa_keypair():
    """Return (private_jwk, public_keyset) using authlib + cryptography."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from authlib.jose import JsonWebKey

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_jwk = JsonWebKey.import_key(private_key, {"kty": "RSA", "use": "sig", "alg": "RS256"})
    public_jwk = JsonWebKey.import_key(private_key.public_key(), {"kty": "RSA", "use": "sig", "alg": "RS256"})
    keyset = JsonWebKey.import_key_set({"keys": [public_jwk.as_dict()]})
    return private_jwk, keyset


def _make_token(
    private_jwk,
    *,
    sub: str = "auth0|test-user",
    aud: str = "test-audience",
    iss: str = "https://test.auth0.com/",
    exp_offset: int = 3600,
    email: str | None = None,
    permissions: list[str] | None = None,
) -> str:
    from authlib.jose import jwt

    payload: dict = {
        "sub": sub,
        "aud": aud,
        "iss": iss,
        "exp": int(time.time()) + exp_offset,
        "iat": int(time.time()),
    }
    if email is not None:
        payload["email"] = email
    if permissions is not None:
        payload["permissions"] = permissions

    token_bytes = jwt.encode({"alg": "RS256"}, payload, private_jwk)
    return token_bytes.decode() if isinstance(token_bytes, bytes) else token_bytes


class _CIHeaders:
    """Case-insensitive headers mapping — mirrors Starlette's Headers behaviour."""

    def __init__(self, data: dict[str, str]) -> None:
        self._data = {k.lower(): v for k, v in data.items()}

    def get(self, key: str, default: str = "") -> str:
        return self._data.get(key.lower(), default)


class _MockRequest:
    """Minimal stand-in for starlette.requests.Request with case-insensitive headers."""

    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = _CIHeaders(headers)


def _request_with_token(token: str) -> _MockRequest:
    return _MockRequest({"Authorization": f"Bearer {token}"})


def _request_without_token() -> _MockRequest:
    return _MockRequest({})


@pytest.fixture(autouse=True)
def _reset_cache():
    """Ensure the module-level JWKS cache is empty before and after each test."""
    _cache._keyset = None
    _cache._fetched_at = 0.0
    yield
    _cache._keyset = None
    _cache._fetched_at = 0.0


@pytest.fixture
def auth_settings(monkeypatch):
    """Patch settings inside src.core.auth to activate auth with test tenant."""
    mock = MagicMock()
    mock.auth_active = True
    mock.auth0_domain = "test.auth0.com"
    mock.auth0_audience = "test-audience"
    mock.auth0_issuer = "https://test.auth0.com/"
    import src.core.auth as auth_module

    monkeypatch.setattr(auth_module, "settings", mock)
    return mock


@pytest.fixture
def inactive_auth_settings(monkeypatch):
    """Patch settings to disable auth (AUTH_ENABLED=False)."""
    mock = MagicMock()
    mock.auth_active = False
    import src.core.auth as auth_module

    monkeypatch.setattr(auth_module, "settings", mock)
    return mock


@pytest.fixture
def keypair():
    return _generate_rsa_keypair()


@pytest.mark.unit
class TestCurrentUser:
    def test_anonymous_returns_anonymous_sub(self):
        user = CurrentUser.anonymous()
        assert user.sub == "anonymous"

    def test_anonymous_has_no_email(self):
        user = CurrentUser.anonymous()
        assert user.email is None

    def test_anonymous_has_empty_permissions(self):
        user = CurrentUser.anonymous()
        assert user.permissions == []

    def test_construction_with_all_fields(self):
        user = CurrentUser(sub="auth0|123", email="test@example.com", permissions=["read:places"])
        assert user.sub == "auth0|123"
        assert user.email == "test@example.com"
        assert user.permissions == ["read:places"]


@pytest.mark.unit
class TestAuthDisabled:
    async def test_returns_anonymous_when_auth_inactive(self, inactive_auth_settings):
        request = _request_without_token()
        user = await get_current_user(request)
        assert user.sub == "anonymous"

    async def test_no_token_needed_when_auth_inactive(self, inactive_auth_settings):
        request = _request_without_token()
        user = await get_current_user(request)
        assert isinstance(user, CurrentUser)


@pytest.mark.unit
class TestValidToken:
    async def test_valid_token_returns_current_user(self, auth_settings, keypair):
        private_jwk, keyset = keypair
        token = _make_token(private_jwk, aud="test-audience", iss="https://test.auth0.com/")

        async def mock_get(url, *, force_refresh=False):
            return keyset

        with patch.object(_cache, "get", side_effect=mock_get):
            user = await get_current_user(_request_with_token(token))

        assert user.sub == "auth0|test-user"

    async def test_email_claim_extracted(self, auth_settings, keypair):
        private_jwk, keyset = keypair
        token = _make_token(private_jwk, aud="test-audience", iss="https://test.auth0.com/", email="user@example.com")

        async def mock_get(url, *, force_refresh=False):
            return keyset

        with patch.object(_cache, "get", side_effect=mock_get):
            user = await get_current_user(_request_with_token(token))

        assert user.email == "user@example.com"

    async def test_permissions_claim_extracted(self, auth_settings, keypair):
        private_jwk, keyset = keypair
        token = _make_token(
            private_jwk,
            aud="test-audience",
            iss="https://test.auth0.com/",
            permissions=["write:places", "read:places"],
        )

        async def mock_get(url, *, force_refresh=False):
            return keyset

        with patch.object(_cache, "get", side_effect=mock_get):
            user = await get_current_user(_request_with_token(token))

        assert "write:places" in user.permissions


@pytest.mark.unit
class TestMissingOrMalformedHeader:
    async def test_missing_header_raises_401(self, auth_settings):
        with pytest.raises(AuthenticationError) as exc_info:
            await get_current_user(_request_without_token())
        assert exc_info.value.status_code == 401

    async def test_missing_bearer_prefix_raises_401(self, auth_settings):
        request = _MockRequest({"Authorization": "Token abc123"})
        with pytest.raises(AuthenticationError) as exc_info:
            await get_current_user(request)
        assert exc_info.value.status_code == 401

    async def test_www_authenticate_header_present(self, auth_settings):
        with pytest.raises(AuthenticationError) as exc_info:
            await get_current_user(_request_without_token())
        assert "WWW-Authenticate" in exc_info.value.headers


@pytest.mark.unit
class TestInvalidToken:
    async def test_wrong_signature_raises_401(self, auth_settings, keypair):
        private_jwk, _ = keypair
        _, other_keyset = _generate_rsa_keypair()
        token = _make_token(private_jwk, aud="test-audience", iss="https://test.auth0.com/")

        call_count = 0

        async def mock_get(url, *, force_refresh=False):
            nonlocal call_count
            call_count += 1
            return other_keyset

        with pytest.raises(AuthenticationError) as exc_info:
            with patch.object(_cache, "get", side_effect=mock_get):
                await get_current_user(_request_with_token(token))

        assert exc_info.value.status_code == 401
        assert call_count == 2, "Cache should be refreshed once on signature failure"

    async def test_expired_token_raises_401(self, auth_settings, keypair):
        private_jwk, keyset = keypair
        token = _make_token(private_jwk, aud="test-audience", iss="https://test.auth0.com/", exp_offset=-10)

        async def mock_get(url, *, force_refresh=False):
            return keyset

        with pytest.raises(AuthenticationError) as exc_info:
            with patch.object(_cache, "get", side_effect=mock_get):
                await get_current_user(_request_with_token(token))

        assert exc_info.value.status_code == 401

    async def test_wrong_audience_raises_401(self, auth_settings, keypair):
        private_jwk, keyset = keypair
        token = _make_token(private_jwk, aud="wrong-audience", iss="https://test.auth0.com/")

        async def mock_get(url, *, force_refresh=False):
            return keyset

        with pytest.raises(AuthenticationError) as exc_info:
            with patch.object(_cache, "get", side_effect=mock_get):
                await get_current_user(_request_with_token(token))

        assert exc_info.value.status_code == 401

    async def test_wrong_issuer_raises_401(self, auth_settings, keypair):
        private_jwk, keyset = keypair
        token = _make_token(private_jwk, aud="test-audience", iss="https://evil.example.com/")

        async def mock_get(url, *, force_refresh=False):
            return keyset

        with pytest.raises(AuthenticationError) as exc_info:
            with patch.object(_cache, "get", side_effect=mock_get):
                await get_current_user(_request_with_token(token))

        assert exc_info.value.status_code == 401


@pytest.mark.unit
class TestJwksCache:
    async def test_cache_not_fetched_when_auth_inactive(self, inactive_auth_settings):
        fetched = []

        async def mock_fetch(url):
            fetched.append(url)

        with patch.object(_cache, "_fetch", side_effect=mock_fetch):
            await get_current_user(_request_without_token())

        assert fetched == [], "JWKS should not be fetched when auth is disabled"

    async def test_stale_cache_triggers_refetch(self, auth_settings, keypair):
        private_jwk, keyset = keypair
        token = _make_token(private_jwk, aud="test-audience", iss="https://test.auth0.com/")

        _cache._keyset = keyset
        _cache._fetched_at = time.monotonic() - 7200

        fetch_calls = []

        original_fetch = _cache._fetch

        async def counting_fetch(url):
            fetch_calls.append(url)
            _cache._keyset = keyset
            _cache._fetched_at = time.monotonic()

        with patch.object(_cache, "_fetch", side_effect=counting_fetch):
            await get_current_user(_request_with_token(token))

        assert len(fetch_calls) == 1, "Stale cache should trigger exactly one refetch"
