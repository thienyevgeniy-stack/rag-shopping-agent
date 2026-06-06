from server.session.state import SessionState
from server.tools.cart import CartTool


PRODUCT_CARD = {
    "id": "p_beauty_021",
    "name": "科颜氏牛油果保湿眼霜",
    "category": "美妆护肤",
    "brand": "科颜氏",
    "price": 210.0,
    "image_url": "http://127.0.0.1:8000/assets/products/p_beauty_021_live.jpg",
    "detail_url": "http://127.0.0.1:8000/products/p_beauty_021",
    "reason": "匹配眼霜需求",
}

SECOND_CARD = {
    **PRODUCT_CARD,
    "id": "p_beauty_016",
    "name": "AHC塑颜修护全脸眼霜",
    "brand": "AHC",
    "price": 139.0,
}


def make_session() -> SessionState:
    session = SessionState(session_id="pytest-cart")
    session.candidate_products = [PRODUCT_CARD["id"], SECOND_CARD["id"]]
    session.candidate_product_cards = [PRODUCT_CARD, SECOND_CARD]
    return session


def test_cart_tool_adds_latest_candidate() -> None:
    session = make_session()
    tool = CartTool()

    result = tool.run(message="把刚才那款加到购物车", session=session)

    assert "已将 科颜氏牛油果保湿眼霜 加入购物车" in result["answer"]
    assert result["cart"]["total_quantity"] == 1
    assert result["cart"]["total_price"] == 210.0
    assert result["cart"]["items"][0]["product_id"] == "p_beauty_021"


def test_cart_tool_adds_second_candidate_and_updates_quantity() -> None:
    session = make_session()
    tool = CartTool()

    tool.run(message="把第二个加到购物车", session=session)
    result = tool.run(message="把数量改成2", session=session)

    assert result["cart"]["total_quantity"] == 2
    assert result["cart"]["total_price"] == 278.0
    assert result["cart"]["items"][0]["product_id"] == "p_beauty_016"
    assert result["cart"]["items"][0]["quantity"] == 2


def test_cart_tool_removes_item() -> None:
    session = make_session()
    tool = CartTool()

    tool.run(message="把刚才那款加到购物车", session=session)
    result = tool.run(message="删除第一个", session=session)

    assert "已从购物车删除" in result["answer"]
    assert result["cart"]["is_empty"] is True
