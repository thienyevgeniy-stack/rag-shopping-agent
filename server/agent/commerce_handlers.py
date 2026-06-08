from collections.abc import AsyncIterator

from server.agent.bundle_optimizer import optimize_bundle_selection
from server.agent.intent import UserIntent
from server.agent.responses import build_done_payload, stream_text
from server.agent.scenarios import ScenarioCatalog, build_bundle_answer, get_default_scenario_catalog
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
    def __init__(self, catalog: ScenarioCatalog | None = None) -> None:
        self.catalog = catalog or get_default_scenario_catalog()

    def matches(self, context: AgentTurnContext) -> bool:
        return context.plan.intent == "bundle" or self.match(context) is not None

    async def handle(self, context: AgentTurnContext) -> AsyncIterator[dict]:
        match = self.match(context)
        if match is None:
            return
        bundle = match.bundle

        grouped_candidates = []
        for slot in bundle.slots:
            slot_cards = context.registry.execute(
                "search_products",
                query=slot.query,
                filters=slot.filters,
                top_k=max(slot.candidate_pool_size, slot.max_items),
            )
            grouped_candidates.append((slot, slot_cards))

        optimization = optimize_bundle_selection(
            grouped_candidates,
            total_budget=context.filters.max_price,
        )
        grouped_cards = optimization.grouped_cards
        cards: list[dict] = []
        for _, slot_cards in grouped_cards:
            cards.extend(slot_cards)

        context.session.candidate_products = [card["id"] for card in cards]
        context.session.candidate_product_cards = cards
        context.metadata["strategy"] = {
            "bundle_id": bundle.id,
            "catalog_version": bundle.source_version,
            "confidence": bundle.match_confidence,
            "signals": list(bundle.match_signals),
            "matched_terms": list(bundle.matched_terms),
            "governance": bundle.governance or {},
            "slot_count": len(bundle.slots),
            "filled_slots": optimization.filled_slots,
            "missing_required_slots": optimization.missing_required_slots,
            "total_budget": context.filters.max_price,
            "selected_total_price": round(optimization.total_price, 2),
            "within_budget": optimization.within_budget,
        }

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

    def match(self, context: AgentTurnContext):
        match = self.catalog.route(
            context.message,
            plan=context.plan,
            filters=context.filters,
            session_id=context.session_id,
        )
        if match is not None:
            return match
        if context.query and context.query != context.message:
            return self.catalog.route(
                context.query,
                plan=context.plan,
                filters=context.filters,
                session_id=context.session_id,
            )
        return None
