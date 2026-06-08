from collections.abc import AsyncIterator

from server.agent.intent import UserIntent
from server.agent.responses import build_done_payload, stream_text
from server.agent.scenarios import build_bundle_answer, detect_scenario_bundle
from server.agent.workflow import AgentTurnContext
from server.tools.product_compare import build_comparison_answer


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


class ScenarioBundleHandler:
    def matches(self, context: AgentTurnContext) -> bool:
        return context.plan.intent == "bundle" or detect_scenario_bundle(context.message) is not None

    async def handle(self, context: AgentTurnContext) -> AsyncIterator[dict]:
        bundle = detect_scenario_bundle(context.message)
        if bundle is None:
            bundle = detect_scenario_bundle(context.query)
        if bundle is None:
            return

        grouped_cards: list[tuple[object, list[dict]]] = []
        seen: set[str] = set()
        cards: list[dict] = []
        for slot in bundle.slots:
            slot_cards = context.registry.execute(
                "search_products",
                query=slot.query,
                filters=slot.filters,
                top_k=slot.max_items,
            )
            unique_slot_cards = []
            for card in slot_cards:
                if card["id"] in seen:
                    continue
                seen.add(card["id"])
                unique_slot_cards.append(card)
                cards.append(card)
            grouped_cards.append((slot, unique_slot_cards))

        context.session.candidate_products = [card["id"] for card in cards]
        context.session.candidate_product_cards = cards

        answer = build_bundle_answer(bundle, grouped_cards)
        async for item in stream_text(answer):
            yield item
        context.session.add_assistant_message(answer)
        for card in cards:
            yield {"event": "product_card", "data": card}
        yield {
            "event": "done",
            "data": build_done_payload(context.session_id, context.session, needs_clarification=False),
        }
