import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from core.config import settings
from models.company import Company
from services.wave import (
    WaveAuthError,
    WaveClient,
    WaveGraphQLError,
    WaveNotConnectedError,
    build_oauth_authorize_url,
    exchange_oauth_code,
    generate_oauth_state,
    verify_oauth_state,
)

MOCK_SECRET_KEY = "wave-client-test-secret-key-at-least-32-chars!"


@pytest.fixture(autouse=True)
def setup_settings(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", MOCK_SECRET_KEY)
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")
    monkeypatch.setattr(settings, "WAVE_CLIENT_ID", "mock_client_id")
    monkeypatch.setattr(settings, "WAVE_CLIENT_SECRET", "mock_client_secret")
    monkeypatch.setattr(settings, "WAVE_REDIRECT_URI", "http://localhost:8000/api/wave/oauth/callback")


def test_oauth_state_generation_and_verification():
    company_id = uuid.uuid4()
    state = generate_oauth_state(company_id)
    assert isinstance(state, str)

    extracted_id = verify_oauth_state(state)
    assert extracted_id == company_id


def test_oauth_state_expired_or_invalid():
    company_id = uuid.uuid4()
    # Expired state
    expired_state = generate_oauth_state(company_id, expires_in_minutes=-5)
    with pytest.raises(WaveAuthError, match="Invalid or expired"):
        verify_oauth_state(expired_state)

    # Malformed state
    with pytest.raises(WaveAuthError, match="Invalid or expired"):
        verify_oauth_state("not.a.valid.jwt")


def test_build_oauth_authorize_url():
    company_id = uuid.uuid4()
    url = build_oauth_authorize_url(company_id)
    assert url.startswith(settings.WAVE_AUTHORIZE_URL.rstrip("/"))
    assert "response_type=code" in url
    assert "client_id=mock_client_id" in url
    assert "scope=" in url
    assert "business%3Aread" in url or "business:read" in url
    assert "state=" in url


def test_exchange_oauth_code_success():
    mock_transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "access_token": "wave_test_access_token",
                "refresh_token": "wave_test_refresh_token",
                "token_type": "Bearer",
                "expires_in": 7200,
            },
        )
    )
    client = httpx.Client(transport=mock_transport)
    result = exchange_oauth_code("test_code", http_client=client)
    assert result["access_token"] == "wave_test_access_token"
    assert result["refresh_token"] == "wave_test_refresh_token"
    assert result["expires_in"] == 7200


def test_exchange_oauth_code_failure():
    mock_transport = httpx.MockTransport(
        lambda request: httpx.Response(
            400,
            json={"error": "invalid_grant", "error_description": "Code expired"},
        )
    )
    client = httpx.Client(transport=mock_transport)
    with pytest.raises(WaveAuthError, match="Wave token exchange failed"):
        exchange_oauth_code("invalid_code", http_client=client)


def test_wave_client_not_connected():
    company = Company(name="Test Co", wave_equity_account_id="eq_1")
    wave_client = WaveClient(company=company)
    with pytest.raises(WaveNotConnectedError, match="not connected to Wave"):
        wave_client.ensure_valid_token()


def test_wave_client_valid_token_no_refresh():
    future = datetime.now(UTC) + timedelta(hours=1)
    company = Company(
        name="Test Co",
        wave_equity_account_id="eq_1",
        wave_access_token="valid_access_token",
        wave_token_expires_at=future,
    )
    wave_client = WaveClient(company=company)
    assert wave_client.is_token_expired() is False
    token = wave_client.ensure_valid_token()
    assert token == "valid_access_token"


def test_wave_client_auto_refresh_token(db_session):
    past = datetime.now(UTC) - timedelta(minutes=10)
    company = Company(
        name="Test Co",
        wave_equity_account_id="eq_1",
        wave_access_token="expired_token",
        wave_refresh_token="valid_refresh_token",
        wave_token_expires_at=past,
    )
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    mock_transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "access_token": "new_refreshed_access_token",
                "refresh_token": "new_refreshed_refresh_token",
                "expires_in": 3600,
            },
        )
    )
    http_client = httpx.Client(transport=mock_transport)

    wave_client = WaveClient(company=company, db=db_session, http_client=http_client)
    assert wave_client.is_token_expired() is True

    valid_token = wave_client.ensure_valid_token()
    assert valid_token == "new_refreshed_access_token"
    assert company.wave_access_token == "new_refreshed_access_token"
    assert company.wave_refresh_token == "new_refreshed_refresh_token"

    # Verify persisted in database
    db_session.refresh(company)
    assert company.wave_access_token == "new_refreshed_access_token"
    expires_at = company.wave_token_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    assert expires_at > datetime.now(UTC)


def test_wave_client_query_graphql_success():
    future = datetime.now(UTC) + timedelta(hours=1)
    company = Company(
        name="Test Co",
        wave_equity_account_id="eq_1",
        wave_access_token="valid_token",
        wave_token_expires_at=future,
    )

    def handler(request: httpx.Request):
        assert request.headers["Authorization"] == "Bearer valid_token"
        return httpx.Response(
            200,
            json={"data": {"businesses": {"edges": [{"node": {"id": "biz_123", "name": "Test Co"}}]}}},
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    wave_client = WaveClient(company=company, http_client=http_client)
    result = wave_client.query_graphql("query { businesses { edges { node { id name } } } }")
    assert "businesses" in result


def test_wave_client_query_graphql_error():
    future = datetime.now(UTC) + timedelta(hours=1)
    company = Company(
        name="Test Co",
        wave_equity_account_id="eq_1",
        wave_access_token="valid_token",
        wave_token_expires_at=future,
    )

    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            json={"errors": [{"message": "Field 'invalidField' doesn't exist"}]},
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    wave_client = WaveClient(company=company, http_client=http_client)
    with pytest.raises(WaveGraphQLError, match="Field 'invalidField' doesn't exist"):
        wave_client.query_graphql("query { invalidField }")
