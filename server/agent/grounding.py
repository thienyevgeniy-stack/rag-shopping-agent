import re
from dataclasses import dataclass, field


PROMOTION_TERMS = (
    "优惠",
    "优惠券",
    "券",
    "折扣",
    "满减",
    "促销",
    "活动价",
    "秒杀",
    "立减",
    "返现",
    "赠品",
    "包邮",
)

UNSUPPORTED_BUSINESS_TERMS = (
    "库存充足",
    "现货",
    "销量",
    "月销",
    "好评率",
    "官方认证",
    "正品保障",
)

ABSOLUTE_OR_MEDICAL_CLAIMS = (
    "保证",
    "100%",
    "百分百",
    "根治",
    "治愈",
    "无副作用",
    "永久",
    "全网第一",
    "行业第一",
)

DECLINE_RECOMMENDATION_TERMS = (
    "没有",
    "未找到",
    "暂未",
    "无法",
    "不能",
    "不支持",
    "无可用",
)

PRODUCT_NEED_TERMS = (
    "商品",
    "产品",
    "候选",
    "推荐",
    "匹配",
    "类",
)

PRICE_PATTERN = re.compile(r"(?:[¥￥]\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*元)")


@dataclass(frozen=True)
class GroundingResult:
    answer: str
    safe: bool
    violations: list[str] = field(default_factory=list)
    action: str = "pass"
    citations: list[dict] = field(default_factory=list)


def guard_grounded_answer(
    *,
    answer: str,
    cards: list[dict],
    fallback_answer: str,
    allowed_extra_prices: list[float] | None = None,
) -> GroundingResult:
    violations = detect_grounding_violations(
        answer=answer,
        cards=cards,
        allowed_extra_prices=allowed_extra_prices or [],
    )
    if not violations:
        return GroundingResult(answer=answer, safe=True, citations=build_answer_citations(answer, cards))
    return GroundingResult(
        answer=fallback_answer,
        safe=False,
        violations=violations,
        action="fallback",
        citations=build_answer_citations(fallback_answer, cards),
    )


def detect_grounding_violations(
    *,
    answer: str,
    cards: list[dict],
    allowed_extra_prices: list[float],
) -> list[str]:
    if not answer.strip():
        return ["empty_answer"]

    violations: list[str] = []
    matched_terms = terms_in_text(answer, PROMOTION_TERMS)
    if matched_terms:
        violations.append(f"unsupported_promotion_terms:{','.join(matched_terms)}")

    matched_terms = terms_in_text(answer, UNSUPPORTED_BUSINESS_TERMS)
    if matched_terms:
        violations.append(f"unsupported_business_terms:{','.join(matched_terms)}")

    matched_terms = terms_in_text(answer, ABSOLUTE_OR_MEDICAL_CLAIMS)
    if matched_terms:
        violations.append(f"unsupported_absolute_or_medical_claims:{','.join(matched_terms)}")

    unsupported_prices = prices_not_grounded(answer, cards, allowed_extra_prices)
    if unsupported_prices:
        violations.append(f"unsupported_prices:{','.join(unsupported_prices)}")

    if cards and not references_any_candidate(answer, cards) and not answer_declines_product_recommendation(answer):
        violations.append("missing_candidate_reference")

    return violations


def answer_declines_product_recommendation(answer: str) -> bool:
    normalized = normalize_guard_text(answer)
    if not normalized:
        return False
    has_decline = any(normalize_guard_text(term) in normalized for term in DECLINE_RECOMMENDATION_TERMS)
    has_product_need = any(normalize_guard_text(term) in normalized for term in PRODUCT_NEED_TERMS)
    return has_decline and has_product_need


def normalize_guard_text(value) -> str:
    return re.sub(r"\s+", "", str(value)).lower()


def terms_in_text(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def prices_not_grounded(answer: str, cards: list[dict], allowed_extra_prices: list[float]) -> list[str]:
    allowed = {normalize_price(candidate_fact(card, "price", 0)) for card in cards}
    allowed.update(normalize_price(value) for value in allowed_extra_prices)

    unsupported: list[str] = []
    for match in PRICE_PATTERN.finditer(answer):
        raw = match.group(1) or match.group(2) or ""
        if normalize_price(raw) not in allowed:
            unsupported.append(raw)
    return unsupported


def normalize_price(value) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return -1


def references_any_candidate(answer: str, cards: list[dict]) -> bool:
    normalized_answer = answer.lower()
    for card in cards:
        name = str(candidate_fact(card, "name", "")).strip()
        brand = str(candidate_fact(card, "brand", "")).strip()
        if name and name in answer:
            return True
        if brand and brand.lower() in normalized_answer:
            return True
    return False


def candidate_fact(card: dict, field: str, default=None):
    evidence = card.get("evidence")
    if isinstance(evidence, dict) and field in evidence:
        return evidence[field]
    if field == "product_id":
        return card.get("id", default)
    return card.get(field, default)


def build_answer_citations(answer: str, cards: list[dict]) -> list[dict]:
    citations: list[dict] = []
    for card in cards:
        product_id = candidate_fact(card, "product_id", "")
        name = str(candidate_fact(card, "name", "")).strip()
        brand = str(candidate_fact(card, "brand", "")).strip()
        price = candidate_fact(card, "price", None)
        cited_fields: list[str] = []

        if name and name in answer:
            cited_fields.append("name")
        if brand and brand.lower() in answer.lower():
            cited_fields.append("brand")
        if price is not None and normalize_price(price) in mentioned_prices(answer):
            cited_fields.append("price")

        if cited_fields:
            citations.append(
                {
                    "source": "product_catalog",
                    "product_id": product_id,
                    "fields": cited_fields,
                }
            )
    return citations


def mentioned_prices(answer: str) -> set[int]:
    prices: set[int] = set()
    for match in PRICE_PATTERN.finditer(answer):
        raw = match.group(1) or match.group(2) or ""
        prices.add(normalize_price(raw))
    return prices
