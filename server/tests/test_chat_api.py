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


def test_product_image_asset_is_served() -> None:
    response = client.get("/assets/products/p_beauty_021_live.jpg")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content.startswith(b"\xff\xd8")


def test_product_detail_page_is_served() -> None:
    response = client.get("/products/p_beauty_021")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "科颜氏牛油果保湿眼霜" in response.text
    assert "/assets/products/p_beauty_021_live.jpg" in response.text


def test_product_detail_page_returns_404_for_missing_product() -> None:
    response = client.get("/products/missing-product")

    assert response.status_code == 404


def test_chat_stream_returns_tokens_and_product_card() -> None:
    response = client.post(
        "/chat",
        json={
            "session_id": "pytest-chat",
            "message": "推荐一款保湿眼霜，预算250以内",
        },
    )

    assert response.status_code == 200
    assert "event: status" in response.text
    assert "event: token" in response.text
    assert "event: product_card" in response.text
    assert "科颜氏牛油果保湿眼霜" in response.text
    assert "http://127.0.0.1:8000/assets/products/p_beauty_021_live.jpg" in response.text
    assert "http://127.0.0.1:8000/products/p_beauty_021" in response.text
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


def test_chat_compare_returns_comparison_card() -> None:
    response = client.post(
        "/chat",
        json={
            "session_id": "pytest-compare",
            "message": "科颜氏和AHC哪个眼霜更适合干皮",
        },
    )

    assert response.status_code == 200
    assert "event: comparison_card" in response.text
    assert "event: product_card" in response.text
    assert "我先基于当前商品库做对比" in collect_token_text(response.text)


def test_chat_cart_update_after_product_recommendation() -> None:
    session_id = "pytest-cart-api"
    first = client.post(
        "/chat",
        json={
            "session_id": session_id,
            "message": "推荐一款保湿眼霜，预算250以内",
        },
    )
    second = client.post(
        "/chat",
        json={
            "session_id": session_id,
            "message": "把刚才那款加到购物车",
        },
    )

    assert first.status_code == 200
    assert "event: product_card" in first.text
    assert second.status_code == 200
    assert "event: cart_update" in second.text
    assert "科颜氏牛油果保湿眼霜" in second.text
    assert '"total_quantity": 1' in second.text


def test_chat_sports_shoe_request_does_not_return_pants() -> None:
    response = client.post(
        "/chat",
        json={
            "session_id": "pytest-sports-shoes",
            "message": "推荐一款运动鞋",
        },
    )

    assert response.status_code == 200
    assert "event: product_card" in response.text
    assert "跑鞋" in response.text or "跑步鞋" in response.text
    assert "运动长裤" not in response.text
    assert "运动短裤" not in response.text


def test_debug_traces_capture_chat_turn() -> None:
    session_id = "pytest-debug-trace"
    response = client.post(
        "/chat",
        json={
            "session_id": session_id,
            "message": "科颜氏和AHC哪个眼霜更适合干皮",
        },
    )
    traces = client.get(f"/debug/traces?session_id={session_id}")

    assert response.status_code == 200
    assert traces.status_code == 200
    payload = traces.json()
    assert payload
    latest = payload[0]
    assert latest["session_id"] == session_id
    assert latest["handler"] == "CompareHandler"
    assert latest["plan"]["intent"] == "compare"
    assert "comparison_card" in latest["event_counts"]
    assert latest["comparison_product_ids"]


def test_debug_traces_capture_strategy_metadata_for_scenario_bundle() -> None:
    session_id = "pytest-strategy-trace"
    response = client.post(
        "/chat",
        json={
            "session_id": session_id,
            "message": "去海岛玩，预算1000以内，帮我配一套防晒和穿搭",
        },
    )
    traces = client.get(f"/debug/traces?session_id={session_id}")

    assert response.status_code == 200
    payload = traces.json()
    assert payload
    latest = payload[0]
    assert latest["handler"] == "ScenarioBundleHandler"
    assert latest["metadata"]["strategy"]["bundle_id"] == "sanya_trip"
    assert latest["metadata"]["strategy"]["catalog_version"] == "2026-06-08"
    assert latest["metadata"]["strategy"]["within_budget"] is True
    assert latest["metadata"]["strategy"]["signals"]


def test_debug_trace_detail_returns_404_for_missing_trace() -> None:
    response = client.get("/debug/traces/missing-trace-id")

    assert response.status_code == 404
