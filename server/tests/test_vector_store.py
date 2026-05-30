from pathlib import Path

import pytest

from server.rag.vector_store import (
    ChromaStore,
    HashingEmbeddingFunction,
    load_product_documents,
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
