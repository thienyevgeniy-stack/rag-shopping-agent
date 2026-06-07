from pathlib import Path

from server.rag.post_process import SearchFilters
from server.rag.vector_store import LocalJsonVectorStore
from server.tools.product_search import ProductSearchTool, to_product_card


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


def test_product_search_filters_sports_shoes_without_sports_pants() -> None:
    tool = make_tool()

    cards = tool.run(
        query="推荐一款运动鞋",
        filters=SearchFilters(product_types=["clothes.sports_shoes"]),
        top_k=5,
    )

    assert cards
    assert all("鞋" in card["name"] for card in cards)
    assert not any("裤" in card["name"] for card in cards)
    assert all("clothes.sports_shoes" in card["product_types"] for card in cards)


def test_product_search_handles_compound_sports_shoe_expression() -> None:
    tool = make_tool()

    cards = tool.run(
        query="推荐一款适合跑步的鞋",
        filters=SearchFilters(product_types=["clothes.sports_shoes"]),
        top_k=5,
    )

    assert cards
    assert all("clothes.sports_shoes" in card["product_types"] for card in cards)
    assert not any("裤" in card["name"] for card in cards)


def test_product_type_filters_are_or_within_same_facet() -> None:
    tool = make_tool()

    cards = tool.run(
        query="推荐运动鞋或运动裤",
        filters=SearchFilters(product_types=["clothes.sports_shoes", "clothes.sports_pants"]),
        top_k=10,
    )
    returned_types = {product_type for card in cards for product_type in card["product_types"]}

    assert cards
    assert "clothes.sports_shoes" in returned_types
    assert "clothes.sports_pants" in returned_types
    assert all(
        set(card["product_types"]) & {"clothes.sports_shoes", "clothes.sports_pants"}
        for card in cards
    )


def test_product_card_enriches_product_type_from_legacy_metadata() -> None:
    card = to_product_card(
        {
            "metadata": {
                "id": "legacy_shoe",
                "name": "缓震跑步鞋",
                "category": "服饰运动",
                "sub_category": "运动鞋",
                "brand": "Demo",
                "price": 399,
                "image_url": "",
                "detail_url": "",
                "tags": ["跑鞋"],
                "description": "",
            }
        },
        query="推荐一款运动鞋",
    )

    assert card["product_types"] == ["clothes.sports_shoes"]
    assert card["product_type_names"] == ["运动鞋"]
