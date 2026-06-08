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

    primary = cards[0]
    alternatives = cards[1:3]

    if intent == "browsing":
        opening = "我先按当前商品库给你几个可参考的方向。"
    else:
        opening = "我会优先推荐这款。"

    pieces = [
        opening,
        f"首选是 {format_product_reference(primary)}，{clean_reason(primary.get('reason', ''))}",
    ]
    if alternatives:
        pieces.append("另外可以顺手对比：")
        for card in alternatives:
            pieces.append(f"{format_product_reference(card)}，{clean_reason(card.get('reason', ''))}")
    pieces.append("如果你更看重预算、尺码/肤质、使用场景，我可以继续帮你把候选缩到一两款。")
    return "\n".join(piece for piece in pieces if piece.strip())


def format_product_reference(card: dict) -> str:
    name = str(card.get("name", "")).strip()
    brand = str(card.get("brand", "")).strip()
    price = card.get("price", "")
    brand_prefix = f"{brand} " if brand and brand not in name else ""
    return f"{brand_prefix}{name}（¥{format_price(price)}）"


def format_price(value) -> str:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return str(value)
    if price.is_integer():
        return str(int(price))
    return f"{price:.2f}".rstrip("0").rstrip(".")


def clean_reason(reason: str) -> str:
    text = " ".join(str(reason).split()).strip()
    if not text:
        return "它与当前检索条件相近。"
    if text[-1] not in "。！？!?；;":
        text += "。"
    return text
