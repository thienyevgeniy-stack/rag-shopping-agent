from server.agent.pending_clarification import apply_pending_clarification_scope
from server.agent.semantic_schema import SemanticFilter, SemanticPlan
from server.nlu.clarification_policy import CategoryClarificationPolicy, ClarificationPolicyConfig
from server.session.state import SessionState


def test_pending_clarification_answer_inherits_product_scope() -> None:
    session = SessionState(session_id="pending-scope")
    session.set_pending_clarification(
        product_type="electronics.laptop",
        subject="laptop",
        rule_id="laptop_preference_probe",
        requested_slots=["budget", "use_case"],
    )
    plan = SemanticPlan(
        intent="bundle",
        filters=[SemanticFilter(kind="max_price", value="8000")],
        filled_slots={
            "budget": {"value": 8000, "source": "rule"},
            "preference": {"values": ["office", "travel"], "source": "rule"},
        },
    )

    updated = apply_pending_clarification_scope(plan, session)

    assert updated.intent == "recommend"
    assert SemanticFilter(kind="product_type", value="electronics.laptop") in updated.filters
    assert updated.filled_slots["product_type"]["value"] == "electronics.laptop"
    assert updated.route_hints["pending_clarification_answer"]["product_type"] == "electronics.laptop"


def test_pending_clarification_answer_does_not_override_explicit_new_scope() -> None:
    session = SessionState(session_id="pending-scope-switch")
    session.set_pending_clarification(
        product_type="electronics.laptop",
        subject="laptop",
        rule_id="laptop_preference_probe",
        requested_slots=["budget", "use_case"],
    )
    plan = SemanticPlan(
        intent="recommend",
        filters=[SemanticFilter(kind="product_type", value="electronics.tablet")],
        filled_slots={"product_type": {"value": "electronics.tablet", "source": "rule"}},
    )

    updated = apply_pending_clarification_scope(plan, session)

    assert updated is plan
    assert SemanticFilter(kind="product_type", value="electronics.laptop") not in updated.filters


def test_pending_clarification_uses_injected_policy_for_slot_terms() -> None:
    policy = CategoryClarificationPolicy(
        ClarificationPolicyConfig.model_validate(
            {
                "version": "test",
                "rules": [
                    {
                        "id": "custom_probe",
                        "product_type": "demo.custom",
                        "subject": "custom",
                        "required_slots": ["budget", "use_case"],
                        "ask_order": ["budget", "use_case"],
                        "slot_terms": {"use_case": ["roadtrip"]},
                        "slot_validators": {
                            "budget": {"type": "price", "min_value": 1, "max_value": 1000},
                            "use_case": {"type": "non_empty"},
                        },
                    }
                ],
            }
        )
    )
    session = SessionState(session_id="pending-policy-injection")
    session.set_pending_clarification(
        product_type="demo.custom",
        subject="custom",
        rule_id="custom_probe",
        requested_slots=["budget", "use_case"],
    )
    plan = SemanticPlan(
        intent="recommend",
        filters=[SemanticFilter(kind="max_price", value="500")],
        filled_slots={"budget": {"value": 500, "source": "rule"}},
        evidence={"raw_query": "budget 500 roadtrip"},
    )

    updated = apply_pending_clarification_scope(plan, session, policy=policy)

    assert updated.filled_slots["use_case"]["terms"] == ["roadtrip"]
    assert updated.filled_slots["preference"]["slot"] == "use_case"
    assert SemanticFilter(kind="product_type", value="demo.custom") in updated.filters
