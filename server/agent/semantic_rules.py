import re
from typing import Any

from server.agent.context import extract_referenced_index, select_contextual_product
from server.agent.filters import extract_filters
from server.agent.intent import UserIntent, detect_intent
from server.agent.semantic_schema import CartAction, SemanticFilter, SemanticIntent, SemanticPlan
from server.rag.taxonomy import extract_product_type_matches
from server.session.state import SessionState


def build_rule_plan(message: str, session: SessionState) -> SemanticPlan:
    filters = [SemanticFilter(kind=item.kind, value=item.value) for item in extract_filters(message)]
    filters.extend(build_semantic_filters(message, session))

    reference = infer_reference(message, session.candidate_product_cards)
    cart_action = infer_cart_action(message)
    quantity = extract_quantity(message)
    user_intent = detect_intent(message)
    intent = map_rule_intent(
        message=message,
        user_intent=user_intent,
        has_reference=reference["reference_type"] != "none",
        cart_action=cart_action,
    )
    needs_search = intent not in {"ask_product_detail", "cart", "clarify"}
    query = build_rule_query(message, filters)
    if session.pending_subject and session.pending_subject not in query:
        query = f"{session.pending_subject} {query}"

    return SemanticPlan(
        intent=intent,
        cart_action=cart_action,
        reference_type=reference["reference_type"],
        reference_index=reference["reference_index"],
        reference_text=reference["reference_text"],
        quantity=quantity,
        query=query,
        filters=dedupe_semantic_filters(filters),
        needs_search=needs_search,
        confidence=0.55,
    )


def build_semantic_filters(message: str, session: SessionState) -> list[SemanticFilter]:
    filters: list[SemanticFilter] = []
    for match in extract_product_type_matches(message):
        filters.append(SemanticFilter(kind="product_type", value=match.product_type_id))

    keyword_aliases = {
        "干皮": "保湿",
        "补水": "保湿",
        "滋润": "保湿",
        "温和": "敏感肌",
        "更温和": "敏感肌",
        "低刺激": "敏感肌",
        "维稳": "敏感肌",
        "熬夜": "修护",
        "淡纹": "修护",
    }
    for word, keyword in keyword_aliases.items():
        if word in message:
            filters.append(SemanticFilter(kind="keyword", value=keyword))

    referenced_card = select_contextual_product(message, session.candidate_product_cards)
    if referenced_card and any(word in message for word in ["别太贵", "不要太贵", "差不多价位", "同价位"]):
        filters.append(SemanticFilter(kind="max_price", value=str(int(float(referenced_card.get("price", 0))))))

    filters.extend(build_candidate_exclusions(message, session.candidate_product_cards))
    return filters


def build_candidate_exclusions(message: str, cards: list[dict]) -> list[SemanticFilter]:
    filters: list[SemanticFilter] = []
    if not any(word in message for word in ["先不要", "不要了", "排除", "换个"]):
        return filters

    for card in cards:
        for value in [str(card.get("brand", "")), str(card.get("name", ""))]:
            if value and value in message:
                filters.append(SemanticFilter(kind="exclude", value=value))
    return filters


def infer_reference(message: str, cards: list[dict]) -> dict[str, Any]:
    index = extract_referenced_index(message)
    if index is not None:
        return {"reference_type": "ordinal", "reference_index": index + 1, "reference_text": ""}

    if any(word in message for word in ["最便宜", "便宜的那个", "低价那个"]):
        return {"reference_type": "cheapest", "reference_index": None, "reference_text": ""}

    for card in cards:
        brand = str(card.get("brand", "")).strip()
        name = str(card.get("name", "")).strip()
        if brand and brand.lower() in message.lower():
            return {"reference_type": "brand", "reference_index": None, "reference_text": brand}
        if name and name in message:
            return {"reference_type": "name", "reference_index": None, "reference_text": name}

    if any(word in message for word in ["刚才", "上一个", "这个", "这款", "那款", "它", "那支", "那件"]):
        return {"reference_type": "last", "reference_index": None, "reference_text": ""}
    return {"reference_type": "none", "reference_index": None, "reference_text": ""}


def infer_cart_action(message: str) -> CartAction:
    if any(word in message for word in ["下单", "结算", "提交订单"]):
        return "checkout"
    if any(word in message for word in ["删除", "删掉", "移除", "不要这个"]):
        return "remove"
    if any(word in message for word in ["数量", "改成", "改为", "设为", "加一件", "减一件"]):
        return "update_quantity"
    if "购物车" in message and not any(word in message for word in ["加到", "加入", "加购", "放到", "放进"]):
        return "view"
    if is_add_to_cart_expression(message):
        return "add"
    return "none"


def is_add_to_cart_expression(message: str) -> bool:
    if any(word in message for word in ["加到", "加入", "加购", "放到", "放进", "购买"]):
        return True
    return bool(re.search(r"(来|要|买)\s*(\d+|一|二|两|三|四|五)?\s*(件|个|支|瓶|台|份)", message))


def map_rule_intent(
    message: str,
    user_intent: UserIntent,
    has_reference: bool,
    cart_action: CartAction,
) -> SemanticIntent:
    if cart_action != "none":
        return "cart"
    if asks_for_bundle(message):
        return "bundle"
    if user_intent == UserIntent.COMPARE:
        return "compare"
    if user_intent == UserIntent.CART:
        return "cart"
    if has_reference and not asks_for_new_search(message):
        return "ask_product_detail"
    if user_intent == UserIntent.BROWSING:
        return "browse"
    return "recommend"


def asks_for_bundle(message: str) -> bool:
    return any(
        word in message
        for word in [
            "三亚",
            "海边",
            "度假",
            "旅游",
            "旅行",
            "搭配一套",
            "组合推荐",
            "一套方案",
            "购买方案",
            "全套",
            "运动套装",
            "跑步装备",
        ]
    )


def asks_for_new_search(message: str) -> bool:
    return any(word in message for word in ["有没有", "换个", "换一款", "再推荐", "更适合", "再看看", "还有"])


def build_rule_query(message: str, filters: list[SemanticFilter]) -> str:
    keywords = [item.value for item in filters if item.kind == "keyword"]
    excludes = [item.value for item in filters if item.kind == "exclude"]
    pieces = [message, *keywords]
    if excludes:
        pieces.append("排除 " + " ".join(excludes))
    return " ".join(piece for piece in pieces if piece).strip()


def extract_quantity(message: str) -> int | None:
    patterns = [
        r"(?:数量|改成|改为|设为)\s*(\d+)",
        r"(\d+)\s*(件|个|份|台|瓶|支)",
        r"(?:来|要|买)\s*(\d+)\s*(件|个|份|台|瓶|支)",
    ]
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return int(match.group(1))

    for word, quantity in {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5}.items():
        if f"{word}件" in message or f"{word}个" in message or f"{word}支" in message:
            return quantity
    return None


def dedupe_semantic_filters(filters: list[SemanticFilter]) -> list[SemanticFilter]:
    seen: set[tuple[str, str]] = set()
    result: list[SemanticFilter] = []
    for item in filters:
        key = (item.kind, item.value.strip())
        if not key[1] or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
