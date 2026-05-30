import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


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
        self.documents = self._load_documents(data_path)

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

    def _load_documents(self, data_path: Path) -> list[VectorDocument]:
        with data_path.open("r", encoding="utf-8") as file:
            products = json.load(file)

        documents: list[VectorDocument] = []
        for item in products:
            tags = " ".join(item.get("tags", []))
            attributes = json.dumps(item.get("attributes", {}), ensure_ascii=False)
            text = (
                f"{item['name']} {item['category']} {item['brand']} {tags} "
                f"{attributes} {item.get('description', '')}"
            )
            metadata = {
                "id": item["id"],
                "name": item["name"],
                "category": item["category"],
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


class ChromaStore:
    def add(self, documents: list[VectorDocument]) -> None:
        raise NotImplementedError("Chroma adapter will be wired after embedding config is finalized.")

    def query(self, query: str, top_k: int = 5) -> list[dict]:
        raise NotImplementedError("Chroma adapter will be wired after embedding config is finalized.")

    def delete(self, ids: list[str]) -> None:
        raise NotImplementedError("Chroma adapter will be wired after embedding config is finalized.")


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
