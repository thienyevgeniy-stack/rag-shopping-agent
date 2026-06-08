import asyncio
from collections.abc import AsyncIterator

from server.agent.semantic import SemanticPlanner, build_rule_plan, extract_json_object
from server.session.state import SessionState


PRODUCT_CARD = {
    "id": "p_beauty_021",
    "name": "科颜氏牛油果保湿眼霜",
    "category": "美妆护肤",
    "brand": "科颜氏",
    "price": 210.0,
}

SECOND_CARD = {
    **PRODUCT_CARD,
    "id": "p_beauty_016",
    "name": "AHC塑颜修护全脸眼霜",
    "brand": "AHC",
    "price": 139.0,
}


class FakePlanningLLM:
    async def stream_messages(self, messages: list[dict]) -> AsyncIterator[str]:
        yield '{"intent":"cart","cart_action":"add","reference_type":"brand",'
        yield '"reference_text":"AHC","quantity":2,"query":"","filters":[],'
        yield '"needs_search":false,"confidence":0.91}'


class FakeBrowsePlanningLLM:
    async def stream_messages(self, messages: list[dict]) -> AsyncIterator[str]:
        yield '{"intent":"browse","cart_action":"none","reference_type":"none",'
        yield '"reference_text":"","quantity":null,"query":"热门好物","filters":[],'
        yield '"needs_search":true,"confidence":0.93}'


def make_session() -> SessionState:
    session = SessionState(session_id="pytest-semantic")
    session.candidate_product_cards = [PRODUCT_CARD, SECOND_CARD]
    return session


def test_rule_plan_understands_brand_reference() -> None:
    plan = build_rule_plan("刚才你说的 AHC 那个，熬夜党能用吗？", make_session())

    assert plan.intent == "ask_product_detail"
    assert plan.reference_type == "brand"
    assert plan.reference_text == "AHC"
    assert ("keyword", "修护") in [(item.kind, item.value) for item in plan.filters]


def test_rule_plan_understands_implicit_cart_quantity() -> None:
    plan = build_rule_plan("那支给我来两件", make_session())

    assert plan.intent == "cart"
    assert plan.cart_action == "add"
    assert plan.quantity == 2
    assert plan.reference_type == "last"


def test_rule_plan_adds_candidate_exclusion_and_soft_preference() -> None:
    plan = build_rule_plan("科颜氏先不要了，换个更温和的", make_session())

    values = [(item.kind, item.value) for item in plan.filters]

    assert plan.intent == "recommend"
    assert ("exclude", "科颜氏") in values
    assert ("keyword", "敏感肌") in values


def test_extract_json_object_ignores_wrapping_text() -> None:
    assert extract_json_object('```json\n{"intent":"recommend"}\n```') == {"intent": "recommend"}


def test_semantic_planner_can_use_llm_json_plan() -> None:
    async def _run():
        return await SemanticPlanner(FakePlanningLLM()).plan("AHC 那个来两件", make_session())

    plan = asyncio.run(_run())

    assert plan.intent == "cart"
    assert plan.cart_action == "add"
    assert plan.reference_type == "brand"
    assert plan.reference_text == "AHC"
    assert plan.quantity == 2


def test_semantic_planner_does_not_downgrade_explicit_product_request_to_browse() -> None:
    async def _run():
        return await SemanticPlanner(FakeBrowsePlanningLLM()).plan("推荐一款运动鞋", make_session())

    plan = asyncio.run(_run())
    values = [(item.kind, item.value) for item in plan.filters]

    assert plan.intent == "recommend"
    assert ("product_type", "clothes.sports_shoes") in values
