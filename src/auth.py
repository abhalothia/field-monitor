"""OAuth2 client credentials authentication for Sentinel Hub."""

import threading
import time

import requests

from config.settings import SentinelHubConfig


class TokenManager:
    """Thread-safe OAuth2 bearer token manager with auto-refresh."""

    def __init__(self, config: SentinelHubConfig) -> None:
        self._config = config
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    def get_token(self) -> str:
        """Return a valid bearer token, refreshing if expired."""
        with self._lock:
            if self._token and time.time() < self._expires_at - 30:
                return self._token
            return self._refresh()

    def _refresh(self) -> str:
        """Request a new token from Sentinel Hub or CDSE."""
        is_cdse = "dataspace.copernicus" in self._config.token_url

        if is_cdse:
            # CDSE uses form body for credentials
            response = requests.post(
                self._config.token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._config.client_id,
                    "client_secret": self._config.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
        else:
            # Sentinel Hub uses HTTP Basic Auth
            response = requests.post(
                self._config.token_url,
                data={"grant_type": "client_credentials"},
                auth=(self._config.client_id, self._config.client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
        response.raise_for_status()
        data = response.json()

        self._token = data["access_token"]
        expires_in = data.get("expires_in", 300)
        self._expires_at = time.time() + expires_in

        return self._token

    @property
    def is_valid(self) -> bool:
        """Check if the current token is still valid."""
        return self._token is not None and time.time() < self._expires_at - 30
