import re
from typing import Any

from server.agent.context import select_contextual_product
from server.session.state import SessionState


class CartTool:
    name = "manage_cart"

    def run(self, message: str, session: SessionState, plan=None) -> dict[str, Any]:
        action = detect_cart_action(message, plan)
        if action == "remove":
            answer = remove_from_cart(message, session)
        elif action == "update_quantity":
            answer = update_quantity(message, session, plan)
        elif action == "checkout":
            answer = build_checkout_answer(session)
        elif action == "view":
            answer = build_cart_summary(session.cart)
        else:
            answer = add_to_cart(message, session, plan)

        return {
            "answer": answer,
            "cart": build_cart_payload(session.cart),
        }


def detect_cart_action(message: str, plan=None) -> str:
    plan_action = getattr(plan, "cart_action", "none")
    if plan_action and plan_action != "none":
        return plan_action

    if any(word in message for word in ["下单", "结算", "提交订单"]):
        return "checkout"
    if any(word in message for word in ["删除", "删掉", "移除", "不要这个"]):
        return "remove"
    if any(word in message for word in ["数量", "改成", "改为", "设为", "加一件", "减一件"]):
        return "update_quantity"
    if "购物车" in message and not any(word in message for word in ["加到", "加入", "加购", "放到", "放进"]):
        return "view"
    if re.search(r"(来|要|买)\s*(\d+|一|二|两|三|四|五)?\s*(件|个|支|瓶|台|份)", message):
        return "add"
    return "add"


def add_to_cart(message: str, session: SessionState, plan=None) -> str:
    if not session.candidate_product_cards:
        return "我还没有可加购的候选商品。你可以先让我推荐或对比商品，再说“把刚才那款加到购物车”。"

    product = select_product_from_candidates(message, session.candidate_product_cards, plan)
    quantity = getattr(plan, "quantity", None) or extract_quantity(message) or 1
    existing = next((item for item in session.cart if item["product_id"] == product["id"]), None)
    if existing:
        existing["quantity"] += quantity
    else:
        session.cart.append(build_cart_item(product, quantity))

    return f"已将 {product['name']} 加入购物车，数量 {quantity}。{build_cart_totals_sentence(session.cart)}"


def remove_from_cart(message: str, session: SessionState) -> str:
    if not session.cart:
        return "购物车目前是空的，暂时没有商品可以删除。"

    index = extract_ordinal_index(message, default=len(session.cart) - 1)
    if index < 0 or index >= len(session.cart):
        return f"购物车里没有第 {index + 1} 个商品。{build_cart_totals_sentence(session.cart)}"

    item = session.cart.pop(index)
    return f"已从购物车删除 {item['name']}。{build_cart_totals_sentence(session.cart)}"


def update_quantity(message: str, session: SessionState, plan=None) -> str:
    if not session.cart:
        return "购物车目前是空的，暂时没有商品可以修改数量。"

    index = extract_ordinal_index(message, default=len(session.cart) - 1)
    if index < 0 or index >= len(session.cart):
        return f"购物车里没有第 {index + 1} 个商品。"

    item = session.cart[index]
    if "加一件" in message:
        item["quantity"] += 1
    elif "减一件" in message:
        item["quantity"] = max(1, item["quantity"] - 1)
    else:
        quantity = getattr(plan, "quantity", None) or extract_quantity(message)
        if quantity is None:
            return "我还没识别到要修改成几件，可以说“把数量改成 2”。"
        item["quantity"] = max(1, quantity)

    return f"已将 {item['name']} 的数量改为 {item['quantity']}。{build_cart_totals_sentence(session.cart)}"


def build_checkout_answer(session: SessionState) -> str:
    if not session.cart:
        return "购物车目前是空的，暂时无法下单。你可以先把商品加入购物车。"

    return (
        "已为你生成模拟订单确认："
        f"{build_cart_summary(session.cart)} "
        "当前 Demo 不会真实支付或提交地址，只展示购物车到下单确认的闭环。"
    )


def build_cart_item(product: dict, quantity: int) -> dict[str, Any]:
    return {
        "product_id": product.get("id", ""),
        "name": product.get("name", ""),
        "brand": product.get("brand", ""),
        "category": product.get("category", ""),
        "price": float(product.get("price", 0)),
        "quantity": quantity,
        "image_url": product.get("image_url", ""),
        "detail_url": product.get("detail_url", ""),
    }


def build_cart_payload(cart: list[dict]) -> dict[str, Any]:
    total_quantity = sum(int(item.get("quantity", 0)) for item in cart)
    total_price = sum(float(item.get("price", 0)) * int(item.get("quantity", 0)) for item in cart)
    return {
        "items": cart,
        "total_quantity": total_quantity,
        "total_price": round(total_price, 2),
        "is_empty": total_quantity == 0,
    }


def build_cart_summary(cart: list[dict]) -> str:
    if not cart:
        return "购物车目前是空的。"

    items = [
        f"{index + 1}. {item['name']} × {item['quantity']}，¥{int(float(item['price']) * int(item['quantity']))}"
        for index, item in enumerate(cart)
    ]
    return "购物车中有：" + "；".join(items) + f"。{build_cart_totals_sentence(cart)}"


def build_cart_totals_sentence(cart: list[dict]) -> str:
    payload = build_cart_payload(cart)
    return f"当前共 {payload['total_quantity']} 件，合计 ¥{int(payload['total_price'])}。"


def select_product_from_candidates(message: str, candidates: list[dict], plan=None) -> dict:
    contextual = select_contextual_product(message, candidates, plan)
    if contextual is not None:
        return contextual

    index = extract_ordinal_index(message, default=0)
    if index < 0 or index >= len(candidates):
        return candidates[0]
    return candidates[index]


def extract_ordinal_index(message: str, default: int) -> int:
    match = re.search(r"第\s*(\d+)\s*(个|件|款)?", message)
    if match:
        return int(match.group(1)) - 1

    for word, index in CHINESE_ORDINALS.items():
        if f"第{word}" in message:
            return index
    return default


def extract_quantity(message: str) -> int | None:
    patterns = [
        r"(?:数量|改成|改为|设为)\s*(\d+)",
        r"(\d+)\s*(件|个|份|台|瓶|支)",
    ]
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return int(match.group(1))

    for word, quantity in CHINESE_NUMBERS.items():
        if f"{word}件" in message or f"{word}个" in message:
            return quantity
    return None


CHINESE_ORDINALS = {
    "一": 0,
    "二": 1,
    "两": 1,
    "三": 2,
    "四": 3,
    "五": 4,
}

CHINESE_NUMBERS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
}
