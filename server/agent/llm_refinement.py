from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import logging
import re

from server.agent.grounding import guard_grounded_answer
from server.agent.workflow import AgentTurnContext


MARKDOWN_EMPHASIS_PATTERN = re.compile(r"(\*\*|__)(.*?)\1")
logger = logging.getLogger(__name__)


async def collect_llm_refinement_after_fast_answer(
    *,
    context: AgentTurnContext,
    cards: list[dict],
    discovery_policy_allows_llm: bool,
) -> str:
    if not discovery_policy_allows_llm:
        return ""
    if context.llm_client is None or not cards:
        return ""
    if context.recommendation_llm_budget_seconds > 0:
        return ""
    if not context.recommendation_llm_async_enabled:
        return ""

    budget = max(0.0, float(context.recommendation_llm_async_budget_seconds or 0.0))
    if budget <= 0:
        return ""

    context.metadata["llm_async_refinement"] = {
        "enabled": True,
        "budget_seconds": budget,
        "candidate_product_ids": [str(card.get("id", "")) for card in cards],
    }
    task = asyncio.create_task(collect_llm_refinement(context, cards))
    try:
        refinement = await asyncio.wait_for(task, timeout=budget)
    except TimeoutError:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        context.metadata["llm_async_refinement"] = {
            **dict(context.metadata.get("llm_async_refinement", {})),
            "status": "timeout",
        }
        return ""
    except Exception as exc:
        logger.warning("LLM async refinement failed; keeping fast grounded answer: %s", exc)
        context.metadata["llm_async_refinement"] = {
            **dict(context.metadata.get("llm_async_refinement", {})),
            "status": "error",
            "error": exc.__class__.__name__,
        }
        return ""

    refinement = clean_llm_text(refinement)
    if not refinement:
        context.metadata["llm_async_refinement"] = {
            **dict(context.metadata.get("llm_async_refinement", {})),
            "status": "empty",
        }
        return ""

    guarded = guard_grounded_answer(
        answer=refinement,
        cards=cards,
        fallback_answer="",
        allowed_extra_prices=allowed_filter_prices(context.filters),
    )
    context.metadata["llm_async_refinement"] = {
        **dict(context.metadata.get("llm_async_refinement", {})),
        "status": "accepted" if guarded.safe else "guardrail_blocked",
        "violations": guarded.violations,
        "citations": guarded.citations,
    }
    if not guarded.safe:
        return ""
    return guarded.answer


async def collect_llm_refinement(context: AgentTurnContext, cards: list[dict]) -> str:
    chunks: list[str] = []
    stream_messages = getattr(context.llm_client, "stream_messages", None)
    if callable(stream_messages):
        async for token in stream_messages(build_refinement_messages(context.message, cards)):
            chunks.append(token)
        return "".join(chunks)

    async for token in context.llm_client.stream_answer(  # type: ignore[union-attr]
        context.message,
        cards,
        context.intent.value,
    ):
        chunks.append(token)
    return "".join(chunks)


def build_refinement_messages(user_message: str, cards: list[dict]) -> list[dict]:
    compact_cards = [
        {
            "id": card.get("id", ""),
            "name": card.get("name", ""),
            "brand": card.get("brand", ""),
            "category": card.get("category", ""),
            "price": card.get("price", ""),
            "reason": card.get("reason", ""),
            "evidence": (card.get("evidence") or {}).get("highlights", [])
            if isinstance(card.get("evidence"), dict)
            else [],
        }
        for card in cards[:3]
    ]
    return [
        {
            "role": "system",
            "content": (
                "You are a Chinese ecommerce shopping guide. Use only the provided product facts. "
                "Do not invent products, prices, stock, discounts, policies, reviews, or effects. "
                "Write concise, natural Chinese."
            ),
        },
        {
            "role": "user",
            "content": (
                "The app has already shown a grounded recommendation and product cards. "
                "Add one short refinement for the same selected products only. "
                "Do not introduce new products. Do not use Markdown. "
                "Keep it to 1-2 complete Chinese sentences.\n\n"
                f"User request: {user_message}\n"
                "Selected products JSON:\n"
                f"{json.dumps(compact_cards, ensure_ascii=False)}"
            ),
        },
    ]


def allowed_filter_prices(filters) -> list[float]:
    prices: list[float] = []
    if getattr(filters, "min_price", None) is not None:
        prices.append(filters.min_price)
    if getattr(filters, "max_price", None) is not None:
        prices.append(filters.max_price)
    return prices


def clean_llm_text(answer: str) -> str:
    text = MARKDOWN_EMPHASIS_PATTERN.sub(lambda match: match.group(2), answer)
    return text.replace("```", "").replace("`", "").strip()
