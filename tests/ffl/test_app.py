from fastapi.testclient import TestClient

from ffl.app import create_app


def test_health_endpoint_reports_ffl_service():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"service": "ffl-operating-kernel", "status": "ok"}
