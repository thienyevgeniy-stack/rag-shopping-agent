from pathlib import Path

import httpx
import pytest

from server.rag.vector_store import (
    ArkEmbeddingFunction,
    ChromaStore,
    HashingEmbeddingFunction,
    load_product_documents,
    parse_embedding_response,
)


ROOT_DIR = Path(__file__).resolve().parents[2]


def test_hashing_embedding_is_deterministic() -> None:
    embedder = HashingEmbeddingFunction(dimensions=32)

    first = embedder(["保湿眼霜"])[0]
    second = embedder(["保湿眼霜"])[0]

    assert first == second
    assert len(first) == 32


def test_chroma_store_round_trip(tmp_path: Path) -> None:
    pytest.importorskip("chromadb")
    documents = load_product_documents(ROOT_DIR / "data" / "products_ref.json")
    store = ChromaStore(tmp_path / "chroma")
    store.add(documents)

    hits = store.query("推荐一款保湿眼霜，预算250以内", top_k=5)

    assert store.count() == len(documents)
    assert hits
    assert any(hit["metadata"]["id"] == "p_beauty_021" for hit in hits)


def test_product_documents_include_normalized_product_types() -> None:
    documents = load_product_documents(ROOT_DIR / "data" / "products_ref.json")
    by_id = {document.id: document.metadata for document in documents}

    assert "clothes.sports_shoes" in by_id["p_clothes_007"]["product_types"]
    assert "clothes.sports_shoes" not in by_id["p_clothes_004"]["product_types"]
    assert "clothes.sports_pants" in by_id["p_clothes_004"]["product_types"]


def test_parse_embedding_response_orders_vectors_by_index() -> None:
    payload = {
        "data": [
            {"index": 1, "object": "embedding", "embedding": [2, 0.5]},
            {"index": 0, "object": "embedding", "embedding": [1, 0.25]},
        ]
    }

    assert parse_embedding_response(payload, expected_count=2) == [[1.0, 0.25], [2.0, 0.5]]


def test_ark_embedding_function_calls_openai_compatible_endpoint() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json_from_bytes(request.content)
        requests.append(payload)
        data = [
            {"index": index, "object": "embedding", "embedding": [float(len(text)), float(index)]}
            for index, text in enumerate(payload["input"])
        ]
        return httpx.Response(200, json={"object": "list", "data": data})

    embedder = ArkEmbeddingFunction(
        api_key="test-key",
        base_url="https://ark.example.test/api/v3",
        model="doubao-embedding-text-240515",
        batch_size=2,
        transport=httpx.MockTransport(handler),
    )

    vectors = embedder(["a", "bb", "ccc"])

    assert len(requests) == 2
    assert requests[0]["model"] == "doubao-embedding-text-240515"
    assert requests[0]["input"] == ["a", "bb"]
    assert requests[1]["input"] == ["ccc"]
    assert vectors == [[1.0, 0.0], [2.0, 1.0], [3.0, 0.0]]


def json_from_bytes(content: bytes) -> dict:
    import json

    return json.loads(content.decode("utf-8"))
