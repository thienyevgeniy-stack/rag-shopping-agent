import json
import asyncio

from pydantic import ValidationError

from server.agent.planning_policy import should_try_llm_planning, validate_semantic_plan
from server.agent.planning_context import (
    format_candidate_context,
    format_cart_context,
    format_recent_turns,
    load_planning_context,
)
from server.agent.semantic_rules import build_rule_plan, dedupe_semantic_constraints, dedupe_semantic_filters
from server.agent.semantic_schema import SemanticPlan
from server.session.state import SessionState


class SemanticPlanner:
    def __init__(self, llm_client: object | None = None, *, timeout_seconds: float = 0.8) -> None:
        self.llm_client = llm_client
        self.timeout_seconds = timeout_seconds

    async def plan(self, message: str, session: SessionState) -> SemanticPlan:
        fallback = build_rule_plan(message, session)
        if not should_try_llm_planning(message=message, fallback=fallback, session=session):
            return fallback
        llm_plan = await self._try_llm_plan(message, session)
        if llm_plan is None:
            return fallback
        merged = merge_semantic_plans(fallback=fallback, llm_plan=llm_plan)
        return validate_semantic_plan(
            message=message,
            session=session,
            fallback=fallback,
            candidate=merged,
        )

    async def _try_llm_plan(self, message: str, session: SessionState) -> SemanticPlan | None:
        if self.llm_client is None or not hasattr(self.llm_client, "stream_messages"):
            return None
        if self.timeout_seconds <= 0:
            return None

        try:
            chunks = await self._collect_llm_plan_tokens(message, session)
            payload = extract_json_object("".join(chunks))
            if payload is None:
                return None
            return SemanticPlan.model_validate(payload)
        except (RuntimeError, ValueError, TypeError, TimeoutError, ValidationError, json.JSONDecodeError):
            return None

    async def _collect_llm_plan_tokens(self, message: str, session: SessionState) -> list[str]:
        client = self.llm_client
        chunks: list[str] = []
        async with asyncio.timeout(self.timeout_seconds):
            async for token in client.stream_messages(build_semantic_plan_messages(message, session)):  # type: ignore[attr-defined]
                chunks.append(token)
        return chunks


def build_semantic_plan_messages(message: str, session: SessionState) -> list[dict]:
    context = load_planning_context(session)
    schema_hint = {
        "intent": "recommend|compare|cart|ask_product_detail|clarify|browse|bundle",
        "cart_action": "none|add|remove|update_quantity|view|checkout",
        "reference_type": "none|last|ordinal|name|brand|cheapest",
        "reference_index": "1-based integer when user says first/second/etc, otherwise null",
        "reference_text": "brand/product hint such as AHC or 科颜氏",
        "quantity": "integer or null",
        "query": "search query in Chinese, include category and preferences",
        "presentation_mode": "auto|single|listing",
        "filled_slots": {
            "product_type": "canonical product type object or null",
            "budget": "price range object or null",
            "brand": "brand object or null",
            "use_case": "usage preference object or null",
        },
        "filters": [
            {
                "kind": (
                    "keyword|should_keyword|max_price|min_price|brand|preferred_brand|"
                    "exclude_brand|exclude|category|exclude_category|product_type|exclude_product_type|"
                    "in_stock|facet|unsupported_service"
                ),
                "value": "string",
            }
        ],
        "constraints": [
            {
                "mode": "must|must_not|should",
                "field": "product_type|category|keyword|brand|price|attribute|stock|facet|service",
                "operator": "eq|contains|lte|gte",
                "value": "string",
                "source": "llm",
            }
        ],
        "needs_search": "boolean",
        "confidence": "0-1",
        "confidence_by_field": {"intent": "0-1", "product_type": "0-1", "quantity": "0-1"},
        "evidence": {"intent": "short source text", "product_type": "matched span", "quantity": "matched span"},
    }
    return [
        {
            "role": "system",
            "content": (
                "你是电商导购 Agent 的语义解析器，只输出一个 JSON 对象。"
                "不要输出解释、Markdown 或多余文本。"
                "你只负责理解用户意图，不得编造商品事实、价格、库存或优惠。"
                "库存只能解析为 in_stock/static stock 约束；"
                "发票、优惠券、实时发货、售后政策如果没有上下文证据，输出 unsupported_service，不能当作已支持事实。"
                "严格区分单品推荐和组合方案："
                "用户说“推荐一款/一瓶/一双/一个/一件”通常是 recommend，"
                "只有明确说“配一套/一整套/清单/方案/从...到...”或多类目方案时才输出 bundle；"
                "“组合/套装”可能只是商品范围，例如“文具组合/护肤套装”，不能仅凭这类词输出 bundle。"
                "购物车动作必须有明确的用户动作词和可解析商品引用；"
                "如果信息不足以执行购物车动作、上下文引用或组合方案，输出 clarify。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"JSON schema 示例：\n{json.dumps(schema_hint, ensure_ascii=False)}\n\n"
                f"最近对话：\n{format_recent_turns(context)}\n\n"
                f"会话摘要：\n{context.history_summary or '无'}\n\n"
                f"用户偏好 profile：\n{json.dumps(context.user_profile, ensure_ascii=False)}\n\n"
                f"上一轮候选商品：\n{format_candidate_context(context)}\n\n"
                f"当前购物车：\n{format_cart_context(context)}\n\n"
                f"待确认购物车动作：\n{json.dumps(context.pending_cart_action, ensure_ascii=False)}\n\n"
                f"当前用户输入：\n{message}\n\n"
                "判定示例：\n"
                "- “推荐一款防晒霜” => intent=recommend, presentation_mode=single, product_type=beauty.sunscreen\n"
                "- “推荐一款护肤品” => intent=recommend, presentation_mode=single, category=beauty.skincare\n"
                "- “我想看所有洁面泡沫” => intent=browse, presentation_mode=listing, product_type=beauty.cleanser\n"
                "- “去三亚玩，帮我配一套从防晒到穿搭的方案” => intent=bundle\n"
                "- “推荐一款文具组合” => intent=recommend；如果商品库没有该类目，不要改成跨类目 bundle\n"
                "- “我想买两双安踏”且上一轮有多款安踏 => intent=clarify 或 cart，不能随意选商品\n\n"
                "facet 示例：16GB 内存 => facet memory:16GB；42码 => facet shoe_size:42；"
                "只看有货 => in_stock=true；支持企业开票 => unsupported_service=invoice_policy。\n\n"
                "请输出 JSON。"
            ),
        },
    ]


def merge_semantic_plans(fallback: SemanticPlan, llm_plan: SemanticPlan) -> SemanticPlan:
    if llm_plan.confidence < 0.5:
        return fallback

    merged_filters = dedupe_semantic_filters([*fallback.filters, *llm_plan.filters])
    merged_constraints = dedupe_semantic_constraints([*fallback.constraints, *llm_plan.constraints])
    intent = llm_plan.intent or fallback.intent
    if fallback.intent in {"cart", "compare", "bundle"}:
        intent = fallback.intent
    if llm_plan.intent == "browse" and (
        fallback.intent == "recommend"
        or any(item.kind == "product_type" for item in fallback.filters)
    ):
        intent = fallback.intent
    presentation_mode = (
        llm_plan.presentation_mode
        if llm_plan.presentation_mode != "auto"
        else fallback.presentation_mode
    )

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
            "presentation_mode": presentation_mode,
            "query_understanding": fallback.query_understanding or llm_plan.query_understanding,
            "filled_slots": merge_filled_slots(fallback, llm_plan),
            "filters": merged_filters,
            "constraints": merged_constraints,
            "confidence_by_field": merge_confidence_by_field(fallback, llm_plan),
            "evidence": merge_plan_evidence(fallback, llm_plan),
        }
    )


def merge_confidence_by_field(fallback: SemanticPlan, llm_plan: SemanticPlan) -> dict[str, float]:
    merged = dict(fallback.confidence_by_field)
    for field, value in llm_plan.confidence_by_field.items():
        current = merged.get(field, 0.0)
        merged[field] = max(float(current), float(value))
    if llm_plan.confidence:
        merged["llm_plan"] = round(float(llm_plan.confidence), 4)
    return merged


def merge_filled_slots(fallback: SemanticPlan, llm_plan: SemanticPlan) -> dict:
    merged = dict(fallback.filled_slots)
    for field, value in llm_plan.filled_slots.items():
        if value not in (None, "", [], {}, ()):
            merged[field] = value
    return merged


def merge_plan_evidence(fallback: SemanticPlan, llm_plan: SemanticPlan) -> dict:
    merged = dict(fallback.evidence)
    if llm_plan.evidence:
        merged["llm"] = llm_plan.evidence
    if llm_plan.confidence:
        merged["llm_plan"] = {"confidence": round(float(llm_plan.confidence), 4)}
    return merged


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
