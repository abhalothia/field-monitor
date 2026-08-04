from pathlib import Path

from fastapi.testclient import TestClient

from ffl.app import create_app
from ffl.portal import (
    activate_phone_identity,
    invite_phone_identity,
    normalise_phone_e164,
    portal_host_is_under_base,
    provision_fortune_portal,
)
from ffl.portal_auth import VerifiedPhone
from ffl.portal_auth import SupabasePhoneOtpProvider
from ffl.services.access import provision_initial_fortune_team


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "db" / "postgres" / "0012_agro_customer_portals.sql"


class FakePhoneProvider:
    configured = True
    delivery_channel = "sms"

    def __init__(self):
        self.requested = []

    def request_code(self, phone_e164):
        self.requested.append(phone_e164)

    def verify_code(self, phone_e164, code):
        if code != "123456":
            raise RuntimeError("bad code")
        return VerifiedPhone(auth_subject="auth-user-daksh", phone_e164=phone_e164)


def _portal_app(tmp_path):
    provider = FakePhoneProvider()
    app = create_app(
        str(tmp_path / "portal.db"), portal_auth_provider=provider,
        portal_session_secret="portal-test-signing-secret", portal_session_max_age_seconds=600,
    )
    provision_initial_fortune_team(app.state.conn, observed_at="2026-08-04T12:00:00+00:00")
    portal = provision_fortune_portal(app.state.conn, observed_at="2026-08-04T12:00:00+00:00")
    return app, provider, portal


def test_customer_portal_schema_keeps_crm_contacts_out_of_identity_authority():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS agro_customer_portals" in sql
    assert "CREATE TABLE IF NOT EXISTS agro_portal_identities" in sql
    assert "CREATE TABLE IF NOT EXISTS agro_portal_memberships" in sql
    assert "portal_role IN ('owner', 'admin', 'field_worker', 'farmer')" in sql
    assert "TrackWick contact point is deliberately not an identity" in sql
    assert "REVOKE ALL ON TABLE agro_portal_identities FROM PUBLIC" in sql


def test_fortune_portal_provisions_hostname_and_staff_roles_but_no_logins(ffl_db):
    provision_initial_fortune_team(ffl_db, observed_at="2026-08-04T12:00:00+00:00")
    portal = provision_fortune_portal(ffl_db, observed_at="2026-08-04T12:00:00+00:00")
    rows = ffl_db.execute(
        """SELECT person.name, membership.portal_role, membership.membership_status
           FROM portal_memberships membership JOIN people person ON person.id = membership.person_id
           ORDER BY person.name"""
    ).fetchall()

    assert (portal.slug, portal.hostname, portal.display_name) == (
        "fortune", "fortune.agroceo.com", "Fortune Rice",
    )
    assert [dict(row) for row in rows] == [
        {"name": "Aakash Bhalothia", "portal_role": "owner", "membership_status": "identity_pending"},
        {"name": "Ajay Bhalothia", "portal_role": "owner", "membership_status": "identity_pending"},
        {"name": "Daksh Bhatia", "portal_role": "admin", "membership_status": "identity_pending"},
    ]


def test_phone_identity_requires_explicit_invitation_then_verified_otp(ffl_db):
    provision_initial_fortune_team(ffl_db, observed_at="2026-08-04T12:00:00+00:00")
    portal = provision_fortune_portal(ffl_db, observed_at="2026-08-04T12:00:00+00:00")
    daksh = ffl_db.execute("SELECT id FROM people WHERE name = ?", ("Daksh Bhatia",)).fetchone()

    identity_id = invite_phone_identity(
        ffl_db, portal_id=portal.id, person_id=daksh["id"], phone_e164="+919876543210",
        observed_at="2026-08-04T12:01:00+00:00",
    )
    principal = activate_phone_identity(
        ffl_db, portal_id=portal.id, phone_e164="+919876543210", auth_subject="auth-daksh",
        observed_at="2026-08-04T12:02:00+00:00",
    )
    identity = ffl_db.execute(
        "SELECT identity_status, auth_subject FROM portal_identities WHERE id = ?", (identity_id,)
    ).fetchone()
    access = ffl_db.execute(
        "SELECT identity_phone, identity_status FROM access_memberships WHERE person_id = ?", (daksh["id"],)
    ).fetchone()

    assert principal.person_name == "Daksh Bhatia"
    assert principal.portal_role == "admin"
    assert dict(identity) == {"identity_status": "active", "auth_subject": "auth-daksh"}
    assert dict(access) == {"identity_phone": "+919876543210", "identity_status": "active"}


def test_portal_phone_flow_is_generic_for_unknown_numbers_and_unlocks_only_an_active_admin(tmp_path):
    app, provider, portal = _portal_app(tmp_path)
    daksh = app.state.conn.execute("SELECT id FROM people WHERE name = ?", ("Daksh Bhatia",)).fetchone()
    invite_phone_identity(
        app.state.conn, portal_id=portal.id, person_id=daksh["id"], phone_e164="+919876543210",
        observed_at="2026-08-04T12:01:00+00:00",
    )

    with TestClient(app, base_url="https://fortune.agroceo.com") as client:
        portal_shell = client.get("/")
        portal_css = client.get("/assets/portal.css")
        portal_js = client.get("/assets/portal.js")
        bootstrap = client.get("/api/v1/portal/bootstrap")
        anonymous = client.get("/api/v1/portal/session")
        unknown = client.post("/api/v1/portal/auth/request-code", json={"phone": "+919999999999"})
        known = client.post("/api/v1/portal/auth/request-code", json={"phone": "+919876543210"})
        authenticated = client.post(
            "/api/v1/portal/auth/verify-code", json={"phone": "+919876543210", "code": "123456"},
        )
        session = client.get("/api/v1/portal/session")
        board = client.get("/api/v1/trackwick/board")
        manager_session = client.get("/api/v1/manager-session/status")
        logout = client.post("/api/v1/portal/auth/logout")
        signed_out = client.get("/api/v1/portal/session")

    assert portal_shell.status_code == 200 and "Sign in with your phone." in portal_shell.text
    assert portal_css.status_code == portal_js.status_code == 200
    assert bootstrap.json() == {
        "portal": {"slug": "fortune", "name": "Fortune Rice"},
        "phone_sign_in": {"enabled": True, "delivery_channel": "sms"},
    }
    assert anonymous.status_code == 401
    assert unknown.json() == known.json() == {"status": "code_requested"}
    assert provider.requested == ["+919876543210"]
    assert authenticated.json()["next_path"] == "/manager"
    assert session.json()["portal_role"] == "admin"
    assert board.status_code == 200
    assert manager_session.json()["auth_method"] == "phone"
    assert logout.json() == {"status": "signed_out"}
    assert signed_out.status_code == 401


def test_phone_and_hostname_input_are_strict():
    assert normalise_phone_e164(" +91 98765 43210 ") == "+919876543210"
    assert portal_host_is_under_base("fortune.agroceo.com", "agroceo.com") is True
    assert portal_host_is_under_base("north.fortune.agroceo.com", "agroceo.com") is False
    assert portal_host_is_under_base("fortune.evil.example", "agroceo.com") is False


def test_supabase_phone_provider_uses_the_selected_delivery_channel(monkeypatch):
    calls = []

    class Response:
        status_code = 200

        def json(self):
            return {"user": {"id": "auth-user-1", "phone": "+919876543210"}}

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr("ffl.portal_auth.httpx.post", fake_post)
    provider = SupabasePhoneOtpProvider(
        base_url="https://project.supabase.co", publishable_key="sb_publishable_test", delivery_channel="whatsapp",
    )

    provider.request_code("+919876543210")
    verified = provider.verify_code("+919876543210", "123456")

    assert calls[0][0].endswith("/auth/v1/otp")
    assert calls[0][1]["json"] == {
        "phone": "+919876543210", "create_user": True, "options": {"channel": "whatsapp"},
    }
    assert calls[1][0].endswith("/auth/v1/verify")
    assert calls[1][1]["json"] == {"phone": "+919876543210", "token": "123456", "type": "whatsapp"}
    assert verified == VerifiedPhone(auth_subject="auth-user-1", phone_e164="+919876543210")
