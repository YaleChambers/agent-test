from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
AUTH_HEADERS = {"Authorization": "Bearer test-key"}


def test_health_is_public():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_traces_without_token_returns_401():
    response = client.get("/v1/traces")

    assert response.status_code == 401


def test_traces_with_token_returns_list():
    response = client.get("/v1/traces", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_llm_without_token_returns_401():
    response = client.post(
        "/v1/llm",
        json={"model": "general-primary", "messages": []},
    )

    assert response.status_code == 401


def test_stream_without_token_returns_401():
    response = client.post(
        "/v1/llm/stream",
        json={"model": "general-primary", "messages": []},
    )

    assert response.status_code == 401


def test_llm_missing_model_returns_422():
    response = client.post(
        "/v1/llm",
        headers=AUTH_HEADERS,
        json={"messages": [{"role": "user", "content": "你好"}]},
    )

    assert response.status_code == 422


def test_unknown_model_returns_400():
    response = client.post(
        "/v1/llm",
        headers=AUTH_HEADERS,
        json={"model": "unknown-xyz", "messages": [{"role": "user", "content": "你好"}]},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unknown_model"
