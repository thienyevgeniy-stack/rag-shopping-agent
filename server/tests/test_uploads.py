import json
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from server.main import app


ROOT_DIR = Path(__file__).resolve().parents[2]
client = TestClient(app)


def test_upload_image_returns_image_id() -> None:
    response = client.post(
        "/uploads/images",
        files={"file": ("test.jpg", make_jpeg(), "image/jpeg")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["image_id"]) == 32
    assert payload["mime_type"] == "image/jpeg"
    assert payload["size_bytes"] > 0


def test_upload_image_rejects_non_image() -> None:
    response = client.post(
        "/uploads/images",
        files={"file": ("test.txt", b"not an image", "text/plain")},
    )

    assert response.status_code == 400


def test_chat_accepts_uploaded_image_id() -> None:
    image_bytes = (ROOT_DIR / "data" / "product_images" / "p_clothes_007_live.jpg").read_bytes()
    upload = client.post(
        "/uploads/images",
        files={"file": ("shoe.jpg", image_bytes, "image/jpeg")},
    )
    image_id = upload.json()["image_id"]

    response = client.post(
        "/chat",
        json={
            "session_id": "pytest-image-id-search",
            "message": "find the same item in the image",
            "image_id": image_id,
        },
    )

    assert upload.status_code == 200
    assert response.status_code == 200
    assert "event: image_analysis" in response.text
    assert "p_clothes_007" in response.text
    assert "event: product_card" in response.text


def test_chat_accepts_uploaded_image_id_without_message() -> None:
    image_bytes = (ROOT_DIR / "data" / "product_images" / "p_clothes_007_live.jpg").read_bytes()
    upload = client.post(
        "/uploads/images",
        files={"file": ("shoe.jpg", image_bytes, "image/jpeg")},
    )
    image_id = upload.json()["image_id"]

    response = client.post(
        "/chat",
        json={
            "session_id": "pytest-image-only-id-search",
            "message": "",
            "image_id": image_id,
        },
    )

    assert upload.status_code == 200
    assert response.status_code == 200
    assert "event: image_analysis" in response.text
    assert "p_clothes_007" in response.text


def test_chat_rejects_empty_request_without_message_or_image() -> None:
    response = client.post(
        "/chat",
        json={
            "session_id": "pytest-empty-chat",
            "message": "",
        },
    )

    assert response.status_code == 422


def test_chat_with_missing_image_id_degrades_to_text_chat() -> None:
    response = client.post(
        "/chat",
        json={
            "session_id": "pytest-missing-image-id",
            "message": "recommend a running shoe",
            "image_id": "0" * 32,
        },
    )

    assert response.status_code == 200
    assert "event: token" in response.text


def make_jpeg() -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), (255, 0, 0)).save(output, format="JPEG")
    return output.getvalue()
