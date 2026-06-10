from collections.abc import AsyncIterator
import asyncio
from contextlib import suppress
from dataclasses import asdict, dataclass
import logging
import re

from server.agent.grounding import guard_grounded_answer
from server.agent.product_discovery import build_product_discovery_policy, resolve_product_cards_for_answer
from server.agent.responses import (
    build_done_payload,
    build_grounded_answer,
    stream_text,
)
from server.agent.workflow import AgentTurnContext


MARKDOWN_EMPHASIS_PATTERN = re.compile(r"(\*\*|__)(.*?)\1")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProductSearchExecution:
    cards: list[dict]
    diagnostics: object | None = None
    degraded: bool = False
    reason: str = ""


class RecommendationHandler:
    def matches(self, context: AgentTurnContext) -> bool:
        return True

    async def handle(self, context: AgentTurnContext) -> AsyncIterator[dict]:
        product_search = context.registry.get("search_products")
        discovery_policy = build_product_discovery_policy(context.plan)
        search_execution = await execute_product_search_with_budget(
            product_search=product_search,
            query=context.query,
            filters=context.filters,
            top_k=discovery_policy.top_k,
            timeout_seconds=context.retrieval_timeout_seconds,
        )
        cards = search_execution.cards
        if search_execution.diagnostics is not None:
            context.metadata["retrieval"] = asdict(search_execution.diagnostics)
        if search_execution.degraded:
            context.metadata["retrieval_degraded"] = {
                "reason": search_execution.reason,
                "timeout_seconds": context.retrieval_timeout_seconds,
            }
        context.metadata["product_discovery"] = discovery_policy.as_metadata()
        context.metadata["catalog_listing"] = discovery_policy.presentation_mode == "listing"
        if should_suppress_unscoped_product_cards(context):
            context.metadata["catalog_gap"] = {
                "reason": "no_structured_product_scope",
                "suppressed_product_ids": [str(card.get("id", "")) for card in cards],
            }
            cards = []
        context.session.candidate_products = [card["id"] for card in cards]
        context.session.candidate_product_cards = cards

        fallback_answer = build_grounded_answer(
            context.message,
            cards,
            context.intent.value,
            presentation_mode=discovery_policy.presentation_mode,
        )
        answer = fallback_answer
        llm_answer = (
            await collect_llm_answer_with_budget(context, cards)
            if discovery_policy.allow_llm_answer
            else ""
        )
        if llm_answer:
            guarded = guard_grounded_answer(
                answer=clean_answer_text(llm_answer),
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
            context.metadata["answer_source"] = "llm" if guarded.safe else "grounded_fallback_guardrail"
            answer = guarded.answer
        else:
            context.metadata["grounding"] = {
                "safe": True,
                "violations": [],
                "citations": [],
            }
            context.metadata["answer_source"] = "grounded_fallback"

        card_resolution = resolve_product_cards_for_answer(
            answer=answer,
            cards=cards,
            policy=discovery_policy,
        )
        cards = card_resolution.cards
        context.metadata["card_binding"] = card_resolution.metadata
        context.session.candidate_products = [card["id"] for card in cards]
        context.session.candidate_product_cards = cards

        async for item in stream_text(answer):
            yield item

        context.session.add_assistant_message(answer)

        for card in cards:
            yield {"event": "product_card", "data": card}

        yield {
            "event": "done",
            "data": build_done_payload(
                context.session_id,
                context.session,
                needs_clarification=False,
                plan=context.plan,
                trace_id=context.trace_id,
            ),
        }


async def collect_llm_answer_with_budget(context: AgentTurnContext, cards: list[dict]) -> str:
    if context.llm_client is None or not cards:
        return ""
    budget = max(0.0, float(context.recommendation_llm_budget_seconds or 0.0))
    if budget <= 0:
        return ""

    task = asyncio.create_task(collect_llm_answer(context, cards))
    try:
        return await asyncio.wait_for(task, timeout=budget)
    except TimeoutError:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        context.metadata["llm_timeout_budget_seconds"] = budget
        return ""
    except Exception as exc:
        logger.warning("LLM answer stream failed; using grounded fallback answer: %s", exc)
        return ""


async def collect_llm_answer(context: AgentTurnContext, cards: list[dict]) -> str:
    chunks: list[str] = []
    async for token in context.llm_client.stream_answer(  # type: ignore[union-attr]
        context.message,
        cards,
        context.intent.value,
    ):
        chunks.append(token)
    return "".join(chunks)


async def execute_product_search_with_budget(
    *,
    product_search,
    query: str,
    filters,
    top_k: int,
    timeout_seconds: float,
) -> ProductSearchExecution:
    def run_search() -> ProductSearchExecution:
        if hasattr(product_search, "run_with_diagnostics"):
            result = product_search.run_with_diagnostics(query=query, filters=filters, top_k=top_k)
            return ProductSearchExecution(cards=result.cards, diagnostics=result.diagnostics)
        cards = product_search.run(query=query, filters=filters, top_k=top_k)
        return ProductSearchExecution(cards=cards)

    try:
        if timeout_seconds <= 0:
            return await asyncio.to_thread(run_search)
        return await asyncio.wait_for(asyncio.to_thread(run_search), timeout=timeout_seconds)
    except TimeoutError:
        logger.warning("Product retrieval timed out after %.3fs; using empty fallback.", timeout_seconds)
        return ProductSearchExecution(cards=[], degraded=True, reason="retrieval_timeout")
    except Exception as exc:
        logger.warning("Product retrieval failed; using empty fallback: %s", exc)
        return ProductSearchExecution(cards=[], degraded=True, reason="retrieval_error")


def clean_answer_text(answer: str) -> str:
    text = MARKDOWN_EMPHASIS_PATTERN.sub(lambda match: match.group(2), answer)
    return text.replace("```", "").replace("`", "").strip()


def should_suppress_unscoped_product_cards(context: AgentTurnContext) -> bool:
    if context.plan.intent not in {"recommend", "browse"}:
        return False
    if context.plan.reference_type != "none":
        return False
    filters = context.filters
    return not any(
        [
            filters.product_types,
            filters.categories,
            filters.brands,
            filters.preferred_brands,
            filters.keywords,
            filters.should_keywords,
            filters.facets,
        ]
    )
