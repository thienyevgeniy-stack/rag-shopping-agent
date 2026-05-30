import asyncio
import re
from collections.abc import AsyncIterator
from functools import lru_cache

from server.agent.intent import detect_intent
from server.agent.query_rewriter import rewrite_query
from server.config import get_settings
from server.inputs.processors import TextProcessor
from server.llm.ark_client import ArkChatClient, LLMClient
from server.rag.post_process import SearchFilters
from server.rag.vector_store import ChromaStore, LocalJsonVectorStore, load_product_documents
from server.session.state import FilterCondition, SessionStore
from server.tools.product_search import ProductSearchTool
from server.tools.registry import ToolRegistry


class Orchestrator:
    def __init__(
        self,
        registry: ToolRegistry,
        sessions: SessionStore,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.registry = registry
        self.sessions = sessions
        self.llm_client = llm_client
        self.input_processor = TextProcessor()

    async def stream_chat(
        self,
        session_id: str,
        user_message: str,
    ) -> AsyncIterator[dict]:
        session = self.sessions.get(session_id)
        session.add_user_message(user_message)

        processed = self.input_processor.process(user_message)
        extracted = extract_filters(processed.text)
        session.merge_filters(extracted)

        intent = detect_intent(processed.text)
        query = rewrite_query(processed.text, session)
        filters = SearchFilters.from_session(session)
        cards = self.registry.execute("search_products", query=query, filters=filters)

        session.candidate_products = [card["id"] for card in cards]

        tokens: list[str] = []
        if self.llm_client is not None and cards:
            try:
                async for token in self.llm_client.stream_answer(processed.text, cards, intent.value):
                    tokens.append(token)
                    yield {"event": "token", "data": {"text": token}}
            except Exception:
                if not tokens:
                    answer = build_grounded_answer(processed.text, cards, intent.value)
                    async for item in stream_text(answer):
                        yield item
                    tokens.append(answer)
            if not tokens:
                answer = build_grounded_answer(processed.text, cards, intent.value)
                async for item in stream_text(answer):
                    yield item
                tokens.append(answer)
        else:
            answer = build_grounded_answer(processed.text, cards, intent.value)
            async for item in stream_text(answer):
                yield item
            tokens.append(answer)

        session.add_assistant_message("".join(tokens))

        for card in cards:
            yield {"event": "product_card", "data": card}

        yield {
            "event": "done",
            "data": {
                "session_id": session_id,
                "filters": [item.model_dump() for item in session.filters],
                "exclusions": [item.model_dump() for item in session.exclusions],
            },
        }


async def stream_text(text: str) -> AsyncIterator[dict]:
    for char in text:
        yield {"event": "token", "data": {"text": char}}
        await asyncio.sleep(0.01)


def extract_filters(message: str) -> list[FilterCondition]:
    filters: list[FilterCondition] = []

    max_price = re.search(r"(\d+)\s*(元|块)?\s*(以内|以下|之内)", message)
    if max_price:
        filters.append(FilterCondition(kind="max_price", value=max_price.group(1)))

    if any(word in message for word in ["轻量", "轻便", "轻一点"]):
        filters.append(FilterCondition(kind="keyword", value="轻量"))

    if any(word in message for word in ["油皮", "混油"]):
        filters.append(FilterCondition(kind="keyword", value="油皮"))

    if any(word in message for word in ["敏感肌", "低刺激"]):
        filters.append(FilterCondition(kind="keyword", value="敏感肌"))

    for keyword in ["眼霜", "卸妆油", "跑鞋", "咖啡", "蓝牙耳机", "耳机", "防晒", "面霜"]:
        if keyword in message:
            filters.append(FilterCondition(kind="keyword", value=keyword))

    exclusion_pattern = r"(?:不要|不想要|除了|排除)([^，。,.]+)"
    for match in re.finditer(exclusion_pattern, message):
        value = normalize_exclusion(match.group(1))
        if value:
            filters.append(FilterCondition(kind="exclude", value=value))

    return filters


def normalize_exclusion(value: str) -> str:
    value = value.strip().removesuffix("的").strip()
    if value.startswith("含") and len(value) > 1:
        value = value[1:].strip()
    return value


def build_grounded_answer(message: str, cards: list[dict], intent: str) -> str:
    if not cards:
        return (
            "我在当前商品库里没有找到足够匹配的商品。"
            "你可以换一个类目、放宽预算，或补充更具体的需求。"
        )

    names = "、".join(card["name"] for card in cards[:3])
    prefix = "根据当前商品库检索结果，"
    if intent == "browsing":
        prefix += "我先给你几个可参考的方向："
    else:
        prefix += "更匹配你这次需求的是："

    reasons = []
    for card in cards[:3]:
        reasons.append(f"{card['name']}，价格 {card['price']} 元，理由是 {card['reason']}")

    return f"{prefix}{names}。 " + "；".join(reasons) + "。"


@lru_cache
def get_orchestrator() -> Orchestrator:
    settings = get_settings()
    store = create_store(settings)
    llm_client = create_llm_client(settings)
    registry = ToolRegistry()
    registry.register(ProductSearchTool(store))
    return Orchestrator(registry=registry, sessions=SessionStore(), llm_client=llm_client)


def create_store(settings):
    if settings.use_chroma:
        try:
            store = ChromaStore(settings.chroma_path)
            if store.count() == 0:
                store.add(load_product_documents(settings.product_data_file))
            return store
        except RuntimeError as exc:
            print(f"Chroma unavailable, falling back to local JSON search: {exc}")
    return LocalJsonVectorStore(settings.product_data_file)


def create_llm_client(settings) -> LLMClient | None:
    if not settings.use_llm:
        return None
    if not settings.ark_api_key:
        print("USE_LLM=true but ARK_API_KEY is empty; falling back to template answers.")
        return None
    return ArkChatClient(
        api_key=settings.ark_api_key,
        base_url=settings.ark_base_url,
        model=settings.ark_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
