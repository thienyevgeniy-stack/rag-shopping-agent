import json
import re
import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class VectorDocument:
    id: str
    text: str
    metadata: dict


class VectorStore(Protocol):
    def add(self, documents: list[VectorDocument]) -> None:
        ...

    def query(self, query: str, top_k: int = 5) -> list[dict]:
        ...

    def delete(self, ids: list[str]) -> None:
        ...


class LocalJsonVectorStore:
    def __init__(self, data_path: Path) -> None:
        self.data_path = data_path
        self.documents = load_product_documents(data_path)

    def add(self, documents: list[VectorDocument]) -> None:
        self.documents.extend(documents)

    def query(self, query: str, top_k: int = 5) -> list[dict]:
        query_tokens = tokenize(query)
        hits: list[dict] = []
        for doc in self.documents:
            score = score_document(query_tokens, doc)
            if score > 0:
                hits.append({"id": doc.id, "text": doc.text, "metadata": doc.metadata, "score": score})

        hits.sort(key=lambda item: item["score"], reverse=True)
        return hits[:top_k]

    def delete(self, ids: list[str]) -> None:
        id_set = set(ids)
        self.documents = [doc for doc in self.documents if doc.id not in id_set]


class ChromaStore:
    def __init__(self, persist_path: Path, collection_name: str = "products") -> None:
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError as exc:
            raise RuntimeError(
                "chromadb is not installed. Run `pip install -r server/requirements.txt`."
            ) from exc

        self.persist_path = persist_path
        self.persist_path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(self.persist_path),
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=HashingEmbeddingFunction(),
        )

    def add(self, documents: list[VectorDocument]) -> None:
        if not documents:
            return

        self.collection.upsert(
            ids=[document.id for document in documents],
            documents=[document.text for document in documents],
            metadatas=[to_chroma_metadata(document.metadata) for document in documents],
        )

    def query(self, query: str, top_k: int = 5) -> list[dict]:
        if self.count() == 0:
            return []

        candidate_count = min(self.count(), max(top_k * 10, 50))
        result = self.collection.query(
            query_texts=[query],
            n_results=candidate_count,
            include=["documents", "metadatas", "distances"],
        )
        ids = result.get("ids", [[]])[0]
        texts = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        hits: list[dict] = []
        for index, item_id in enumerate(ids):
            metadata = from_chroma_metadata(metadatas[index])
            distance = float(distances[index]) if index < len(distances) else 0.0
            hits.append(
                {
                    "id": item_id,
                    "text": texts[index] if index < len(texts) else "",
                    "metadata": metadata,
                    "score": score_chroma_hit(query, metadata, texts[index], distance),
                }
            )
        hits.sort(key=lambda item: item["score"], reverse=True)
        return hits[:top_k]

    def delete(self, ids: list[str]) -> None:
        if ids:
            self.collection.delete(ids=ids)

    def count(self) -> int:
        return int(self.collection.count())


class HashingEmbeddingFunction:
    """Small local embedding hook for Chroma; swap this for Doubao embeddings later."""

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [hashing_embedding(text, self.dimensions) for text in input]

    @staticmethod
    def name() -> str:
        return "local_hashing_embedding"


def tokenize(text: str) -> set[str]:
    lowered = text.lower()
    chunks = re.findall(r"[\u4e00-\u9fff]+|[a-z0-9]+", lowered)
    tokens: set[str] = set()
    for chunk in chunks:
        tokens.add(chunk)
        if re.fullmatch(r"[\u4e00-\u9fff]+", chunk):
            tokens.update(chunk[index : index + 2] for index in range(max(len(chunk) - 1, 0)))
            tokens.update(chunk[index : index + 3] for index in range(max(len(chunk) - 2, 0)))
    return tokens


def load_product_documents(data_path: Path) -> list[VectorDocument]:
    with data_path.open("r", encoding="utf-8") as file:
        products = json.load(file)

    documents: list[VectorDocument] = []
    for item in products:
        tags = " ".join(str(tag) for tag in item.get("tags", []))
        attributes = json.dumps(item.get("attributes", {}), ensure_ascii=False)
        text = (
            f"{item['name']} {item['category']} {item.get('sub_category', '')} "
            f"{item['brand']} {tags} {attributes} {item.get('description', '')}"
        )
        metadata = {
            "id": item["id"],
            "name": item["name"],
            "category": item["category"],
            "sub_category": item.get("sub_category", ""),
            "brand": item["brand"],
            "price": item["price"],
            "stock": item.get("stock", 0),
            "image_url": item.get("image_url", ""),
            "detail_url": item.get("detail_url", ""),
            "tags": item.get("tags", []),
            "attributes": item.get("attributes", {}),
            "description": item.get("description", ""),
        }
        documents.append(VectorDocument(id=item["id"], text=text, metadata=metadata))
    return documents


def to_chroma_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": metadata["id"],
        "name": metadata["name"],
        "category": metadata.get("category", ""),
        "sub_category": metadata.get("sub_category", ""),
        "brand": metadata.get("brand", ""),
        "price": float(metadata.get("price", 0)),
        "stock": int(metadata.get("stock", 0)),
        "image_url": metadata.get("image_url", ""),
        "detail_url": metadata.get("detail_url", ""),
        "metadata_json": json.dumps(metadata, ensure_ascii=False),
    }


def from_chroma_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    raw = metadata.get("metadata_json")
    if raw:
        return json.loads(raw)
    return metadata


def hashing_embedding(text: str, dimensions: int = 384) -> list[float]:
    vector = [0.0] * dimensions
    tokens = tokenize(text)
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "little") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        weight = 1.0 + min(len(token), 8) / 8.0
        vector[bucket] += sign * weight

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def score_document(query_tokens: set[str], doc: VectorDocument) -> float:
    haystack = doc.text.lower()
    title_text = " ".join(
        [
            str(doc.metadata.get("name", "")),
            str(doc.metadata.get("category", "")),
            str(doc.metadata.get("sub_category", "")),
            str(doc.metadata.get("brand", "")),
            " ".join(str(tag) for tag in doc.metadata.get("tags", [])[:12]),
        ]
    ).lower()
    doc_tokens = tokenize(haystack)
    overlap = len(query_tokens & doc_tokens)
    phrase_bonus = sum(2 for token in query_tokens if len(token) > 1 and token in haystack)
    title_bonus = sum(6 for token in query_tokens if len(token) > 1 and token in title_text)
    return float(overlap + phrase_bonus + title_bonus)


def score_chroma_hit(query: str, metadata: dict[str, Any], text: str, distance: float) -> float:
    lexical_score = score_document(
        tokenize(query),
        VectorDocument(id=str(metadata.get("id", "")), text=text, metadata=metadata),
    )
    vector_score = 1.0 / (1.0 + distance)
    return lexical_score + vector_score
