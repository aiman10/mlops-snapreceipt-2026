from fastapi.testclient import TestClient
import app as app_module

client = TestClient(app_module.app)


def test_root_health_check():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"health_check": "OK"}


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_extract_calls_model(monkeypatch):
    monkeypatch.setattr(
        app_module, "extract", lambda data: {"total_amount": 8.8, "items": []}
    )
    response = client.post(
        "/extract", files={"file": ("r.png", b"fake-bytes", "image/png")}
    )
    assert response.status_code == 200
    assert response.json()["total_amount"] == 8.8


def test_extract_rejects_non_image():
    response = client.post(
        "/extract", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    assert response.status_code == 400
