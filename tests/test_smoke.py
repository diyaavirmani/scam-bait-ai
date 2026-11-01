from fastapi.testclient import TestClient

from app.main import create_app


def test_health_route_exists():
    client = TestClient(create_app())
    assert client.get("/health").status_code in (200, 503)


async def test_startup_fails_loudly_without_required_settings(monkeypatch):
    import pytest

    from app.config import Settings
    from app.main import start_runtime
    for name in ("OPENAI_API_KEY", "CEREBRAS_API_KEY", "API_KEY", "DASHBOARD_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="Missing required settings: OPENAI_API_KEY"):
        await start_runtime(Settings())


def test_health_is_not_fake_when_runtime_missing():
    client = TestClient(create_app(run_startup=False))
    r = client.get("/health")
    assert r.status_code == 503 and r.json()["checks"]["database"] is False


def test_only_model_keys_are_required(monkeypatch):
    from app.config import Settings
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("CEREBRAS_API_KEY", "x")
    for name in ("API_KEY", "DASHBOARD_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    assert Settings().missing_required() == []
