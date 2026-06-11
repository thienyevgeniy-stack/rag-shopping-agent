from server.nlu.clarification_policy import (
    CategoryClarificationPolicy,
    ClarificationDecision,
    get_default_clarification_policy,
)
from server.agent.semantic_schema import SemanticPlan
from server.agent.slot_state import resolve_product_type_scopes
from server.session.state import FilterCondition


def build_clarification_question(
    message: str,
    session,
    policy: CategoryClarificationPolicy | None = None,
    plan: SemanticPlan | None = None,
) -> str:
    decision = get_clarification_decision(message, session, policy, plan)
    if decision is None:
        return ""

    session.set_pending_clarification(
        product_type=decision.product_type,
        subject=decision.subject,
        rule_id=decision.rule_id,
        requested_slots=decision.missing_slots,
    )
    session.mark_clarification_asked(decision.product_type)
    return decision.question


def get_clarification_subject(
    message: str,
    session,
    policy: CategoryClarificationPolicy | None = None,
    plan: SemanticPlan | None = None,
) -> str:
    decision = get_clarification_decision(message, session, policy, plan)
    return decision.subject if decision is not None else ""


def get_clarification_decision(
    message: str,
    session,
    policy: CategoryClarificationPolicy | None = None,
    plan: SemanticPlan | None = None,
) -> ClarificationDecision | None:
    policy = policy or get_default_clarification_policy()
    filled_slots = build_effective_filled_slots(session, plan)
    decision = policy.decide(
        message,
        filled_slots=filled_slots,
        confidence_by_field=plan.confidence_by_field if plan is not None else {},
        clarification_counts=session.clarification_counts,
        skipped_product_types=set(session.skipped_clarifications),
    )
    if decision is None:
        return None
    if not decision.missing_slots and has_actionable_context_for_subject(session, decision.subject):
        return None
    return decision


def detect_clarification_subject(message: str) -> str:
    """Compatibility helper for older tests and callers.

    New code should use CategoryClarificationPolicy directly so category-level
    clarification behavior stays configurable and versioned.
    """
    decision = get_default_clarification_policy().decide(message)
    return decision.subject if decision is not None else ""


def has_actionable_context_for_subject(session, subject: str) -> bool:
    actionable_filters = [
        item
        for item in session.filters
        if item.kind != "product_type" and not (item.kind == "keyword" and item.value == subject)
    ]
    return bool(actionable_filters or session.exclusions)


def build_effective_filled_slots(session, plan: SemanticPlan | None = None) -> dict[str, object]:
    slots: dict[str, object] = {}
    for product_type in resolve_product_type_scopes(session=session, plan=plan):
        slots.update(session.filled_slots_for_scope(product_type))
    if plan is not None:
        slots.update(plan.filled_slots)

    session_slots = filled_slots_from_filters(session.filters)
    for key, value in session_slots.items():
        slots.setdefault(key, value)
    if session.exclusions:
        slots.setdefault(
            "exclusions",
            [{"kind": item.kind, "value": item.value} for item in session.exclusions],
        )
    return slots


def filled_slots_from_filters(filters: list[FilterCondition]) -> dict[str, object]:
    slots: dict[str, object] = {}
    price_filters = [item for item in filters if item.kind in {"min_price", "max_price"}]
    if price_filters:
        slots["budget"] = {
            "filters": [{"kind": item.kind, "value": item.value} for item in price_filters],
            "source": "session.filters",
        }

    product_types = [item.value for item in filters if item.kind == "product_type" and item.value]
    if product_types:
        slots["product_type"] = {"values": product_types, "source": "session.filters"}

    categories = [item.value for item in filters if item.kind == "category" and item.value]
    if categories:
        slots["category"] = {"values": categories, "source": "session.filters"}

    brands = [item.value for item in filters if item.kind in {"brand", "preferred_brand"} and item.value]
    if brands:
        slots["brand"] = {"values": brands, "source": "session.filters"}

    if any(item.kind == "in_stock" for item in filters):
        slots["stock"] = {"value": "in_stock", "source": "session.filters"}

    facet_values: dict[str, list[str]] = {}
    for item in filters:
        if item.kind != "facet" or ":" not in item.value:
            continue
        field, value = item.value.split(":", 1)
        facet_values.setdefault(field, []).append(value)
    if facet_values:
        slots["facet"] = facet_values
        for field, values in facet_values.items():
            slots.setdefault(field, {"values": values, "source": "session.filters"})

    return slots
