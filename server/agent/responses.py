import asyncio
from collections.abc import AsyncIterator


async def stream_text(text: str) -> AsyncIterator[dict]:
    for char in text:
        yield {"event": "token", "data": {"text": char}}
        await asyncio.sleep(0.01)


def build_done_payload(session_id: str, session, needs_clarification: bool) -> dict:
    return {
        "session_id": session_id,
        "filters": [item.model_dump() for item in session.filters],
        "exclusions": [item.model_dump() for item in session.exclusions],
        "needs_clarification": needs_clarification,
        "pending_subject": session.pending_subject,
    }


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
