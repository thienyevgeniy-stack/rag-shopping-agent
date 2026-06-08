import time
from dataclasses import dataclass, field

from server.rag.post_process import ExclusionFilter, KeywordFilter, ProductTypeFilter, RangeFilter, SearchFilters
from server.rag.taxonomy import product_type_matches
from server.rag.vector_store import VectorSearchFilters, VectorStore


@dataclass(frozen=True)
class RetrievalStep:
    name: str
    count: int
    elapsed_ms: float


@dataclass(frozen=True)
class RetrievalDiagnostics:
    query: str
    requested_top_k: int
    candidate_top_k: int
    steps: tuple[RetrievalStep, ...] = ()
    applied_filters: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalPipelineResult:
    hits: list[dict]
    diagnostics: RetrievalDiagnostics


class ProductRetrievalPipeline:
    """Production-shaped retrieval chain: prefilter, post-filter, rerank, truncate."""

    def __init__(
        self,
        store: VectorStore,
        *,
        candidate_multiplier: int = 10,
        min_candidate_pool: int = 50,
    ) -> None:
        self.store = store
        self.candidate_multiplier = max(candidate_multiplier, 1)
        self.min_candidate_pool = max(min_candidate_pool, 1)
        self.post_processors = [RangeFilter(), ProductTypeFilter(), KeywordFilter(), ExclusionFilter()]

    def run(self, query: str, filters: SearchFilters, top_k: int = 5) -> RetrievalPipelineResult:
        top_k = max(int(top_k), 0)
        if top_k == 0:
            return RetrievalPipelineResult(
                hits=[],
                diagnostics=RetrievalDiagnostics(
                    query=query,
                    requested_top_k=0,
                    candidate_top_k=0,
                    applied_filters=describe_filters(filters),
                ),
            )

        candidate_top_k = max(top_k * self.candidate_multiplier, self.min_candidate_pool)
        steps: list[RetrievalStep] = []

        started = time.perf_counter()
        hits = self.store.query(
            query=query,
            top_k=candidate_top_k,
            filters=VectorSearchFilters(
                max_price=filters.max_price,
                product_types=tuple(filters.product_types),
            ),
        )
        steps.append(RetrievalStep("store_prefilter_recall", len(hits), elapsed_ms(started)))

        for processor in self.post_processors:
            started = time.perf_counter()
            hits = processor.apply(hits, filters)
            steps.append(RetrievalStep(processor.__class__.__name__, len(hits), elapsed_ms(started)))

        started = time.perf_counter()
        hits = dedupe_hits(hits)
        hits = rerank_hits(hits, query=query, filters=filters)
        steps.append(RetrievalStep("dedupe_and_rerank", len(hits), elapsed_ms(started)))

        return RetrievalPipelineResult(
            hits=hits[:top_k],
            diagnostics=RetrievalDiagnostics(
                query=query,
                requested_top_k=top_k,
                candidate_top_k=candidate_top_k,
                steps=tuple(steps),
                applied_filters=describe_filters(filters),
            ),
        )


def dedupe_hits(hits: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique_hits: list[dict] = []
    for hit in hits:
        item_id = str(hit.get("id") or hit.get("metadata", {}).get("id", ""))
        if item_id in seen:
            continue
        seen.add(item_id)
        unique_hits.append(hit)
    return unique_hits


def rerank_hits(hits: list[dict], *, query: str, filters: SearchFilters) -> list[dict]:
    query = query.lower()
    scored_hits: list[tuple[float, int, dict]] = []
    for index, hit in enumerate(hits):
        metadata = hit.get("metadata", {})
        score = float(hit.get("score", 0.0))
        score += relevance_bonus(metadata, query=query, filters=filters)
        enriched_hit = dict(hit)
        enriched_hit["score"] = score
        enriched_hit["retrieval_rank"] = index + 1
        scored_hits.append((score, -index, enriched_hit))

    scored_hits.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [hit for _, _, hit in scored_hits]


def relevance_bonus(metadata: dict, *, query: str, filters: SearchFilters) -> float:
    bonus = 0.0
    haystack = build_metadata_haystack(metadata)
    if filters.product_types and any(product_type_matches(item, metadata) for item in filters.product_types):
        bonus += 20.0
    for keyword in filters.keywords:
        if keyword and keyword.lower() in haystack:
            bonus += 6.0
    if filters.max_price is not None:
        price = float(metadata.get("price", 0) or 0)
        if price <= filters.max_price:
            bonus += 2.0
            bonus += max(0.0, min(filters.max_price - price, 500.0) / 500.0)
    name = str(metadata.get("name", "")).lower()
    brand = str(metadata.get("brand", "")).lower()
    if name and name in query:
        bonus += 8.0
    if brand and brand in query:
        bonus += 4.0
    return bonus


def build_metadata_haystack(metadata: dict) -> str:
    parts = [
        str(metadata.get("name", "")),
        str(metadata.get("category", "")),
        str(metadata.get("sub_category", "")),
        str(metadata.get("brand", "")),
        " ".join(str(item) for item in metadata.get("tags", [])),
        str(metadata.get("description", "")),
    ]
    return " ".join(parts).lower()


def describe_filters(filters: SearchFilters) -> dict[str, object]:
    return {
        "max_price": filters.max_price,
        "keywords": list(filters.keywords),
        "product_types": list(filters.product_types),
        "exclusions": list(filters.exclusions),
    }


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)
