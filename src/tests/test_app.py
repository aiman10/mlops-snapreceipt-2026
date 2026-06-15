from fastapi.testclient import TestClient
import app as app_module

client = TestClient(app_module.app)


def test_health_check():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"health_check": "OK"}


def test_extract_calls_model(monkeypatch):
    monkeypatch.setattr(app_module, "extract", lambda data: {"total": 8.8, "items": []})
    response = client.post("/extract", files={"file": ("r.png", b"fake-bytes", "image/png")})
    assert response.status_code == 200
    assert response.json()["total"] == 8.8
