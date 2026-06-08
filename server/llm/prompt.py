SYSTEM_PROMPT = """你是一个电商智能导购助手。
你只能基于提供的商品上下文回答，不得编造不存在的商品、价格、库存、优惠券、活动或功效。
如果商品上下文不足以满足用户需求，要明确说明不足，并建议用户放宽或补充条件。
回答要像真实导购：先给最推荐的一款，再说明为什么适合，必要时给备选差异。
不要机械复读字段，不要输出被截断的半句话；每个理由必须是完整自然句。
不要使用 Markdown 标记，例如 **加粗**、列表符号或代码块。"""


def build_product_context(cards: list[dict]) -> str:
    if not cards:
        return "当前没有可用商品。"

    lines: list[str] = []
    for index, card in enumerate(cards, 1):
        evidence = card.get("evidence") if isinstance(card.get("evidence"), dict) else {}
        highlights = evidence.get("highlights") if isinstance(evidence.get("highlights"), list) else []
        lines.append(
            "\n".join(
                [
                    f"{index}. 商品ID: {card.get('id', '')}",
                    f"   名称: {card.get('name', '')}",
                    f"   类目: {card.get('category', '')}",
                    f"   品牌: {card.get('brand', '')}",
                    f"   价格: {card.get('price', '')} 元",
                    f"   推荐依据: {card.get('reason', '')}",
                    f"   商品证据要点: {' '.join(str(item) for item in highlights[:2])}",
                ]
            )
        )
    return "\n".join(lines)


def build_grounded_messages(user_message: str, cards: list[dict], intent: str) -> list[dict]:
    product_context = build_product_context(cards)
    user_prompt = f"""用户需求：
{user_message}

识别意图：
{intent}

候选商品：
{product_context}

请基于候选商品回答。必须遵守：
1. 只推荐候选商品中的商品。
2. 价格、品牌、类目必须与候选商品一致。
3. 不要编造优惠、库存、销量、功效或外部评价。
4. 如果候选商品与需求不完全匹配，要如实说明。
5. 用自然导购口吻回答，不要截断句子；理由要来自“推荐依据”或“商品证据要点”。
"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
