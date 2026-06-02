import asyncio
from collections.abc import AsyncIterator

from server.agent.orchestrator import Orchestrator
from server.session.state import SessionStore
from server.tools.product_compare import ProductCompareTool
from server.tools.registry import ToolRegistry


PRODUCT_CARD = {
    "id": "p_beauty_021",
    "name": "科颜氏牛油果保湿眼霜",
    "category": "美妆护肤",
    "brand": "科颜氏",
    "price": 210.0,
    "image_url": "",
    "detail_url": "",
    "reason": "匹配眼霜需求",
    "score": 10.0,
}


class FixedSearchTool:
    name = "search_products"

    def __init__(self, cards: list[dict]) -> None:
        self.cards = cards
        self.calls: list[dict] = []

    def run(self, **kwargs) -> list[dict]:
        self.calls.append(kwargs)
        return self.cards


class FakeLLMClient:
    def __init__(self, tokens: list[str] | None = None, should_fail: bool = False) -> None:
        self.tokens = tokens or []
        self.should_fail = should_fail
        self.calls: list[dict] = []

    async def stream_answer(
        self,
        user_message: str,
        cards: list[dict],
        intent: str,
    ) -> AsyncIterator[str]:
        self.calls.append({"user_message": user_message, "cards": cards, "intent": intent})
        if self.should_fail:
            raise RuntimeError("LLM failed")
        for token in self.tokens:
            yield token


def make_orchestrator(cards: list[dict], llm_client: FakeLLMClient | None) -> Orchestrator:
    registry = ToolRegistry()
    search_tool = FixedSearchTool(cards)
    registry.register(search_tool)
    registry.register(ProductCompareTool(search_tool))
    return Orchestrator(registry=registry, sessions=SessionStore(), llm_client=llm_client)


def collect_events(orchestrator: Orchestrator, message: str) -> list[dict]:
    async def _collect() -> list[dict]:
        return [item async for item in orchestrator.stream_chat("pytest-llm", message)]

    return asyncio.run(_collect())


def token_text(events: list[dict]) -> str:
    return "".join(item["data"]["text"] for item in events if item["event"] == "token")


def test_orchestrator_streams_llm_answer_when_configured() -> None:
    llm = FakeLLMClient(tokens=["LLM", "回答"])
    orchestrator = make_orchestrator(cards=[PRODUCT_CARD], llm_client=llm)

    events = collect_events(orchestrator, "推荐一款眼霜")

    assert token_text(events) == "LLM回答"
    assert any(item["event"] == "product_card" for item in events)
    assert llm.calls
    assert llm.calls[0]["cards"][0]["id"] == "p_beauty_021"


def test_orchestrator_falls_back_to_template_when_llm_fails() -> None:
    llm = FakeLLMClient(should_fail=True)
    orchestrator = make_orchestrator(cards=[PRODUCT_CARD], llm_client=llm)

    events = collect_events(orchestrator, "推荐一款眼霜")

    assert "根据当前商品库检索结果" in token_text(events)
    assert any(item["event"] == "product_card" for item in events)


def test_orchestrator_skips_llm_when_no_cards() -> None:
    llm = FakeLLMClient(tokens=["不会被调用"])
    orchestrator = make_orchestrator(cards=[], llm_client=llm)

    events = collect_events(orchestrator, "推荐一款不存在的商品")

    assert "没有找到足够匹配的商品" in token_text(events)
    assert llm.calls == []


def test_orchestrator_asks_clarification_for_vague_phone_request() -> None:
    orchestrator = make_orchestrator(cards=[PRODUCT_CARD], llm_client=None)

    events = collect_events(orchestrator, "推荐一款手机")

    assert "你更看重拍照、续航、性能还是性价比" in token_text(events)
    assert not any(item["event"] == "product_card" for item in events)
    done = [item for item in events if item["event"] == "done"][-1]
    assert done["data"]["needs_clarification"] is True
    assert done["data"]["pending_subject"] == "手机"


def test_orchestrator_emits_comparison_card_for_compare_intent() -> None:
    other_card = {
        **PRODUCT_CARD,
        "id": "p_beauty_016",
        "name": "AHC塑颜修护全脸眼霜",
        "brand": "AHC",
        "price": 139.0,
        "reason": "匹配眼霜需求",
    }
    llm = FakeLLMClient(tokens=["不应调用"])
    orchestrator = make_orchestrator(cards=[PRODUCT_CARD, other_card], llm_client=llm)

    events = collect_events(orchestrator, "科颜氏和AHC哪个眼霜更适合干皮")

    assert "我先基于当前商品库做对比" in token_text(events)
    assert any(item["event"] == "comparison_card" for item in events)
    assert sum(1 for item in events if item["event"] == "product_card") == 2
    assert llm.calls == []
