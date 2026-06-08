import base64
import json
from pathlib import Path

from fastapi.testclient import TestClient

from server.main import app


ROOT_DIR = Path(__file__).resolve().parents[2]
client = TestClient(app)


def token_text(stream_text: str) -> str:
    parts: list[str] = []
    for line in stream_text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = json.loads(line.removeprefix("data: "))
        if "text" in payload:
            parts.append(payload["text"])
    return "".join(parts)


def test_chat_accepts_image_and_returns_visual_match() -> None:
    image_bytes = (ROOT_DIR / "data" / "product_images" / "p_clothes_007_live.jpg").read_bytes()
    response = client.post(
        "/chat",
        json={
            "session_id": "pytest-image-search",
            "message": "我想找图片里的同款鞋",
            "image_base64": base64.b64encode(image_bytes).decode("ascii"),
            "image_mime_type": "image/jpeg",
            "image_filename": "p_clothes_007_live.jpg",
        },
    )

    assert response.status_code == 200
    assert "event: image_analysis" in response.text
    assert "p_clothes_007" in response.text
    assert "event: product_card" in response.text


def test_chat_builds_scenario_bundle_for_sanya_trip() -> None:
    response = client.post(
        "/chat",
        json={
            "session_id": "pytest-sanya-bundle",
            "message": "下周去三亚度假，帮我搭配一套从防晒到穿搭的方案",
        },
    )

    assert response.status_code == 200
    answer = token_text(response.text)
    assert "三亚度假组合方案" in answer
    assert "防晒保护" in answer
    assert "舒适出行" in answer
    assert response.text.count("event: product_card") >= 3
    assert "event: done" in response.text
