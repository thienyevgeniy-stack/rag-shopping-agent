import json

from fastapi.testclient import TestClient

from server.main import app


client = TestClient(app)


def collect_token_text(stream_text: str) -> str:
    parts: list[str] = []
    for line in stream_text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = json.loads(line.removeprefix("data: "))
        if "text" in payload:
            parts.append(payload["text"])
    return "".join(parts)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat_stream_returns_tokens_and_product_card() -> None:
    response = client.post(
        "/chat",
        json={
            "session_id": "pytest-chat",
            "message": "推荐一款保湿眼霜，预算250以内",
        },
    )

    assert response.status_code == 200
    assert "event: token" in response.text
    assert "event: product_card" in response.text
    assert "科颜氏牛油果保湿眼霜" in response.text
    assert "event: done" in response.text


def test_chat_empty_result_degrades_without_product_card() -> None:
    response = client.post(
        "/chat",
        json={
            "session_id": "pytest-empty",
            "message": "推荐一款预算1元以内的无人机",
        },
    )

    assert response.status_code == 200
    assert "没有找到足够匹配的商品" in collect_token_text(response.text)
    assert "event: product_card" not in response.text
