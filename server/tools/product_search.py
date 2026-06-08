import re
from pathlib import PurePosixPath
from urllib.parse import quote, urlparse

from dataclasses import dataclass

from server.rag.post_process import SearchFilters
from server.rag.retrieval_pipeline import ProductRetrievalPipeline, RetrievalDiagnostics
from server.rag.taxonomy import enrich_product_type_metadata, product_type_display_names
from server.rag.vector_store import VectorStore


DESCRIPTION_FAQ_MARKERS = (" 问：", "\n问：", " Q:", "\nQ:")
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[。！？!?；;])\s*")
PRIORITY_EVIDENCE_TERMS = (
    "核心卖点",
    "主打",
    "搭载",
    "搭配",
    "适合",
    "适用",
    "场景",
    "日常",
    "建议",
)


@dataclass(frozen=True)
class ProductSearchResult:
    cards: list[dict]
    diagnostics: RetrievalDiagnostics


class ProductSearchTool:
    name = "search_products"

    def __init__(self, store: VectorStore, public_base_url: str = "") -> None:
        self.store = store
        self.public_base_url = public_base_url
        self.pipeline = ProductRetrievalPipeline(store)

    def run(self, query: str, filters: SearchFilters, top_k: int = 5) -> list[dict]:
        return self.run_with_diagnostics(query=query, filters=filters, top_k=top_k).cards

    def run_with_diagnostics(self, query: str, filters: SearchFilters, top_k: int = 5) -> ProductSearchResult:
        result = self.pipeline.run(query=query, filters=filters, top_k=top_k)
        cards = [to_product_card(hit, query, public_base_url=self.public_base_url) for hit in result.hits]
        return ProductSearchResult(cards=cards, diagnostics=result.diagnostics)


def to_product_card(hit: dict, query: str, public_base_url: str = "") -> dict:
    metadata = enrich_product_type_metadata(hit["metadata"])
    reason = build_reason(metadata, query)
    return {
        "id": metadata["id"],
        "name": metadata["name"],
        "category": metadata["category"],
        "product_types": metadata.get("product_types", []),
        "product_type_names": product_type_display_names(metadata.get("product_types", [])),
        "brand": metadata["brand"],
        "price": metadata["price"],
        "image_url": build_product_image_url(metadata.get("image_url", ""), public_base_url),
        "detail_url": build_product_detail_url(
            product_id=metadata["id"],
            raw_detail_url=metadata.get("detail_url", ""),
            public_base_url=public_base_url,
        ),
        "reason": reason,
        "score": hit.get("score", 0),
        "evidence": build_product_evidence(metadata, hit, query=query, reason=reason),
    }


def build_reason(metadata: dict, query: str) -> str:
    tags = metadata.get("tags", [])
    matched = matched_query_terms(tags, query)
    evidence = build_evidence_summary(metadata, query=query, matched_terms=matched)
    if matched and evidence:
        return f"匹配你提到的{format_terms(matched)}；{evidence}"
    if evidence:
        return evidence
    if matched:
        return f"匹配你提到的{format_terms(matched)}，可作为当前需求的候选商品。"
    return "与当前检索条件相近，可继续结合预算、尺码或使用场景确认。"


def build_product_evidence(metadata: dict, hit: dict, *, query: str, reason: str) -> dict:
    matched_terms = matched_query_terms(metadata.get("tags", []), query)
    return {
        "source": "product_catalog",
        "product_id": metadata["id"],
        "name": metadata["name"],
        "brand": metadata["brand"],
        "category": metadata["category"],
        "product_types": metadata.get("product_types", []),
        "price": float(metadata["price"]),
        "reason": reason,
        "highlights": build_evidence_highlights(metadata, matched_terms=matched_terms, query=query),
        "matched_terms": matched_terms,
        "score": float(hit.get("score", 0.0)),
        "retrieval_rank": hit.get("retrieval_rank"),
    }


def matched_query_terms(tags: list, query: str) -> list[str]:
    normalized_query = str(query).lower()
    matched: list[str] = []
    for tag in tags:
        value = str(tag).strip()
        if not value:
            continue
        if len(value) > 18 and ":" not in value:
            continue
        if value.lower() in normalized_query and value not in matched:
            matched.append(value)
    return matched[:4]


def format_terms(terms: list[str]) -> str:
    if not terms:
        return "核心条件"
    return "、".join(terms[:3])


def build_evidence_summary(metadata: dict, *, query: str, matched_terms: list[str]) -> str:
    highlights = build_evidence_highlights(metadata, matched_terms=matched_terms, query=query)
    return join_complete_sentences(highlights, max_sentences=2)


def build_evidence_highlights(metadata: dict, *, matched_terms: list[str], query: str = "") -> list[str]:
    description = clean_description(str(metadata.get("description", "")))
    if not description:
        return []

    sentences = split_sentences(description)
    if not sentences:
        return []

    scored: list[tuple[int, int, str]] = []
    query_terms = [term for term in matched_terms if len(term) >= 2]
    normalized_query = query.lower()
    for index, sentence in enumerate(sentences):
        score = 0
        for term in query_terms:
            if term in sentence:
                score += 12
        for term in PRIORITY_EVIDENCE_TERMS:
            if term in sentence:
                score += 6
        if normalized_query and any(chunk and chunk in sentence.lower() for chunk in normalized_query.split()):
            score += 4
        if index == 0:
            score += 3
        if "注意" in sentence and score < 10:
            score -= 3
        scored.append((score, -index, sentence))

    selected = [item[2] for item in sorted(scored, reverse=True)[:2]]
    selected.sort(key=lambda sentence: sentences.index(sentence))
    return selected


def clean_description(description: str) -> str:
    text = " ".join(description.split())
    for marker in DESCRIPTION_FAQ_MARKERS:
        index = text.find(marker)
        if index >= 0:
            text = text[:index]
    return text.strip()


def split_sentences(text: str) -> list[str]:
    sentences = [piece.strip() for piece in SENTENCE_SPLIT_PATTERN.split(text) if piece.strip()]
    return [sentence for sentence in sentences if sentence]


def join_complete_sentences(sentences: list[str], max_sentences: int = 2) -> str:
    selected = sentences[: max(max_sentences, 1)]
    return "".join(ensure_sentence_ending(sentence) for sentence in selected).strip()


def ensure_sentence_ending(sentence: str) -> str:
    stripped = sentence.strip()
    if not stripped:
        return ""
    if stripped[-1] in "。！？!?；;":
        return stripped
    return f"{stripped}。"


def build_product_image_url(raw_image_url: str, public_base_url: str = "") -> str:
    filename = PurePosixPath(str(raw_image_url).replace("\\", "/")).name
    if not filename:
        return ""

    path = f"/assets/products/{quote(filename)}"
    if not public_base_url:
        return path
    return f"{public_base_url.rstrip('/')}{path}"


def build_product_detail_url(product_id: str, raw_detail_url: str = "", public_base_url: str = "") -> str:
    raw_detail_url = str(raw_detail_url).strip()
    if raw_detail_url and urlparse(raw_detail_url).scheme in {"http", "https"}:
        return raw_detail_url

    path = f"/products/{quote(str(product_id))}"
    if not public_base_url:
        return path
    return f"{public_base_url.rstrip('/')}{path}"
