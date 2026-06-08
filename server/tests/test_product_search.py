from pathlib import Path

from server.rag.post_process import SearchFilters
from server.rag.vector_store import LocalJsonVectorStore
from server.tools.product_search import ProductSearchTool, build_reason, to_product_card


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
    assert cards[0]["evidence"]["source"] == "product_catalog"
    assert cards[0]["evidence"]["product_id"] == cards[0]["id"]


def test_product_search_exposes_pipeline_diagnostics() -> None:
    tool = make_tool()

    result = tool.run_with_diagnostics(
        query="推荐一款保湿眼霜",
        filters=SearchFilters(max_price=250, keywords=["保湿", "眼霜"]),
        top_k=3,
    )

    step_names = [step.name for step in result.diagnostics.steps]

    assert result.cards
    assert result.diagnostics.requested_top_k == 3
    assert result.diagnostics.candidate_top_k >= 30
    assert "store_prefilter_recall" in step_names
    assert "dedupe_and_rerank" in step_names
    assert result.diagnostics.applied_filters["keywords"] == ["保湿", "眼霜"]


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


def test_product_reason_uses_complete_catalog_sentences_without_hard_cutoff() -> None:
    reason = build_reason(
        {
            "tags": ["跑步鞋", "缓震"],
            "description": (
                "这双跑步鞋主打缓震反馈和日常训练支撑，适合3-10公里路跑。"
                "核心卖点是工程网布透气，通勤和小区夜跑都比较合适。"
                " 问：这款怎么清洁？ 答：用软刷清洁。"
            ),
        },
        query="推荐一款缓震跑步鞋",
    )

    assert "匹配你提到的跑步鞋、缓震" in reason
    assert reason.endswith("。")
    assert "问：" not in reason
    assert reason != "这双跑步鞋主打缓震反馈和日常训练支撑，适合3-10公里"
