from server.agent.orchestrator import extract_filters


def test_extract_filters_handles_multiple_exclusions() -> None:
    filters = extract_filters("推荐防晒霜，但我不要含酒精的，也不要日系品牌")

    values = [(item.kind, item.value) for item in filters]

    assert ("keyword", "防晒") in values
    assert ("exclude", "酒精") in values
    assert ("exclude", "日系品牌") in values


def test_extract_filters_handles_budget_prefix() -> None:
    filters = extract_filters("拍照优先，预算4000")

    values = [(item.kind, item.value) for item in filters]

    assert ("keyword", "拍照") in values
    assert ("max_price", "4000") in values
