"""Access-token verification — asymmetric (ES256/RS256) and legacy HS256 paths."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from app.core.errors import APIError

from app.core import security
from app.core.config import settings


def _claims(**over):
    now = int(time.time())
    base = {
        "sub": "11111111-2222-3333-4444-555555555555",
        "email": "agent@example.com",
        "aud": "authenticated",
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + 3600,
    }
    base.update(over)
    return base


def test_hs256_token_verified_with_secret(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", "test-secret-at-least-32-bytes-long!!", raising=False)
    token = jwt.encode(_claims(), "test-secret-at-least-32-bytes-long!!", algorithm="HS256")
    user = security.decode_access_token(token)
    assert user.sub == "11111111-2222-3333-4444-555555555555"
    assert user.email == "agent@example.com"


def test_hs256_rejected_when_secret_missing(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", "", raising=False)
    token = jwt.encode(_claims(), "whatever", algorithm="HS256")
    with pytest.raises(APIError) as ei:
        security.decode_access_token(token)
    assert ei.value.status_code == 401


def test_hs256_rejected_on_wrong_secret(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", "right-secret-at-least-32-bytes-long!", raising=False)
    token = jwt.encode(_claims(), "wrong-secret-at-least-32-bytes-long!", algorithm="HS256")
    with pytest.raises(APIError) as ei:
        security.decode_access_token(token)
    assert ei.value.status_code == 401


def test_unsigned_token_is_rejected(monkeypatch):
    """The old dev fallback accepted alg=none / unverified claims. It must not."""
    monkeypatch.setattr(settings, "supabase_jwt_secret", "", raising=False)
    token = jwt.encode(_claims(), key="", algorithm="none")
    with pytest.raises(APIError) as ei:
        security.decode_access_token(token)
    assert ei.value.status_code == 401


def test_expired_token_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", "test-secret-at-least-32-bytes-long!!", raising=False)
    token = jwt.encode(_claims(exp=int(time.time()) - 10), "test-secret-at-least-32-bytes-long!!", algorithm="HS256")
    with pytest.raises(APIError) as ei:
        security.decode_access_token(token)
    assert ei.value.status_code == 401


def test_wrong_issuer_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", "test-secret-at-least-32-bytes-long!!", raising=False)
    token = jwt.encode(_claims(iss="https://evil.example.com"), "test-secret-at-least-32-bytes-long!!", algorithm="HS256")
    with pytest.raises(APIError) as ei:
        security.decode_access_token(token)
    assert ei.value.status_code == 401


def test_es256_token_verified_against_jwks(monkeypatch):
    """A real ES256 token verifies when its key is served by the project JWKS."""
    key = ec.generate_private_key(ec.SECP256R1())
    token = jwt.encode(_claims(), key, algorithm="ES256", headers={"kid": "test-kid"})

    class _StubSigningKey:
        def __init__(self, public_key):
            self.key = public_key

    class _StubJWKClient:
        def get_signing_key_from_jwt(self, _token):
            return _StubSigningKey(key.public_key())

    security.reset_jwk_client()
    monkeypatch.setattr(security, "_get_jwk_client", lambda: _StubJWKClient())
    user = security.decode_access_token(token)
    assert user.sub == "11111111-2222-3333-4444-555555555555"


def test_es256_rejected_when_signed_by_other_key(monkeypatch):
    project_key = ec.generate_private_key(ec.SECP256R1())
    attacker_key = ec.generate_private_key(ec.SECP256R1())
    token = jwt.encode(_claims(), attacker_key, algorithm="ES256", headers={"kid": "test-kid"})

    class _StubSigningKey:
        def __init__(self, public_key):
            self.key = public_key

    class _StubJWKClient:
        def get_signing_key_from_jwt(self, _token):
            return _StubSigningKey(project_key.public_key())

    security.reset_jwk_client()
    monkeypatch.setattr(security, "_get_jwk_client", lambda: _StubJWKClient())
    with pytest.raises(APIError) as ei:
        security.decode_access_token(token)
    assert ei.value.status_code == 401
