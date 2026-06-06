import re

from server.session.state import FilterCondition


def extract_contextual_filters(message: str, session, plan=None) -> list[FilterCondition]:
    if not session.candidate_product_cards:
        return []

    referenced_card = select_contextual_product(message, session.candidate_product_cards, plan)
    if referenced_card and any(word in message for word in ["别太贵", "不要太贵", "差不多价位", "同价位"]):
        price = int(float(referenced_card.get("price", 0)))
        if price > 1:
            return [FilterCondition(kind="max_price", value=str(price))]

    if is_cheaper_follow_up(message):
        prices = [
            float(card.get("price", 0))
            for card in session.candidate_product_cards
            if float(card.get("price", 0)) > 1
        ]
        if not prices:
            return []

        next_max_price = max(1, int(min(prices)) - 1)
        return [FilterCondition(kind="max_price", value=str(next_max_price))]

    return []


def is_cheaper_follow_up(message: str) -> bool:
    return any(word in message for word in ["再便宜", "更便宜", "便宜点", "便宜一点", "便宜些", "低价一点"])


def select_contextual_product(message: str, cards: list[dict], plan=None) -> dict | None:
    if not cards:
        return None

    plan_match = select_product_from_plan(cards, plan)
    if plan_match is not None:
        return plan_match

    index = extract_referenced_index(message)
    if index is not None:
        if 0 <= index < len(cards):
            return cards[index]
        return None

    text_match = select_product_by_text(message, cards)
    if text_match is not None:
        return text_match

    if any(word in message for word in ["刚才", "上一个", "这个", "这款", "那款", "它", "那支", "那件"]):
        return cards[0]
    return None


def select_product_from_plan(cards: list[dict], plan) -> dict | None:
    if plan is None:
        return None

    reference_type = getattr(plan, "reference_type", "none")
    reference_index = getattr(plan, "reference_index", None)
    reference_text = str(getattr(plan, "reference_text", "") or "")

    if reference_type == "ordinal" and reference_index is not None:
        index = int(reference_index) - 1
        if 0 <= index < len(cards):
            return cards[index]
        return None

    if reference_type == "cheapest":
        return min(cards, key=lambda card: float(card.get("price", 0)))

    if reference_type in {"name", "brand"} and reference_text:
        return select_product_by_text(reference_text, cards)

    if reference_type == "last":
        return cards[0]
    return None


def select_product_by_text(text: str, cards: list[dict]) -> dict | None:
    normalized = text.lower()
    for card in cards:
        brand = str(card.get("brand", "")).strip()
        name = str(card.get("name", "")).strip()
        product_id = str(card.get("id", "")).strip()
        if brand and brand.lower() in normalized:
            return card
        if name and name.lower() in normalized:
            return card
        if product_id and product_id.lower() in normalized:
            return card
    return None


def extract_referenced_index(message: str) -> int | None:
    match = re.search(r"第\s*(\d+)\s*(个|件|款)?", message)
    if match:
        return int(match.group(1)) - 1

    for word, index in {
        "一": 0,
        "二": 1,
        "两": 1,
        "三": 2,
        "四": 3,
        "五": 4,
    }.items():
        if f"第{word}" in message:
            return index
    return None


def build_contextual_product_answer(message: str, card: dict) -> str:
    focus_terms = [
        term
        for term in ["干皮", "敏感肌", "拍照", "续航", "性能", "性价比", "保湿", "温和", "熬夜", "修护"]
        if term in message
    ]
    focus_text = f"关于 {'、'.join(focus_terms)}，" if focus_terms else ""
    return (
        f"你说的是 {card['name']}。"
        f"{focus_text}当前商品库里能确认的信息是：品牌 {card['brand']}，"
        f"类目 {card['category']}，价格 {int(float(card['price']))} 元，"
        f"匹配依据是 {card.get('reason', '与当前需求相关')}。"
        "如果你想换一个方向，可以继续说“再便宜点”“看第二个”或“把它加到购物车”。"
    )
