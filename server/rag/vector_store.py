import base64
import heapq
import json
import re
import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterable
from typing import Any, Protocol

import httpx

from server.rag.taxonomy import (
    canonicalize_product_type,
    enrich_product_type_metadata,
    infer_product_type_ids,
    product_type_display_names,
)


INDEX_SCHEMA_VERSION = "v2_metadata_filters"


@dataclass(frozen=True)
class VectorDocument:
    id: str
    text: str
    metadata: dict


@dataclass(frozen=True)
class DocumentFeatures:
    haystack: str
    title_text: str
    tokens: frozenset[str]


@dataclass(frozen=True)
class VectorSearchFilters:
    max_price: float | None = None
    product_types: tuple[str, ...] = ()


class VectorStore(Protocol):
    def add(self, documents: list[VectorDocument]) -> None:
        ...

    def query(self, query: str, top_k: int = 5, filters: VectorSearchFilters | None = None) -> list[dict]:
        ...

    def delete(self, ids: list[str]) -> None:
        ...


class LocalJsonVectorStore:
    def __init__(self, data_path: Path) -> None:
        self.data_path = data_path
        self.documents = load_product_documents(data_path)
        self.product_type_index = build_product_type_index(self.documents)
        self.document_features = build_document_feature_index(self.documents)

    @classmethod
    def from_documents(cls, documents: list[VectorDocument]) -> "LocalJsonVectorStore":
        store = cls.__new__(cls)
        store.data_path = None
        store.documents = list(documents)
        store.product_type_index = build_product_type_index(store.documents)
        store.document_features = build_document_feature_index(store.documents)
        return store

    def add(self, documents: list[VectorDocument]) -> None:
        self.documents.extend(documents)
        for document in documents:
            for product_type in infer_product_type_ids(document.metadata):
                self.product_type_index.setdefault(product_type, []).append(document)
            self.document_features[document.id] = build_document_features(document)

    def query(self, query: str, top_k: int = 5, filters: VectorSearchFilters | None = None) -> list[dict]:
        query_tokens = tokenize(query)
        hits: list[dict] = []
        for doc in self.candidate_documents(filters):
            if not metadata_matches_vector_filters(doc.metadata, filters):
                continue
            score = score_document_features(query_tokens, self.document_features[doc.id])
            if score > 0:
                hits.append({"id": doc.id, "text": doc.text, "metadata": doc.metadata, "score": score})

        return heapq.nlargest(top_k, hits, key=lambda item: item["score"])

    def delete(self, ids: list[str]) -> None:
        id_set = set(ids)
        self.documents = [doc for doc in self.documents if doc.id not in id_set]
        self.product_type_index = build_product_type_index(self.documents)
        self.document_features = build_document_feature_index(self.documents)

    def candidate_documents(self, filters: VectorSearchFilters | None) -> Iterable[VectorDocument]:
        if not filters or not filters.product_types:
            yield from self.documents
            return

        seen: set[str] = set()
        for product_type in filters.product_types:
            canonical = canonicalize_product_type(product_type)
            for document in self.product_type_index.get(canonical, []):
                if document.id in seen:
                    continue
                seen.add(document.id)
                yield document


class ChromaStore:
    def __init__(
        self,
        persist_path: Path,
        collection_name: str = "products",
        embedding_function: Any | None = None,
    ) -> None:
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
            embedding_function=embedding_function or HashingEmbeddingFunction(),
        )

    def add(self, documents: list[VectorDocument]) -> None:
        if not documents:
            return

        self.collection.upsert(
            ids=[document.id for document in documents],
            documents=[document.text for document in documents],
            metadatas=[to_chroma_metadata(document.metadata) for document in documents],
        )

    def query(self, query: str, top_k: int = 5, filters: VectorSearchFilters | None = None) -> list[dict]:
        if self.count() == 0:
            return []

        candidate_count = min(self.count(), max(top_k * 10, 50))
        where = build_chroma_where(filters)
        query_kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": candidate_count,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            query_kwargs["where"] = where

        result = self.collection.query(
            **query_kwargs,
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
    """Small local embedding hook for Chroma when external embeddings are disabled."""

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [hashing_embedding(text, self.dimensions) for text in input]

    @staticmethod
    def name() -> str:
        return "local_hashing_embedding"


class ArkEmbeddingFunction:
    """Chroma embedding hook backed by Ark's OpenAI-compatible embeddings API."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 60.0,
        batch_size: int = 64,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if batch_size <= 0 or batch_size > 256:
            raise ValueError("ARK embedding batch_size must be between 1 and 256.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.batch_size = batch_size
        self.transport = transport

    def __call__(self, input: list[str]) -> list[list[float]]:
        if not input:
            return []
        if not self.api_key:
            raise RuntimeError("ARK_API_KEY is not configured for embedding.")

        embeddings: list[list[float]] = []
        timeout = httpx.Timeout(self.timeout_seconds)
        with httpx.Client(timeout=timeout, transport=self.transport) as client:
            for start in range(0, len(input), self.batch_size):
                batch = input[start : start + self.batch_size]
                embeddings.extend(self._embed_batch(client, batch))
        return embeddings

    def _embed_batch(self, client: httpx.Client, batch: list[str]) -> list[list[float]]:
        url = f"{self.base_url}/embeddings"
        payload = {
            "model": self.model,
            "input": [text if text.strip() else "<empty>" for text in batch],
            "encoding_format": "float",
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        response = client.post(url, headers=headers, json=payload)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = response.text[:500].replace("\n", " ")
            raise RuntimeError(
                "ARK embedding request failed: "
                f"HTTP {response.status_code} for {url}; model={self.model}; body={body}"
            ) from exc
        return parse_embedding_response(response.json(), expected_count=len(batch))

    def name(self) -> str:
        return f"ark_embedding_{safe_identifier(self.model)}"


class ArkMultimodalEmbeddingFunction:
    """Ark multimodal embedding hook for Doubao vision/text-image embedding endpoints."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 60.0,
        batch_size: int = 1,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if batch_size <= 0 or batch_size > 32:
            raise ValueError("ARK multimodal embedding batch_size must be between 1 and 32.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.batch_size = batch_size
        self.transport = transport

    def __call__(self, input: list[str]) -> list[list[float]]:
        if not input:
            return []
        if not self.api_key:
            raise RuntimeError("ARK_API_KEY is not configured for embedding.")

        embeddings: list[list[float]] = []
        timeout = httpx.Timeout(self.timeout_seconds)
        with httpx.Client(timeout=timeout, transport=self.transport) as client:
            for text in input:
                embeddings.append(self._embed_text(client, text))
        return embeddings

    def embed_text(self, text: str) -> list[float]:
        if not self.api_key:
            raise RuntimeError("ARK_API_KEY is not configured for embedding.")
        timeout = httpx.Timeout(self.timeout_seconds)
        with httpx.Client(timeout=timeout, transport=self.transport) as client:
            return self._embed_text(client, text)

    def embed_image_bytes(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> list[float]:
        if not self.api_key:
            raise RuntimeError("ARK_API_KEY is not configured for embedding.")
        data_url = image_data_url(image_bytes, mime_type)
        timeout = httpx.Timeout(self.timeout_seconds)
        with httpx.Client(timeout=timeout, transport=self.transport) as client:
            return self._embed_input(
                client,
                [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_url,
                        },
                    }
                ],
            )

    def _embed_text(self, client: httpx.Client, text: str) -> list[float]:
        return self._embed_input(
            client,
            [
                {
                    "type": "text",
                    "text": text if text.strip() else "<empty>",
                }
            ],
        )

    def _embed_input(self, client: httpx.Client, input_items: list[dict[str, Any]]) -> list[float]:
        url = f"{self.base_url}/embeddings/multimodal"
        payload = {
            "model": self.model,
            "encoding_format": "float",
            "input": input_items,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        response = client.post(url, headers=headers, json=payload)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = response.text[:500].replace("\n", " ")
            raise RuntimeError(
                "ARK multimodal embedding request failed: "
                f"HTTP {response.status_code} for {url}; model={self.model}; body={body}"
            ) from exc
        return parse_multimodal_embedding_response(response.json())

    def name(self) -> str:
        return f"ark_multimodal_embedding_{safe_identifier(self.model)}"


def image_data_url(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    safe_mime = mime_type if mime_type.startswith("image/") else "image/jpeg"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{safe_mime};base64,{encoded}"


def parse_multimodal_embedding_response(payload: dict[str, Any]) -> list[float]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("ARK multimodal embedding response is missing a data object.")

    embedding = data.get("embedding")
    if not isinstance(embedding, list) or not embedding:
        raise RuntimeError("ARK multimodal embedding response contains an invalid embedding.")
    return [float(value) for value in embedding]


def parse_embedding_response(payload: dict[str, Any], expected_count: int) -> list[list[float]]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise RuntimeError("ARK embedding response is missing a data list.")

    by_index: dict[int, list[float]] = {}
    for fallback_index, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        index = int(item.get("index", fallback_index))
        embedding = item.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise RuntimeError("ARK embedding response contains an invalid embedding.")
        by_index[index] = [float(value) for value in embedding]

    missing = [index for index in range(expected_count) if index not in by_index]
    if missing:
        raise RuntimeError(f"ARK embedding response missing indexes: {missing}")

    return [by_index[index] for index in range(expected_count)]


def build_chroma_embedding_function(
    *,
    use_ark_embedding: bool,
    embedding_api: str = "text",
    api_key: str,
    base_url: str,
    model: str,
    timeout_seconds: float,
    batch_size: int,
    collection_name: str,
) -> tuple[Any, str]:
    collection_name = f"{collection_name}_{INDEX_SCHEMA_VERSION}"
    if use_ark_embedding and api_key:
        normalized_api = embedding_api.strip().lower()
        if normalized_api == "multimodal":
            embedder = ArkMultimodalEmbeddingFunction(
                api_key=api_key,
                base_url=base_url,
                model=model,
                timeout_seconds=timeout_seconds,
                batch_size=batch_size,
            )
        elif normalized_api == "text":
            embedder = ArkEmbeddingFunction(
                api_key=api_key,
                base_url=base_url,
                model=model,
                timeout_seconds=timeout_seconds,
                batch_size=batch_size,
            )
        else:
            raise ValueError("ARK embedding_api must be 'text' or 'multimodal'.")
        return embedder, bounded_chroma_collection_name(f"{collection_name}_{safe_identifier(embedder.name())}")
    return HashingEmbeddingFunction(), bounded_chroma_collection_name(collection_name)


def safe_identifier(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()


def bounded_chroma_collection_name(value: str, max_length: int = 63) -> str:
    safe_name = safe_identifier(value)
    if len(safe_name) <= max_length:
        return safe_name

    digest = hashlib.sha1(safe_name.encode("utf-8")).hexdigest()[:8]
    prefix_length = max_length - len(digest) - 1
    prefix = safe_name[:prefix_length].rstrip("_")
    return f"{prefix}_{digest}"


def product_type_filter_key(product_type: str) -> str:
    return f"pt_{safe_identifier(canonicalize_product_type(product_type))}"


def build_product_type_index(documents: list[VectorDocument]) -> dict[str, list[VectorDocument]]:
    index: dict[str, list[VectorDocument]] = {}
    for document in documents:
        for product_type in infer_product_type_ids(document.metadata):
            index.setdefault(product_type, []).append(document)
    return index


def build_document_feature_index(documents: list[VectorDocument]) -> dict[str, DocumentFeatures]:
    return {document.id: build_document_features(document) for document in documents}


def build_document_features(document: VectorDocument) -> DocumentFeatures:
    haystack = document.text.lower()
    title_text = " ".join(
        [
            str(document.metadata.get("name", "")),
            str(document.metadata.get("category", "")),
            str(document.metadata.get("sub_category", "")),
            str(document.metadata.get("brand", "")),
            " ".join(product_type_display_names(document.metadata.get("product_types", []))),
            " ".join(str(tag) for tag in document.metadata.get("tags", [])[:12]),
        ]
    ).lower()
    return DocumentFeatures(
        haystack=haystack,
        title_text=title_text,
        tokens=frozenset(tokenize(haystack)),
    )


def metadata_matches_vector_filters(metadata: dict[str, Any], filters: VectorSearchFilters | None) -> bool:
    if filters is None:
        return True

    if filters.max_price is not None and float(metadata.get("price", 0)) > filters.max_price:
        return False

    if filters.product_types:
        metadata_types = set(infer_product_type_ids(metadata))
        expected = {canonicalize_product_type(product_type) for product_type in filters.product_types}
        if not metadata_types & expected:
            return False

    return True


def build_chroma_where(filters: VectorSearchFilters | None) -> dict[str, Any] | None:
    if filters is None:
        return None

    clauses: list[dict[str, Any]] = []
    if filters.max_price is not None:
        clauses.append({"price": {"$lte": float(filters.max_price)}})

    if filters.product_types:
        product_type_clauses = [
            {product_type_filter_key(product_type): True}
            for product_type in filters.product_types
        ]
        if len(product_type_clauses) == 1:
            clauses.append(product_type_clauses[0])
        elif product_type_clauses:
            clauses.append({"$or": product_type_clauses})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


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
        product_types = infer_product_type_ids(item)
        product_type_names = product_type_display_names(product_types)
        text = (
            f"{item['name']} {item['category']} {item.get('sub_category', '')} "
            f"{item['brand']} {' '.join(product_type_names)} {tags} {attributes} {item.get('description', '')}"
        )
        metadata = {
            "id": item["id"],
            "name": item["name"],
            "category": item["category"],
            "sub_category": item.get("sub_category", ""),
            "brand": item["brand"],
            "product_types": product_types,
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
    payload = {
        "id": metadata["id"],
        "name": metadata["name"],
        "category": metadata.get("category", ""),
        "sub_category": metadata.get("sub_category", ""),
        "brand": metadata.get("brand", ""),
        "product_type_ids": ",".join(str(item) for item in metadata.get("product_types", [])),
        "price": float(metadata.get("price", 0)),
        "stock": int(metadata.get("stock", 0)),
        "image_url": metadata.get("image_url", ""),
        "detail_url": metadata.get("detail_url", ""),
        "metadata_json": json.dumps(metadata, ensure_ascii=False),
    }
    for product_type in metadata.get("product_types", []):
        payload[product_type_filter_key(str(product_type))] = True
    return payload


def from_chroma_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    raw = metadata.get("metadata_json")
    if raw:
        return enrich_product_type_metadata(json.loads(raw))
    return enrich_product_type_metadata(metadata)


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
    return score_document_features(query_tokens, build_document_features(doc))


def score_document_features(query_tokens: set[str], features: DocumentFeatures) -> float:
    overlap = len(query_tokens & features.tokens)
    phrase_bonus = sum(2 for token in query_tokens if len(token) > 1 and token in features.haystack)
    title_bonus = sum(6 for token in query_tokens if len(token) > 1 and token in features.title_text)
    return float(overlap + phrase_bonus + title_bonus)


def score_chroma_hit(query: str, metadata: dict[str, Any], text: str, distance: float) -> float:
    lexical_score = score_document(
        tokenize(query),
        VectorDocument(id=str(metadata.get("id", "")), text=text, metadata=metadata),
    )
    vector_score = 1.0 / (1.0 + distance)
    return lexical_score + vector_score
