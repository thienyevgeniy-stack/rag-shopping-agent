from dataclasses import dataclass, field
from typing import Protocol

from server.session.state import SessionState


KEYWORD_SYNONYMS: dict[str, tuple[str, ...]] = {
    "拍照": ("拍照", "影像", "摄影", "相机", "人像", "长焦", "镜头"),
    "影像": ("影像", "拍照", "摄影", "相机", "人像", "长焦", "镜头"),
    "续航": ("续航", "电池", "长续航", "快充"),
    "性能": ("性能", "芯片", "处理器", "游戏", "流畅"),
    "性价比": ("性价比", "预算", "价格", "划算", "实惠"),
    "轻量": ("轻量", "轻便", "轻薄"),
    "保湿": ("保湿", "补水", "滋润"),
    "敏感肌": ("敏感肌", "敏感", "低刺激", "维稳", "修护"),
}


@dataclass(frozen=True)
class SearchFilters:
    max_price: float | None = None
    keywords: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)

    @classmethod
    def from_session(cls, session: SessionState) -> "SearchFilters":
        max_price: float | None = None
        keywords: list[str] = []
        exclusions: list[str] = []

        for item in session.filters:
            if item.kind == "max_price":
                max_price = float(item.value)
            elif item.kind == "keyword":
                keywords.append(item.value)

        for item in session.exclusions:
            exclusions.append(item.value)

        return cls(max_price=max_price, keywords=keywords, exclusions=exclusions)


class PostProcessor(Protocol):
    def apply(self, hits: list[dict], filters: SearchFilters) -> list[dict]:
        ...


class RangeFilter:
    def apply(self, hits: list[dict], filters: SearchFilters) -> list[dict]:
        if filters.max_price is None:
            return hits
        return [hit for hit in hits if float(hit["metadata"].get("price", 0)) <= filters.max_price]


class ExclusionFilter:
    def apply(self, hits: list[dict], filters: SearchFilters) -> list[dict]:
        if not filters.exclusions:
            return hits

        normalized = [item.lower() for item in filters.exclusions]
        kept: list[dict] = []
        for hit in hits:
            metadata = hit["metadata"]
            haystack = " ".join(
                [
                    str(metadata.get("name", "")),
                    str(metadata.get("brand", "")),
                    str(metadata.get("category", "")),
                    str(metadata.get("tags", "")),
                    str(metadata.get("attributes", "")),
                    hit.get("text", ""),
                ]
            ).lower()
            if not any(exclusion in haystack for exclusion in normalized):
                kept.append(hit)
        return kept


class KeywordFilter:
    def apply(self, hits: list[dict], filters: SearchFilters) -> list[dict]:
        if not filters.keywords:
            return hits

        required = [keyword.lower() for keyword in filters.keywords if keyword.strip()]
        if not required:
            return hits

        filtered: list[dict] = []
        for hit in hits:
            metadata = hit["metadata"]
            haystack = " ".join(
                [
                    str(metadata.get("name", "")),
                    str(metadata.get("category", "")),
                    str(metadata.get("sub_category", "")),
                    str(metadata.get("brand", "")),
                    str(metadata.get("tags", "")),
                    str(metadata.get("description", "")),
                ]
            ).lower()
            if all(keyword_matches(keyword, haystack) for keyword in required):
                filtered.append(hit)

        return filtered


def keyword_matches(keyword: str, haystack: str) -> bool:
    variants = KEYWORD_SYNONYMS.get(keyword, (keyword,))
    return any(variant in haystack for variant in variants)
