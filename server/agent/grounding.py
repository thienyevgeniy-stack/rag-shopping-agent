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

PRICE_PATTERN = re.compile(r"(?:[¥￥]\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*元)")


@dataclass(frozen=True)
class GroundingResult:
    answer: str
    safe: bool
    violations: list[str] = field(default_factory=list)
    action: str = "pass"


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
        return GroundingResult(answer=answer, safe=True)
    return GroundingResult(
        answer=fallback_answer,
        safe=False,
        violations=violations,
        action="fallback",
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

    if cards and not references_any_candidate(answer, cards):
        violations.append("missing_candidate_reference")

    return violations


def terms_in_text(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def prices_not_grounded(answer: str, cards: list[dict], allowed_extra_prices: list[float]) -> list[str]:
    allowed = {normalize_price(card.get("price", 0)) for card in cards}
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
        name = str(card.get("name", "")).strip()
        brand = str(card.get("brand", "")).strip()
        if name and name in answer:
            return True
        if brand and brand.lower() in normalized_answer:
            return True
    return False
