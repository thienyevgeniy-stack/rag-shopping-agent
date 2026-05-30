from server.rag.post_process import ExclusionFilter, KeywordFilter, RangeFilter, SearchFilters
from server.rag.vector_store import VectorStore


class ProductSearchTool:
    name = "search_products"

    def __init__(self, store: VectorStore) -> None:
        self.store = store
        self.post_processors = [RangeFilter(), KeywordFilter(), ExclusionFilter()]

    def run(self, query: str, filters: SearchFilters, top_k: int = 5) -> list[dict]:
        hits = self.store.query(query=query, top_k=max(top_k * 10, 50))
        for processor in self.post_processors:
            hits = processor.apply(hits, filters)
        return [to_product_card(hit, query) for hit in hits[:top_k]]


def to_product_card(hit: dict, query: str) -> dict:
    metadata = hit["metadata"]
    reason = build_reason(metadata, query)
    return {
        "id": metadata["id"],
        "name": metadata["name"],
        "category": metadata["category"],
        "brand": metadata["brand"],
        "price": metadata["price"],
        "image_url": metadata.get("image_url", ""),
        "detail_url": metadata.get("detail_url", ""),
        "reason": reason,
        "score": hit.get("score", 0),
    }


def build_reason(metadata: dict, query: str) -> str:
    tags = metadata.get("tags", [])
    matched = [tag for tag in tags if tag in query]
    if matched:
        return f"匹配 {', '.join(matched[:3])} 等需求"
    description = metadata.get("description", "")
    return description[:36] or "与当前检索条件相近"
