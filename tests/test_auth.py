"""Tests for OAuth2 token management."""

import time

import pytest
import responses

from config.settings import SentinelHubConfig
from src.auth import TokenManager

TOKEN_URL = (
    "https://services.sentinel-hub.com/auth/realms/main/"
    "protocol/openid-connect/token"
)


def _make_config() -> SentinelHubConfig:
    return SentinelHubConfig(
        client_id="test-id",
        client_secret="test-secret",
    )


def _mock_token_response(token: str = "access-token-123", expires_in: int = 300):
    responses.add(
        responses.POST,
        TOKEN_URL,
        json={"access_token": token, "expires_in": expires_in},
        status=200,
    )


class TestTokenManager:
    @responses.activate
    def test_acquires_token_on_first_call(self):
        _mock_token_response("my-token")
        mgr = TokenManager(_make_config())

        token = mgr.get_token()

        assert token == "my-token"

    @responses.activate
    def test_caches_token_on_subsequent_calls(self):
        _mock_token_response("cached-token")
        mgr = TokenManager(_make_config())

        token1 = mgr.get_token()
        token2 = mgr.get_token()

        assert token1 == token2
        assert len(responses.calls) == 1, "Should only call API once"

    @responses.activate
    def test_is_valid_reflects_token_state(self):
        _mock_token_response()
        mgr = TokenManager(_make_config())

        assert not mgr.is_valid
        mgr.get_token()
        assert mgr.is_valid

    @responses.activate
    def test_raises_on_auth_failure(self):
        responses.add(
            responses.POST, TOKEN_URL,
            json={"error": "unauthorized"}, status=401,
        )
        mgr = TokenManager(_make_config())

        with pytest.raises(Exception):
            mgr.get_token()
