import json
import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from server.rag.post_process import SearchFilters
from server.agent.semantic_schema import SemanticPlan


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIO_BUNDLE_PATH = ROOT_DIR / "data" / "scenario_bundles.json"


@dataclass(frozen=True)
class ScenarioSlot:
    label: str
    query: str
    filters: SearchFilters
    max_items: int = 1
    candidate_pool_size: int = 3
    budget_weight: float = 1.0
    optional: bool = False
    min_budget: float | None = None
    match_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioBundle:
    id: str
    title: str
    summary: str
    slots: tuple[ScenarioSlot, ...]
    matched_terms: tuple[str, ...] = ()
    source_version: str = ""
    match_confidence: float = 0.0
    match_signals: tuple[str, ...] = ()
    governance: dict[str, object] | None = None


@dataclass(frozen=True)
class ScenarioMatch:
    bundle: ScenarioBundle
    score: float
    confidence: float
    signals: tuple[str, ...]


class ScenarioFiltersConfig(BaseModel):
    max_price: float | None = None
    keywords: list[str] = Field(default_factory=list)
    product_types: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)

    def to_search_filters(self) -> SearchFilters:
        return SearchFilters(
            max_price=self.max_price,
            keywords=list(dict.fromkeys(item.strip() for item in self.keywords if item.strip())),
            product_types=list(dict.fromkeys(item.strip() for item in self.product_types if item.strip())),
            exclusions=list(dict.fromkeys(item.strip() for item in self.exclusions if item.strip())),
        )


class ScenarioSlotConfig(BaseModel):
    label: str
    query_template: str
    filters: ScenarioFiltersConfig = Field(default_factory=ScenarioFiltersConfig)
    max_items: int = Field(default=1, ge=1, le=5)
    candidate_pool_size: int = Field(default=3, ge=1, le=20)
    budget_weight: float = Field(default=1.0, ge=0.0)
    optional: bool = False
    min_budget: float | None = None
    match_terms: list[str] = Field(default_factory=list)


class ScenarioBundleConfig(BaseModel):
    status: Literal["active", "draft", "disabled"] = "active"
    rollout_percentage: float = Field(default=100.0, ge=0.0, le=100.0)
    owner: str = ""
    reviewed_at: str = ""
    id: str
    priority: int = 0
    trigger_terms: list[str] = Field(default_factory=list)
    semantic_terms: list[str] = Field(default_factory=list)
    min_score: float = 20.0
    title: str
    summary: str
    slots: list[ScenarioSlotConfig] = Field(min_length=1)

    def matched_terms(self, message: str) -> tuple[str, ...]:
        return tuple(term for term in self.trigger_terms if term and term in message)

    def to_runtime_bundle(
        self,
        message: str,
        matched_terms: tuple[str, ...],
        source_version: str,
        *,
        confidence: float = 0.0,
        signals: tuple[str, ...] = (),
        filters: SearchFilters | None = None,
    ) -> ScenarioBundle:
        total_budget = filters.max_price if filters is not None else None
        slots = tuple(
            ScenarioSlot(
                label=slot.label,
                query=render_query_template(slot.query_template, message),
                filters=merge_slot_filters(slot.filters.to_search_filters(), filters),
                max_items=slot.max_items,
                candidate_pool_size=slot.candidate_pool_size,
                budget_weight=slot.budget_weight,
                optional=slot.optional,
                min_budget=slot.min_budget,
                match_terms=tuple(slot.match_terms),
            )
            for slot in self.slots
            if should_keep_slot(slot, message=message, total_budget=total_budget)
        )
        return ScenarioBundle(
            id=self.id,
            title=self.title,
            summary=self.summary,
            slots=slots,
            matched_terms=matched_terms,
            source_version=source_version,
            match_confidence=confidence,
            match_signals=signals,
            governance={
                "status": self.status,
                "rollout_percentage": self.rollout_percentage,
                "owner": self.owner,
                "reviewed_at": self.reviewed_at,
            },
        )

    def enabled_for(self, session_id: str = "") -> bool:
        if self.status != "active":
            return False
        if self.rollout_percentage >= 100:
            return True
        if self.rollout_percentage <= 0:
            return False
        seed = f"{session_id}:{self.id}" if session_id else self.id
        return stable_bucket(seed) < self.rollout_percentage


class ScenarioCatalogConfig(BaseModel):
    version: str = ""
    bundles: list[ScenarioBundleConfig] = Field(default_factory=list)


class ScenarioCatalog:
    def __init__(
        self,
        bundles: tuple[ScenarioBundleConfig, ...],
        *,
        source_version: str = "",
        source_path: Path | None = None,
    ) -> None:
        self.bundles = tuple(sorted(bundles, key=lambda item: item.priority, reverse=True))
        self.source_version = source_version
        self.source_path = source_path

    @classmethod
    def from_file(cls, path: str | Path = DEFAULT_SCENARIO_BUNDLE_PATH) -> "ScenarioCatalog":
        catalog_path = Path(path)
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        config = ScenarioCatalogConfig.model_validate(payload)
        return cls(tuple(config.bundles), source_version=config.version, source_path=catalog_path)

    def route(
        self,
        message: str,
        *,
        plan: SemanticPlan | None = None,
        filters: SearchFilters | None = None,
        session_id: str = "",
    ) -> ScenarioMatch | None:
        message = message.strip()
        if not message:
            return None

        scored_matches: list[tuple[float, int, ScenarioBundleConfig, tuple[str, ...], tuple[str, ...]]] = []
        for bundle in self.bundles:
            if not bundle.enabled_for(session_id=session_id):
                continue
            score, matched_terms, signals = score_bundle(bundle, message, plan=plan, filters=filters)
            if score < bundle.min_score:
                continue
            longest_term = max((len(term) for term in matched_terms), default=0)
            scored_matches.append((score, longest_term, bundle, matched_terms, signals))

        if not scored_matches:
            if plan is not None and plan.intent == "bundle":
                return self.default_match(message, plan=plan, filters=filters, session_id=session_id)
            return None

        score, _, bundle, matched_terms, signals = max(scored_matches, key=lambda item: (item[0], item[1]))
        confidence = min(1.0, round(score / 100.0, 3))
        runtime_bundle = bundle.to_runtime_bundle(
            message=message,
            matched_terms=matched_terms,
            source_version=self.source_version,
            confidence=confidence,
            signals=signals,
            filters=filters,
        )
        return ScenarioMatch(bundle=runtime_bundle, score=score, confidence=confidence, signals=signals)

    def detect(
        self,
        message: str,
        *,
        plan: SemanticPlan | None = None,
        filters: SearchFilters | None = None,
        session_id: str = "",
    ) -> ScenarioBundle | None:
        match = self.route(message, plan=plan, filters=filters, session_id=session_id)
        return match.bundle if match is not None else None

    def default_match(
        self,
        message: str,
        *,
        plan: SemanticPlan | None,
        filters: SearchFilters | None,
        session_id: str,
    ) -> ScenarioMatch | None:
        for bundle in self.bundles:
            if bundle.id != "cross_category_bundle" or not bundle.enabled_for(session_id=session_id):
                continue
            signals = ("plan_intent:bundle", "fallback:cross_category_bundle")
            runtime_bundle = bundle.to_runtime_bundle(
                message=message,
                matched_terms=(),
                source_version=self.source_version,
                confidence=0.5,
                signals=signals,
                filters=filters,
            )
            return ScenarioMatch(bundle=runtime_bundle, score=50.0, confidence=0.5, signals=signals)
        return None


def score_bundle(
    bundle: ScenarioBundleConfig,
    message: str,
    *,
    plan: SemanticPlan | None,
    filters: SearchFilters | None,
) -> tuple[float, tuple[str, ...], tuple[str, ...]]:
    score = float(bundle.priority) * 0.15
    matched_terms: list[str] = []
    signals: list[str] = []

    trigger_terms = [term for term in bundle.trigger_terms if term and term in message]
    if trigger_terms:
        matched_terms.extend(trigger_terms)
        score += 55.0 + max(len(term) for term in trigger_terms) + min(len(trigger_terms), 3) * 8.0
        signals.append(f"trigger:{','.join(trigger_terms)}")

    semantic_terms = [term for term in bundle.semantic_terms if term and term in message]
    if semantic_terms:
        matched_terms.extend(semantic_terms)
        score += min(len(semantic_terms), 4) * 12.0
        signals.append(f"semantic:{','.join(semantic_terms[:4])}")

    plan_requests_bundle = plan is not None and plan.intent == "bundle"
    if not trigger_terms and not semantic_terms and not plan_requests_bundle:
        return 0.0, (), ()

    slot_terms = collect_slot_term_matches(bundle, message)
    if slot_terms:
        matched_terms.extend(slot_terms)
        score += min(len(slot_terms), 5) * 7.0
        signals.append(f"slot_terms:{','.join(slot_terms[:5])}")

    if filters is not None and filters.product_types:
        overlap = set(filters.product_types) & collect_bundle_product_types(bundle)
        if overlap:
            score += len(overlap) * 18.0
            signals.append(f"product_type:{','.join(sorted(overlap))}")

    if plan_requests_bundle:
        score += 20.0
        signals.append("plan_intent:bundle")

    return score, tuple(dict.fromkeys(matched_terms)), tuple(signals)


def collect_slot_term_matches(bundle: ScenarioBundleConfig, message: str) -> list[str]:
    matched: list[str] = []
    for slot in bundle.slots:
        terms = [slot.label, *slot.match_terms]
        for term in terms:
            if term and term in message:
                matched.append(term)
    return matched


def collect_bundle_product_types(bundle: ScenarioBundleConfig) -> set[str]:
    product_types: set[str] = set()
    for slot in bundle.slots:
        product_types.update(slot.filters.product_types)
    return product_types


def merge_slot_filters(slot_filters: SearchFilters, global_filters: SearchFilters | None) -> SearchFilters:
    if global_filters is None:
        return slot_filters
    max_price = slot_filters.max_price
    if max_price is None:
        max_price = global_filters.max_price
    elif global_filters.max_price is not None:
        max_price = min(max_price, global_filters.max_price)

    return SearchFilters(
        max_price=max_price,
        keywords=dedupe([*slot_filters.keywords]),
        product_types=dedupe(slot_filters.product_types),
        exclusions=dedupe([*slot_filters.exclusions, *global_filters.exclusions]),
    )


def should_keep_slot(slot: ScenarioSlotConfig, *, message: str, total_budget: float | None) -> bool:
    if total_budget is not None and slot.min_budget is not None and total_budget < slot.min_budget:
        return False
    if not slot.optional:
        return True
    if not slot.match_terms:
        return True
    return any(term in message for term in slot.match_terms)


def stable_bucket(seed: str) -> float:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") / 0xFFFFFFFF * 100.0


def dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in items if item.strip()))


def has_scenario_match(message: str) -> bool:
    return detect_scenario_bundle(message) is not None


@lru_cache
def load_scenario_catalog(path: str | None = None) -> ScenarioCatalog:
    return ScenarioCatalog.from_file(path or DEFAULT_SCENARIO_BUNDLE_PATH)


def get_default_scenario_catalog() -> ScenarioCatalog:
    return load_scenario_catalog(str(DEFAULT_SCENARIO_BUNDLE_PATH))


def detect_scenario_bundle(
    message: str,
    catalog: ScenarioCatalog | None = None,
    *,
    plan: SemanticPlan | None = None,
    filters: SearchFilters | None = None,
    session_id: str = "",
) -> ScenarioBundle | None:
    return (catalog or get_default_scenario_catalog()).detect(
        message,
        plan=plan,
        filters=filters,
        session_id=session_id,
    )


def render_query_template(template: str, message: str) -> str:
    return template.replace("{message}", message).strip()


def build_bundle_answer(bundle: ScenarioBundle, grouped_cards: list[tuple[ScenarioSlot, list[dict]]]) -> str:
    pieces = [f"我按“{bundle.title}”来搭配。{bundle.summary}"]
    for slot, cards in grouped_cards:
        if cards:
            card = cards[0]
            pieces.append(f"{slot.label}：{card['name']}，¥{int(float(card['price']))}，{card['reason']}")
        else:
            pieces.append(f"{slot.label}：当前商品库里暂时没有足够匹配的商品。")
    pieces.append("你可以继续说预算、品牌偏好或删掉某一类，我会按这套方案继续收敛。")
    return " ".join(pieces)
