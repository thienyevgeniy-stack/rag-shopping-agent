from dataclasses import dataclass, field
from typing import Protocol

from server.session.state import SessionState


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
            if all(keyword in haystack for keyword in required):
                filtered.append(hit)

        return filtered or hits


class ComparisonAggregator:
    def apply(self, hits: list[dict], filters: SearchFilters) -> list[dict]:
        return hits
