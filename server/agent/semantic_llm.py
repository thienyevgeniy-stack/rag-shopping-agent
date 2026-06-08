import json

from pydantic import ValidationError

from server.agent.semantic_rules import build_rule_plan, dedupe_semantic_filters
from server.agent.semantic_schema import SemanticPlan
from server.session.state import SessionState


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
            client = self.llm_client
            chunks: list[str] = []
            async for token in client.stream_messages(build_semantic_plan_messages(message, session)):  # type: ignore[attr-defined]
                chunks.append(token)
            payload = extract_json_object("".join(chunks))
            if payload is None:
                return None
            return SemanticPlan.model_validate(payload)
        except (RuntimeError, ValueError, TypeError, ValidationError, json.JSONDecodeError):
            return None


def build_semantic_plan_messages(message: str, session: SessionState) -> list[dict]:
    candidates = build_candidate_context(session.candidate_product_cards)
    recent_turns = "\n".join(
        f"{turn.role}: {turn.content}"
        for turn in session.history[-6:]
    )
    schema_hint = {
        "intent": "recommend|compare|cart|ask_product_detail|clarify|browse|bundle",
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


def merge_semantic_plans(fallback: SemanticPlan, llm_plan: SemanticPlan) -> SemanticPlan:
    if llm_plan.confidence < 0.5:
        return fallback

    merged_filters = dedupe_semantic_filters([*fallback.filters, *llm_plan.filters])
    intent = llm_plan.intent or fallback.intent
    if fallback.intent in {"cart", "compare", "bundle"}:
        intent = fallback.intent
    if llm_plan.intent == "browse" and (
        fallback.intent == "recommend"
        or any(item.kind == "product_type" for item in fallback.filters)
    ):
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
