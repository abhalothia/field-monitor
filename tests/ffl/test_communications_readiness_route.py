import json

from fastapi.testclient import TestClient

from ffl.app import create_app
from ffl.communications.loopmessage import LoopMessageProvider
from ffl.seed import seed_pilot


def _complete_provider():
    return LoopMessageProvider(
        "organization-api-secret", "dashboard-webhook-secret", "+15550000001",
        whatsapp_channel_enabled=True,
        whatsapp_capability_proof="sandbox-verified",
        whatsapp_capability_proof_ref="reviewed-sandbox-proof-123",
    )


def test_readiness_route_is_manager_only_and_never_leaks_runtime_values(tmp_path):
    app = create_app(
        str(tmp_path / "readiness-route.db"), communication_provider=_complete_provider(),
        manager_api_token="manager-secret", communication_receipt_key="private-receipt-secret",
        private_communications_worker_attested=True,
    )
    with TestClient(app) as client:
        seed = seed_pilot(app.state.conn)
        app.state.manager_person_id = seed["manager_id"]

        assert client.get("/api/v1/communications/readiness").status_code == 403
        ready = client.get(
            "/api/v1/communications/readiness", headers={"X-FFL-Manager-Token": "manager-secret"}
        )
        assert ready.status_code == 200
        report = ready.json()
        assert report["status"] == "ready"
        assert report["live_inbound_eligible"] is True
        assert report["live_outbound_eligible"] is True
        rendered = json.dumps(report)
        for protected in (
            "organization-api-secret", "dashboard-webhook-secret", "+15550000001",
            "private-receipt-secret", "reviewed-sandbox-proof-123",
        ):
            assert protected not in rendered


def test_default_readiness_route_fails_closed(tmp_path):
    app = create_app(str(tmp_path / "readiness-route-default.db"), manager_api_token="manager-secret")
    with TestClient(app) as client:
        seed = seed_pilot(app.state.conn)
        app.state.manager_person_id = seed["manager_id"]

        report = client.get(
            "/api/v1/communications/readiness", headers={"X-FFL-Manager-Token": "manager-secret"}
        ).json()
        assert report["status"] == "blocked"
        assert report["live_inbound_eligible"] is False
        assert report["live_outbound_eligible"] is False
        assert "private_worker_not_attested" in report["gaps"]
