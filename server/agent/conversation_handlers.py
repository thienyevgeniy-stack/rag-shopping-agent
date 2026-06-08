from collections.abc import AsyncIterator

from server.agent.clarification import build_clarification_question, get_clarification_subject
from server.agent.context import (
    build_contextual_product_answer,
    is_cheaper_follow_up,
    select_contextual_product,
)
from server.agent.responses import build_done_payload, stream_text
from server.agent.workflow import AgentTurnContext


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
