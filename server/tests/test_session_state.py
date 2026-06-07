from server.session.state import FilterCondition, SessionState


def test_session_resets_product_scoped_filters_when_product_type_changes() -> None:
    session = SessionState(session_id="pytest-session")
    session.merge_filters(
        [
            FilterCondition(kind="product_type", value="beauty.eye_cream"),
            FilterCondition(kind="keyword", value="眼霜"),
            FilterCondition(kind="max_price", value="250"),
            FilterCondition(kind="exclude", value="科颜氏"),
        ]
    )

    session.merge_filters(
        [
            FilterCondition(kind="product_type", value="electronics.phone"),
            FilterCondition(kind="keyword", value="手机"),
        ]
    )

    values = {(item.kind, item.value) for item in session.filters}
    assert values == {("product_type", "electronics.phone"), ("keyword", "手机")}
    assert session.exclusions == []


def test_session_keeps_filters_for_contextual_follow_up_without_new_product_type() -> None:
    session = SessionState(session_id="pytest-session")
    session.merge_filters(
        [
            FilterCondition(kind="product_type", value="beauty.eye_cream"),
            FilterCondition(kind="keyword", value="眼霜"),
        ]
    )

    session.merge_filters([FilterCondition(kind="keyword", value="敏感肌")])

    values = {(item.kind, item.value) for item in session.filters}
    assert ("product_type", "beauty.eye_cream") in values
    assert ("keyword", "眼霜") in values
    assert ("keyword", "敏感肌") in values
