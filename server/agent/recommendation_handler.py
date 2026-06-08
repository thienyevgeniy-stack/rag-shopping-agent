from collections.abc import AsyncIterator
import re

from server.agent.grounding import guard_grounded_answer
from server.agent.responses import build_done_payload, build_grounded_answer, stream_text
from server.agent.workflow import AgentTurnContext


MARKDOWN_EMPHASIS_PATTERN = re.compile(r"(\*\*|__)(.*?)\1")


class RecommendationHandler:
    def matches(self, context: AgentTurnContext) -> bool:
        return True

    async def handle(self, context: AgentTurnContext) -> AsyncIterator[dict]:
        cards = context.registry.execute("search_products", query=context.query, filters=context.filters)
        context.session.candidate_products = [card["id"] for card in cards]
        context.session.candidate_product_cards = cards

        answer = ""
        if context.llm_client is not None and cards:
            llm_tokens: list[str] = []
            try:
                async for token in context.llm_client.stream_answer(
                    context.message,
                    cards,
                    context.intent.value,
                ):
                    llm_tokens.append(token)
            except Exception:
                if not llm_tokens:
                    llm_tokens = []

            fallback_answer = build_grounded_answer(context.message, cards, context.intent.value)
            if llm_tokens:
                guarded = guard_grounded_answer(
                    answer=clean_answer_text("".join(llm_tokens)),
                    cards=cards,
                    fallback_answer=fallback_answer,
                    allowed_extra_prices=[context.filters.max_price] if context.filters.max_price is not None else [],
                )
                if not guarded.safe:
                    yield {
                        "event": "guardrail",
                        "data": {
                            "action": guarded.action,
                            "violations": guarded.violations,
                        },
                    }
                context.metadata["grounding"] = {
                    "safe": guarded.safe,
                    "violations": guarded.violations,
                    "citations": guarded.citations,
                }
                answer = guarded.answer
            else:
                answer = fallback_answer
        else:
            answer = build_grounded_answer(context.message, cards, context.intent.value)

        cards = order_cards_by_answer_mentions(answer, cards)
        context.session.candidate_products = [card["id"] for card in cards]
        context.session.candidate_product_cards = cards

        async for item in stream_text(answer):
            yield item

        context.session.add_assistant_message(answer)

        for card in cards:
            yield {"event": "product_card", "data": card}

        yield {
            "event": "done",
            "data": build_done_payload(context.session_id, context.session, needs_clarification=False),
        }


def order_cards_by_answer_mentions(answer: str, cards: list[dict]) -> list[dict]:
    if not answer.strip() or len(cards) <= 1:
        return cards

    normalized_answer = answer.lower()

    def mention_position(card: dict, index: int) -> tuple[int, int]:
        candidates = [
            str(card.get("name", "")).strip(),
            str(card.get("brand", "")).strip(),
        ]
        positions = []
        for value in candidates:
            if not value:
                continue
            position = normalized_answer.find(value.lower())
            if position >= 0:
                positions.append(position)
        if not positions:
            return (10_000_000, index)
        return (min(positions), index)

    return [
        card
        for _, card in sorted(
            enumerate(cards),
            key=lambda item: mention_position(item[1], item[0]),
        )
    ]


def clean_answer_text(answer: str) -> str:
    text = MARKDOWN_EMPHASIS_PATTERN.sub(lambda match: match.group(2), answer)
    return text.replace("```", "").replace("`", "").strip()
