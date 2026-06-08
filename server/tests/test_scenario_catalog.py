import json
from pathlib import Path

from server.agent.scenarios import ScenarioCatalog, detect_scenario_bundle, render_query_template
from server.rag.post_process import SearchFilters


def test_default_scenario_catalog_loads_from_data_file() -> None:
    bundle = detect_scenario_bundle("下周去三亚度假，帮我搭配一套")

    assert bundle is not None
    assert bundle.id == "sanya_trip"
    assert bundle.source_version == "2026-06-08"
    assert bundle.matched_terms
    assert [slot.label for slot in bundle.slots][:2] == ["防晒保护", "轻便上衣"]


def test_scenario_catalog_can_be_extended_without_python_branching(tmp_path: Path) -> None:
    config_path = tmp_path / "scenario_bundles.json"
    config_path.write_text(
        json.dumps(
            {
                "version": "test",
                "bundles": [
                    {
                        "id": "camping",
                        "priority": 10,
                        "trigger_terms": ["露营"],
                        "title": "露营组合方案",
                        "summary": "按户外补给和轻便装备搭配。",
                        "slots": [
                            {
                                "label": "户外装备",
                                "query_template": "{message} 户外 轻便",
                                "filters": {"keywords": ["轻便"]},
                                "max_items": 2,
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    catalog = ScenarioCatalog.from_file(config_path)
    bundle = catalog.detect("周末想去露营")

    assert bundle is not None
    assert bundle.id == "camping"
    assert bundle.slots[0].query == "周末想去露营 户外 轻便"
    assert bundle.slots[0].filters.keywords == ["轻便"]
    assert bundle.slots[0].max_items == 2


def test_scenario_catalog_routes_by_semantic_terms_not_only_triggers() -> None:
    bundle = detect_scenario_bundle("我要去海岛玩一周，主要需要防晒和旅行穿搭")

    assert bundle is not None
    assert bundle.id == "sanya_trip"
    assert "semantic" in ",".join(bundle.match_signals)


def test_scenario_catalog_drops_optional_slot_when_budget_is_too_low() -> None:
    bundle = detect_scenario_bundle(
        "去海岛玩，预算1000以内，帮我配一套",
        filters=SearchFilters(max_price=1000),
    )

    assert bundle is not None
    assert bundle.id == "sanya_trip"
    assert "拍照记录" not in [slot.label for slot in bundle.slots]


def test_scenario_catalog_respects_strategy_status_and_rollout(tmp_path: Path) -> None:
    config_path = tmp_path / "scenario_bundles.json"
    config_path.write_text(
        json.dumps(
            {
                "version": "test",
                "bundles": [
                    {
                        "id": "disabled",
                        "status": "disabled",
                        "rollout_percentage": 100,
                        "priority": 100,
                        "trigger_terms": ["露营"],
                        "title": "露营",
                        "summary": "disabled",
                        "slots": [{"label": "装备", "query_template": "露营", "filters": {}}],
                    },
                    {
                        "id": "zero_rollout",
                        "status": "active",
                        "rollout_percentage": 0,
                        "priority": 90,
                        "trigger_terms": ["露营"],
                        "title": "露营",
                        "summary": "zero",
                        "slots": [{"label": "装备", "query_template": "露营", "filters": {}}],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    catalog = ScenarioCatalog.from_file(config_path)

    assert catalog.detect("周末露营") is None


def test_query_template_only_substitutes_message_placeholder() -> None:
    assert render_query_template("{message} 手机 耳机", "通勤一套") == "通勤一套 手机 耳机"
