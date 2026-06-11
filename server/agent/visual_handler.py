from collections.abc import AsyncIterator

from server.agent.responses import build_done_payload, format_product_reference, stream_text
from server.agent.workflow import AgentTurnContext


class VisualMatchHandler:
    def matches(self, context: AgentTurnContext) -> bool:
        return context.modality == "image" and bool(context.visual_matches)

    async def handle(self, context: AgentTurnContext) -> AsyncIterator[dict]:
        cards = list(context.visual_matches[:3])
        context.session.candidate_products = [str(card.get("id", "")) for card in cards if card.get("id")]
        context.session.candidate_product_cards = cards
        context.metadata["visual_match_handler"] = {
            "card_count": len(cards),
            "product_ids": list(context.session.candidate_products),
        }

        answer = build_visual_match_answer(cards)
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


def build_visual_match_answer(cards: list[dict]) -> str:
    if not cards:
        return "我看到了图片，但当前商品库里没有足够可靠的视觉相似商品。你可以补充品类、品牌或预算，我再继续找。"

    pieces = [
        "我先按图片做了相似商品匹配，下面这些是当前商品库里最接近的候选；它们是相似款参考，不会被说成百分百同款。",
        f"优先看 {format_product_reference(cards[0])}，它和图片的视觉特征最接近。",
    ]
    if len(cards) > 1:
        pieces.append("另外也可以对比：")
        for card in cards[1:]:
            pieces.append(format_product_reference(card))
    return "\n".join(pieces)
