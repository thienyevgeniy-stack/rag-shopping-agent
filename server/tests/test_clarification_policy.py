from server.agent.clarification import get_clarification_subject
from server.agent.semantic_rules import build_rule_plan
from server.agent.slot_state import update_session_slot_state
from server.nlu.clarification_policy import CategoryClarificationPolicy, ClarificationPolicyConfig
from server.session.state import FilterCondition, SessionState


def test_category_slot_policy_detects_missing_phone_slots() -> None:
    policy = CategoryClarificationPolicy.from_file()

    decision = policy.decide("推荐一款手机")

    assert decision is not None
    assert decision.subject == "手机"
    assert decision.product_type == "electronics.phone"
    assert decision.missing_slots == ("budget", "use_case")
    assert decision.requested_slot == "budget"
    assert "预算大概是多少" in decision.question
    assert "拍照、续航、性能还是性价比" in decision.question


def test_category_slot_policy_asks_only_missing_slot() -> None:
    policy = CategoryClarificationPolicy.from_file()

    decision = policy.decide("推荐一款3000元以内的手机")

    assert decision is not None
    assert decision.missing_slots == ("use_case",)
    assert decision.requested_slot == "use_case"
    assert "更看重拍照、续航、性能还是性价比" in decision.question


def test_category_slot_policy_skips_when_required_slots_are_filled() -> None:
    policy = CategoryClarificationPolicy.from_file()

    assert policy.decide("推荐一款拍照好、预算3000以内的手机") is None
    assert policy.decide("推荐一款续航好的手机", filled_slots={"budget": {"value": "4000"}}) is None


def test_category_slot_policy_respects_max_clarifications() -> None:
    policy = CategoryClarificationPolicy.from_file()

    assert (
        policy.decide(
            "推荐一款手机",
            clarification_counts={"electronics.phone": 1},
        )
        is None
    )


def test_category_slot_policy_rejects_invalid_budget_slot() -> None:
    policy = CategoryClarificationPolicy.from_file()

    decision = policy.decide(
        "推荐一款手机",
        filled_slots={"budget": {"filters": [{"kind": "max_price", "value": "0"}]}},
    )

    assert decision is not None
    assert decision.missing_slots == ("budget", "use_case")


def test_category_slot_policy_does_not_affect_unconfigured_categories() -> None:
    policy = CategoryClarificationPolicy.from_file()

    assert policy.decide("推荐一款运动鞋") is None


def test_agent_clarification_uses_session_slots() -> None:
    session = SessionState(session_id="clarify-context")
    session.filters = [
        FilterCondition(kind="product_type", value="electronics.phone"),
        FilterCondition(kind="max_price", value="4000"),
    ]
    plan = build_rule_plan("推荐一款手机", session)

    assert get_clarification_subject("推荐一款手机", session, plan=plan) == "手机"


def test_agent_clarification_stops_after_session_limit() -> None:
    session = SessionState(session_id="clarify-context")
    session.clarification_counts["electronics.phone"] = 1
    plan = build_rule_plan("推荐一款手机", session)

    assert get_clarification_subject("推荐一款手机", session, plan=plan) == ""


def test_session_slot_state_is_scoped_by_product_type() -> None:
    session = SessionState(session_id="slot-scope")

    first_plan = build_rule_plan("推荐一款手机", session)
    session.merge_filters(first_plan.to_filter_conditions(), auto_scope_reset=False)
    update_session_slot_state(session, first_plan)
    session.set_pending_clarification(
        product_type="electronics.phone",
        subject="手机",
        rule_id="phone_preference_probe",
        requested_slots=["budget", "use_case"],
    )

    followup_plan = build_rule_plan("预算3000以内，拍照优先", session)
    session.merge_filters(followup_plan.to_filter_conditions(), auto_scope_reset=False)
    update_session_slot_state(session, followup_plan)

    phone_slots = session.filled_slots_for_scope("electronics.phone")
    assert "budget" in phone_slots
    assert "preference" in phone_slots
    assert session.pending_clarification == {}

    shoes_plan = build_rule_plan("推荐一款运动鞋", session)
    session.reset_product_scope()
    session.merge_filters(shoes_plan.to_filter_conditions(), auto_scope_reset=False)
    update_session_slot_state(session, shoes_plan)

    assert "budget" not in session.filled_slots_for_scope("clothes.sports_shoes")


def test_policy_can_be_replaced_without_code_changes() -> None:
    policy = CategoryClarificationPolicy(
        ClarificationPolicyConfig.model_validate(
            {
                "version": "test",
                "rules": [
                    {
                        "id": "sports_shoes_probe",
                        "product_type": "clothes.sports_shoes",
                        "subject": "运动鞋",
                        "trigger_terms": ["推荐"],
                        "required_slots": ["use_case"],
                        "ask_order": ["use_case"],
                        "allow_default_recommendation": False,
                        "slot_terms": {"use_case": ["跑步"]},
                        "question_templates": {"use_case": "你更看重跑步、通勤还是训练？"},
                    }
                ],
            }
        )
    )

    assert policy.decide("推荐一款运动鞋").subject == "运动鞋"
    assert policy.decide("推荐一款跑步运动鞋") is None
