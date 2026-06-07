import json
import re
from collections.abc import AsyncIterator
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, ValidationError

from server.agent.context import extract_referenced_index, select_contextual_product
from server.agent.filters import extract_filters
from server.agent.intent import UserIntent, detect_intent
from server.rag.taxonomy import extract_product_type_matches
from server.session.state import FilterCondition, SessionState


SemanticIntent = Literal["recommend", "compare", "cart", "ask_product_detail", "clarify", "browse"]
CartAction = Literal["none", "add", "remove", "update_quantity", "view", "checkout"]
ReferenceType = Literal["none", "last", "ordinal", "name", "brand", "cheapest"]
FilterKind = Literal["keyword", "max_price", "exclude", "product_type"]


class ChatMessageClient(Protocol):
    async def stream_messages(self, messages: list[dict]) -> AsyncIterator[str]:
        ...


class SemanticFilter(BaseModel):
    kind: FilterKind
    value: str


class SemanticPlan(BaseModel):
    intent: SemanticIntent = "recommend"
    cart_action: CartAction = "none"
    reference_type: ReferenceType = "none"
    reference_index: int | None = None
    reference_text: str = ""
    quantity: int | None = None
    query: str = ""
    filters: list[SemanticFilter] = Field(default_factory=list)
    needs_search: bool = True
    confidence: float = 0.0

    def to_user_intent(self) -> UserIntent:
        if self.intent == "compare":
            return UserIntent.COMPARE
        if self.intent == "cart":
            return UserIntent.CART
        if self.intent == "browse":
            return UserIntent.BROWSING
        return UserIntent.BUYING

    def to_filter_conditions(self) -> list[FilterCondition]:
        return [FilterCondition(kind=item.kind, value=item.value) for item in self.filters if item.value.strip()]


class SemanticPlanner:
    def __init__(self, llm_client: object | None = None) -> None:
        self.llm_client = llm_client

    async def plan(self, message: str, session: SessionState) -> SemanticPlan:
        fallback = build_rule_plan(message, session)
        llm_plan = await self._try_llm_plan(message, session)
        if llm_plan is None:
            return fallback
        return merge_semantic_plans(fallback=fallback, llm_plan=llm_plan)

    async def _try_llm_plan(self, message: str, session: SessionState) -> SemanticPlan | None:
        if self.llm_client is None or not hasattr(self.llm_client, "stream_messages"):
            return None

        try:
            client = self.llm_client  # narrowed by hasattr at runtime
            chunks: list[str] = []
            async for token in client.stream_messages(build_semantic_plan_messages(message, session)):  # type: ignore[attr-defined]
                chunks.append(token)
            payload = extract_json_object("".join(chunks))
            if payload is None:
                return None
            return SemanticPlan.model_validate(payload)
        except (RuntimeError, ValueError, TypeError, ValidationError, json.JSONDecodeError):
            return None


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


def build_semantic_plan_messages(message: str, session: SessionState) -> list[dict]:
    candidates = build_candidate_context(session.candidate_product_cards)
    recent_turns = "\n".join(
        f"{turn.role}: {turn.content}"
        for turn in session.history[-6:]
    )
    schema_hint = {
        "intent": "recommend|compare|cart|ask_product_detail|clarify|browse",
        "cart_action": "none|add|remove|update_quantity|view|checkout",
        "reference_type": "none|last|ordinal|name|brand|cheapest",
        "reference_index": "1-based integer when user says first/second/etc, otherwise null",
        "reference_text": "brand/product hint such as AHC or 科颜氏",
        "quantity": "integer or null",
        "query": "search query in Chinese, include category and preferences",
        "filters": [{"kind": "keyword|max_price|exclude|product_type", "value": "string"}],
        "needs_search": "boolean",
        "confidence": "0-1",
    }
    return [
        {
            "role": "system",
            "content": (
                "你是电商导购 Agent 的语义解析器，只输出一个 JSON 对象。"
                "不要输出解释、Markdown 或多余文本。"
                "你只负责理解用户意图，不得编造商品事实、价格、库存或优惠。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"JSON schema 示例：\n{json.dumps(schema_hint, ensure_ascii=False)}\n\n"
                f"最近对话：\n{recent_turns or '无'}\n\n"
                f"上一轮候选商品：\n{candidates}\n\n"
                f"当前用户输入：\n{message}\n\n"
                "请输出 JSON。"
            ),
        },
    ]


def build_candidate_context(cards: list[dict]) -> str:
    if not cards:
        return "无"
    lines = []
    for index, card in enumerate(cards, 1):
        lines.append(
            f"{index}. id={card.get('id', '')}; name={card.get('name', '')}; "
            f"brand={card.get('brand', '')}; category={card.get('category', '')}; "
            f"price={card.get('price', '')}"
        )
    return "\n".join(lines)


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
    if user_intent == UserIntent.COMPARE:
        return "compare"
    if user_intent == UserIntent.CART:
        return "cart"
    if has_reference and not asks_for_new_search(message):
        return "ask_product_detail"
    if user_intent == UserIntent.BROWSING:
        return "browse"
    return "recommend"


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


def merge_semantic_plans(fallback: SemanticPlan, llm_plan: SemanticPlan) -> SemanticPlan:
    if llm_plan.confidence < 0.5:
        return fallback

    merged_filters = dedupe_semantic_filters([*fallback.filters, *llm_plan.filters])
    intent = llm_plan.intent or fallback.intent
    if fallback.intent in {"cart", "compare"}:
        intent = fallback.intent

    return llm_plan.model_copy(
        update={
            "intent": intent,
            "cart_action": llm_plan.cart_action if llm_plan.cart_action != "none" else fallback.cart_action,
            "reference_type": llm_plan.reference_type
            if llm_plan.reference_type != "none"
            else fallback.reference_type,
            "reference_index": llm_plan.reference_index or fallback.reference_index,
            "reference_text": llm_plan.reference_text or fallback.reference_text,
            "quantity": llm_plan.quantity or fallback.quantity,
            "query": llm_plan.query or fallback.query,
            "filters": merged_filters,
        }
    )


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


def extract_json_object(text: str) -> dict | None:
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start >= 0:
        try:
            payload, _ = decoder.raw_decode(text[start:])
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
            continue
        break
    return None
