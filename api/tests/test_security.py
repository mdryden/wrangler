from datetime import timedelta

import pytest

from core.security import (
    create_access_token,
    decode_access_token,
    verify_admin_credentials,
)

MOCK_USERNAME = "test_admin"
MOCK_PASSWORD = "test_password_123"
MOCK_SECRET_KEY = "test-jwt-secret-key-32-chars-long!"
MOCK_ALGORITHM = "HS256"


def test_verify_admin_credentials_success():
    assert (
        verify_admin_credentials(
            username="test_admin",
            password="test_password_123",
            expected_username=MOCK_USERNAME,
            expected_password=MOCK_PASSWORD,
        )
        is True
    )


def test_verify_admin_credentials_invalid_username():
    assert (
        verify_admin_credentials(
            username="wrong_user",
            password="test_password_123",
            expected_username=MOCK_USERNAME,
            expected_password=MOCK_PASSWORD,
        )
        is False
    )


def test_verify_admin_credentials_invalid_password():
    assert (
        verify_admin_credentials(
            username="test_admin",
            password="wrong_password",
            expected_username=MOCK_USERNAME,
            expected_password=MOCK_PASSWORD,
        )
        is False
    )


def test_verify_admin_credentials_both_invalid():
    assert (
        verify_admin_credentials(
            username="wrong_user",
            password="wrong_password",
            expected_username=MOCK_USERNAME,
            expected_password=MOCK_PASSWORD,
        )
        is False
    )


def test_verify_admin_credentials_empty():
    assert (
        verify_admin_credentials(
            username="",
            password="",
            expected_username=MOCK_USERNAME,
            expected_password=MOCK_PASSWORD,
        )
        is False
    )
    assert (
        verify_admin_credentials(
            username=MOCK_USERNAME,
            password="",
            expected_username=MOCK_USERNAME,
            expected_password=MOCK_PASSWORD,
        )
        is False
    )
    assert (
        verify_admin_credentials(
            username="",
            password=MOCK_PASSWORD,
            expected_username=MOCK_USERNAME,
            expected_password=MOCK_PASSWORD,
        )
        is False
    )


def test_create_and_decode_access_token():
    data = {"sub": "test_admin", "scope": "admin"}
    token = create_access_token(
        data=data,
        secret_key=MOCK_SECRET_KEY,
        algorithm=MOCK_ALGORITHM,
        expires_delta=timedelta(minutes=30),
    )
    assert isinstance(token, str)

    payload = decode_access_token(
        token=token,
        secret_key=MOCK_SECRET_KEY,
        algorithms=[MOCK_ALGORITHM],
    )
    assert payload["sub"] == "test_admin"
    assert payload["scope"] == "admin"
    assert "exp" in payload
    assert "iat" in payload
    assert payload["exp"] - payload["iat"] == 1800


def test_decode_access_token_expired():
    data = {"sub": "test_admin"}
    # Negative expires_delta to create an already-expired token
    token = create_access_token(
        data=data,
        secret_key=MOCK_SECRET_KEY,
        algorithm=MOCK_ALGORITHM,
        expires_delta=timedelta(seconds=-10),
    )

    with pytest.raises(ValueError, match="Invalid token.*expired"):
        decode_access_token(
            token=token,
            secret_key=MOCK_SECRET_KEY,
            algorithms=[MOCK_ALGORITHM],
        )


def test_decode_access_token_tampered_signature():
    token = create_access_token(
        data={"sub": "test_admin"},
        secret_key=MOCK_SECRET_KEY,
        algorithm=MOCK_ALGORITHM,
    )
    parts = token.split(".")
    tampered_token = f"{parts[0]}.{parts[1]}.tamperedsignature"

    with pytest.raises(ValueError, match="Invalid token"):
        decode_access_token(
            token=tampered_token,
            secret_key=MOCK_SECRET_KEY,
            algorithms=[MOCK_ALGORITHM],
        )


def test_decode_access_token_wrong_secret():
    token = create_access_token(
        data={"sub": "test_admin"},
        secret_key=MOCK_SECRET_KEY,
        algorithm=MOCK_ALGORITHM,
    )

    with pytest.raises(ValueError, match="Invalid token"):
        decode_access_token(
            token=token,
            secret_key="completely-different-mock-secret-key!",
            algorithms=[MOCK_ALGORITHM],
        )


def test_decode_access_token_malformed():
    with pytest.raises(ValueError, match="Invalid token"):
        decode_access_token(
            token="not.a.valid.jwt",
            secret_key=MOCK_SECRET_KEY,
            algorithms=[MOCK_ALGORITHM],
        )
