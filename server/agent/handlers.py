from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Protocol

from server.agent.clarification import build_clarification_question, get_clarification_subject
from server.agent.context import (
    build_contextual_product_answer,
    is_cheaper_follow_up,
    select_contextual_product,
)
from server.agent.intent import UserIntent
from server.agent.responses import build_done_payload, build_grounded_answer, stream_text
from server.agent.semantic import SemanticPlan
from server.llm.ark_client import LLMClient
from server.rag.post_process import SearchFilters
from server.session.state import SessionState
from server.tools.product_compare import build_comparison_answer
from server.tools.registry import ToolRegistry


@dataclass
class AgentTurnContext:
    session_id: str
    message: str
    intent: UserIntent
    query: str
    filters: SearchFilters
    plan: SemanticPlan
    session: SessionState
    registry: ToolRegistry
    llm_client: LLMClient | None
    selected_handler: str = ""


class AgentHandler(Protocol):
    def matches(self, context: AgentTurnContext) -> bool:
        ...

    async def handle(self, context: AgentTurnContext) -> AsyncIterator[dict]:
        ...


class AgentWorkflow:
    def __init__(self, handlers: Sequence[AgentHandler]) -> None:
        self.handlers = list(handlers)

    async def stream(self, context: AgentTurnContext) -> AsyncIterator[dict]:
        for handler in self.handlers:
            if handler.matches(context):
                context.selected_handler = handler.__class__.__name__
                async for item in handler.handle(context):
                    yield item
                return
        raise RuntimeError("No agent handler matched the turn.")


class ClarificationHandler:
    def matches(self, context: AgentTurnContext) -> bool:
        return bool(get_clarification_subject(context.message, context.session))

    async def handle(self, context: AgentTurnContext) -> AsyncIterator[dict]:
        answer = build_clarification_question(context.message, context.session)
        async for item in stream_text(answer):
            yield item
        context.session.add_assistant_message(answer)
        yield {
            "event": "done",
            "data": build_done_payload(context.session_id, context.session, needs_clarification=True),
        }


class CartHandler:
    def matches(self, context: AgentTurnContext) -> bool:
        return context.plan.intent == "cart" or context.intent == UserIntent.CART

    async def handle(self, context: AgentTurnContext) -> AsyncIterator[dict]:
        result = context.registry.execute(
            "manage_cart",
            message=context.message,
            session=context.session,
            plan=context.plan,
        )
        async for item in stream_text(result["answer"]):
            yield item
        context.session.add_assistant_message(result["answer"])
        yield {"event": "cart_update", "data": result["cart"]}
        yield {
            "event": "done",
            "data": build_done_payload(context.session_id, context.session, needs_clarification=False),
        }


class CompareHandler:
    def matches(self, context: AgentTurnContext) -> bool:
        return context.plan.intent == "compare" or context.intent == UserIntent.COMPARE

    async def handle(self, context: AgentTurnContext) -> AsyncIterator[dict]:
        result = context.registry.execute("compare_products", query=context.query, filters=context.filters)
        cards = result["cards"]
        comparison = result["comparison"]
        context.session.candidate_products = [card["id"] for card in cards]
        context.session.candidate_product_cards = cards

        answer = build_comparison_answer(comparison)
        async for item in stream_text(answer):
            yield item
        context.session.add_assistant_message(answer)
        for card in cards:
            yield {"event": "product_card", "data": card}
        yield {"event": "comparison_card", "data": comparison}
        yield {
            "event": "done",
            "data": build_done_payload(context.session_id, context.session, needs_clarification=False),
        }


class ContextFollowUpHandler:
    def matches(self, context: AgentTurnContext) -> bool:
        return (
            context.plan.intent == "ask_product_detail"
            and select_contextual_product(context.message, context.session.candidate_product_cards, context.plan)
            is not None
            and not is_cheaper_follow_up(context.message)
        )

    async def handle(self, context: AgentTurnContext) -> AsyncIterator[dict]:
        referenced_card = select_contextual_product(
            context.message,
            context.session.candidate_product_cards,
            context.plan,
        )
        if referenced_card is None:
            return

        answer = build_contextual_product_answer(context.message, referenced_card)
        async for item in stream_text(answer):
            yield item
        context.session.add_assistant_message(answer)
        context.session.candidate_products = [referenced_card["id"]]
        context.session.candidate_product_cards = [referenced_card]
        yield {"event": "product_card", "data": referenced_card}
        yield {
            "event": "done",
            "data": build_done_payload(context.session_id, context.session, needs_clarification=False),
        }


class RecommendationHandler:
    def matches(self, context: AgentTurnContext) -> bool:
        return True

    async def handle(self, context: AgentTurnContext) -> AsyncIterator[dict]:
        cards = context.registry.execute("search_products", query=context.query, filters=context.filters)
        context.session.candidate_products = [card["id"] for card in cards]
        context.session.candidate_product_cards = cards

        tokens: list[str] = []
        if context.llm_client is not None and cards:
            try:
                async for token in context.llm_client.stream_answer(
                    context.message,
                    cards,
                    context.intent.value,
                ):
                    tokens.append(token)
                    yield {"event": "token", "data": {"text": token}}
            except Exception:
                if not tokens:
                    answer = build_grounded_answer(context.message, cards, context.intent.value)
                    async for item in stream_text(answer):
                        yield item
                    tokens.append(answer)
            if not tokens:
                answer = build_grounded_answer(context.message, cards, context.intent.value)
                async for item in stream_text(answer):
                    yield item
                tokens.append(answer)
        else:
            answer = build_grounded_answer(context.message, cards, context.intent.value)
            async for item in stream_text(answer):
                yield item
            tokens.append(answer)

        context.session.add_assistant_message("".join(tokens))

        for card in cards:
            yield {"event": "product_card", "data": card}

        yield {
            "event": "done",
            "data": build_done_payload(context.session_id, context.session, needs_clarification=False),
        }


def build_default_workflow() -> AgentWorkflow:
    return AgentWorkflow(
        handlers=[
            ClarificationHandler(),
            CartHandler(),
            CompareHandler(),
            ContextFollowUpHandler(),
            RecommendationHandler(),
        ]
    )
