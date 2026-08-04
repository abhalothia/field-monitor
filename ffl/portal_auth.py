"""Phone-OTP provider boundary and signed customer-portal browser session."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
import time
from typing import Any, Optional, Protocol
from urllib.parse import urlparse

import httpx


PORTAL_SESSION_FLAG = "ffl_portal_session"
PORTAL_SESSION_SCOPE = "customer-portal-v1"
DEFAULT_PORTAL_SESSION_MAX_AGE_SECONDS = 12 * 60 * 60
MIN_PORTAL_SESSION_MAX_AGE_SECONDS = 5 * 60
MAX_PORTAL_SESSION_MAX_AGE_SECONDS = 24 * 60 * 60


class PortalOtpError(RuntimeError):
    """A safe OTP failure that must not disclose provider or account detail."""


@dataclass(frozen=True)
class VerifiedPhone:
    auth_subject: str
    phone_e164: str


class PortalOtpProvider(Protocol):
    """The only phone-OTP operations exposed to the portal HTTP boundary."""

    @property
    def configured(self) -> bool: ...

    @property
    def delivery_channel(self) -> Optional[str]: ...

    def request_code(self, phone_e164: str) -> None: ...

    def verify_code(self, phone_e164: str, code: str) -> VerifiedPhone: ...


class DisabledPortalOtpProvider:
    """Fail closed when a deployment has not configured a real identity provider."""

    configured = False
    delivery_channel = None

    def request_code(self, phone_e164: str) -> None:
        del phone_e164
        raise PortalOtpError("phone sign-in is not configured")

    def verify_code(self, phone_e164: str, code: str) -> VerifiedPhone:
        del phone_e164, code
        raise PortalOtpError("phone sign-in is not configured")


class SupabasePhoneOtpProvider:
    """Server-side proxy to Supabase Auth's phone OTP endpoints.

    The public/publishable key is permitted in a browser, but keeping the calls
    server-side lets AGRO CEO first verify that a phone is explicitly invited
    into this tenant.  ``shouldCreateUser`` is true *only after* that private
    eligibility check, so unknown TrackWick contacts cannot create accounts.
    """

    def __init__(self, *, base_url: str, publishable_key: str, delivery_channel: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._publishable_key = publishable_key
        self.delivery_channel = delivery_channel
        self.configured = True

    @classmethod
    def from_environment(cls) -> PortalOtpProvider:
        base_url = os.environ.get("FFL_SUPABASE_URL", "").strip().rstrip("/")
        publishable_key = os.environ.get("FFL_SUPABASE_PUBLISHABLE_KEY", "").strip()
        delivery_channel = os.environ.get("FFL_PORTAL_OTP_CHANNEL", "sms").strip().lower()
        parsed = urlparse(base_url)
        if (
            not base_url
            or not publishable_key
            or parsed.scheme != "https"
            or not parsed.netloc
            or parsed.path not in {"", "/"}
            or parsed.params or parsed.query or parsed.fragment
            or delivery_channel not in {"sms", "whatsapp"}
        ):
            return DisabledPortalOtpProvider()
        return cls(
            base_url=base_url, publishable_key=publishable_key, delivery_channel=delivery_channel,
        )

    def _headers(self) -> dict[str, str]:
        return {"apikey": self._publishable_key, "Authorization": "Bearer " + self._publishable_key}

    def request_code(self, phone_e164: str) -> None:
        try:
            response = httpx.post(
                self._base_url + "/auth/v1/otp", headers=self._headers(),
                json={
                    "phone": phone_e164,
                    "create_user": True,
                    "options": {"channel": self.delivery_channel},
                }, timeout=10.0,
            )
        except httpx.HTTPError as error:
            raise PortalOtpError("phone sign-in provider is unavailable") from error
        if response.status_code < 200 or response.status_code >= 300:
            raise PortalOtpError("phone sign-in provider rejected the request")

    def verify_code(self, phone_e164: str, code: str) -> VerifiedPhone:
        try:
            response = httpx.post(
                self._base_url + "/auth/v1/verify", headers=self._headers(),
                json={"phone": phone_e164, "token": code, "type": self.delivery_channel}, timeout=10.0,
            )
            payload = response.json() if 200 <= response.status_code < 300 else None
        except (httpx.HTTPError, ValueError) as error:
            raise PortalOtpError("phone code could not be verified") from error
        if not isinstance(payload, dict):
            raise PortalOtpError("phone code could not be verified")
        user = payload.get("user")
        if not isinstance(user, dict):
            raise PortalOtpError("phone code could not be verified")
        subject = user.get("id")
        verified_phone = user.get("phone")
        if not isinstance(subject, str) or not isinstance(verified_phone, str):
            raise PortalOtpError("phone code could not be verified")
        return VerifiedPhone(auth_subject=subject, phone_e164=verified_phone)


def configured_portal_session_secret() -> Optional[str]:
    value = os.environ.get("FFL_PORTAL_SESSION_SECRET")
    return value if value else None


def configured_portal_session_max_age_seconds() -> Optional[int]:
    raw = os.environ.get("FFL_PORTAL_SESSION_MAX_AGE_SECONDS")
    if raw is None or raw == "":
        return DEFAULT_PORTAL_SESSION_MAX_AGE_SECONDS
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if not MIN_PORTAL_SESSION_MAX_AGE_SECONDS <= value <= MAX_PORTAL_SESSION_MAX_AGE_SECONDS:
        return None
    return value


def portal_session_configuration_is_present(app: Any) -> bool:
    return bool(
        getattr(app.state, "portal_session_secret", None)
        and isinstance(getattr(app.state, "portal_session_max_age_seconds", None), int)
        and getattr(app.state, "portal_session_max_age_seconds") > 0
    )


def portal_session_now(app: Any) -> int:
    return int(getattr(app.state, "portal_session_clock", time.time)())


def _membership_binding(app: Any, portal_id: str, membership_id: str) -> str:
    material = PORTAL_SESSION_SCOPE + "\x1f" + portal_id + "\x1f" + membership_id
    return hmac.new(
        app.state.portal_session_secret.encode("utf-8"), material.encode("utf-8"), hashlib.sha256,
    ).hexdigest()


def begin_portal_session(app: Any, session: dict[str, Any], *, portal_id: str, membership_id: str) -> int:
    """Set an opaque, signed session only after a verified OTP exchange."""

    if not portal_session_configuration_is_present(app):
        raise ValueError("customer portal sign-in is not configured")
    issued_at = portal_session_now(app)
    expires_at = issued_at + app.state.portal_session_max_age_seconds
    session[PORTAL_SESSION_FLAG] = {
        "scope": PORTAL_SESSION_SCOPE,
        "portal_id": portal_id,
        "membership_id": membership_id,
        "binding": _membership_binding(app, portal_id, membership_id),
        "issued_at": issued_at,
        "expires_at": expires_at,
    }
    return expires_at


def active_portal_session(app: Any, session: dict[str, Any]) -> Optional[dict[str, int | str]]:
    value = session.get(PORTAL_SESSION_FLAG)
    if not isinstance(value, dict) or not portal_session_configuration_is_present(app):
        if value is not None:
            session.pop(PORTAL_SESSION_FLAG, None)
        return None
    portal_id = value.get("portal_id")
    membership_id = value.get("membership_id")
    binding = value.get("binding")
    issued_at = value.get("issued_at")
    expires_at = value.get("expires_at")
    if (
        value.get("scope") != PORTAL_SESSION_SCOPE
        or not all(isinstance(item, str) and item for item in (portal_id, membership_id, binding))
        or any(isinstance(item, bool) or not isinstance(item, int) for item in (issued_at, expires_at))
        or issued_at > expires_at
        or expires_at - issued_at > app.state.portal_session_max_age_seconds
        or expires_at <= portal_session_now(app)
        or not hmac.compare_digest(binding, _membership_binding(app, portal_id, membership_id))
    ):
        session.pop(PORTAL_SESSION_FLAG, None)
        return None
    return {
        "portal_id": portal_id, "membership_id": membership_id,
        "issued_at": issued_at, "expires_at": expires_at,
    }


def end_portal_session(session: dict[str, Any]) -> None:
    session.pop(PORTAL_SESSION_FLAG, None)
