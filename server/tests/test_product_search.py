from pathlib import Path

from server.rag.post_process import SearchFilters
from server.rag.vector_store import LocalJsonVectorStore
from server.tools.product_search import ProductSearchTool


ROOT_DIR = Path(__file__).resolve().parents[2]


def make_tool() -> ProductSearchTool:
    store = LocalJsonVectorStore(ROOT_DIR / "data" / "products_ref.json")
    return ProductSearchTool(store)


def test_product_search_respects_budget_and_keyword() -> None:
    tool = make_tool()

    cards = tool.run(
        query="推荐一款保湿眼霜",
        filters=SearchFilters(max_price=250, keywords=["保湿", "眼霜"]),
        top_k=3,
    )

    assert cards
    assert cards[0]["id"] == "p_beauty_021"
    assert cards[0]["image_url"].endswith("/assets/products/p_beauty_021_live.jpg")
    assert cards[0]["detail_url"].endswith("/products/p_beauty_021")
    assert all(card["price"] <= 250 for card in cards)


def test_product_search_excludes_brand() -> None:
    tool = make_tool()

    cards = tool.run(
        query="推荐敏感肌可以用的卸妆油，不要芳珂",
        filters=SearchFilters(max_price=300, keywords=["敏感肌", "卸妆油"], exclusions=["芳珂"]),
        top_k=5,
    )

    assert all(card["brand"] != "芳珂" for card in cards)


def test_product_search_does_not_relax_required_keywords_to_unrelated_items() -> None:
    tool = make_tool()

    cards = tool.run(
        query="预算500以内 跑鞋 轻量",
        filters=SearchFilters(max_price=500, keywords=["跑鞋", "轻量"]),
        top_k=5,
    )

    assert cards == []
