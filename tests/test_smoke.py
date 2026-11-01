from fastapi.testclient import TestClient

from app.main import create_app


def test_health_route_exists():
    client = TestClient(create_app())
    assert client.get("/health").status_code in (200, 503)
