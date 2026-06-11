from typing import Any

from server.agent.semantic_schema import SemanticFilter, SemanticPlan
from server.agent.slot_state import requested_slot_is_filled
from server.nlu.clarification_policy import CategoryClarificationPolicy, get_default_clarification_policy
from server.session.state import SessionState


PRODUCT_SCOPE_FILTER_KINDS = {"product_type", "category"}
PRODUCT_SCOPE_CONSTRAINT_FIELDS = {"product_type", "category"}
CONTEXT_BOUND_INTENTS = {"cart", "compare", "ask_product_detail", "clarify"}
REFINEMENT_FILTER_KINDS = {
    "max_price",
    "min_price",
    "brand",
    "preferred_brand",
    "exclude_brand",
    "keyword",
    "should_keyword",
    "facet",
    "in_stock",
}


def apply_pending_clarification_scope(
    plan: SemanticPlan,
    session: SessionState,
    *,
    policy: CategoryClarificationPolicy | None = None,
) -> SemanticPlan:
    """Bind a clarification answer back to the product scope that asked it.

    A follow-up like "budget 8000, mainly office and travel" can contain
    scenario terms. If the previous turn asked a laptop clarification, those
    terms should fill the laptop slots instead of starting a commute bundle.
    """

    pending = session.pending_clarification
    product_type = str(pending.get("product_type", "")).strip()
    if not product_type:
        return plan
    if plan.intent in CONTEXT_BOUND_INTENTS:
        return plan
    if _has_explicit_product_scope(plan):
        return plan
    if not _looks_like_pending_clarification_answer(plan, pending):
        return plan

    filters = list(plan.filters)
    filters.append(SemanticFilter(kind="product_type", value=product_type))

    policy = policy or get_default_clarification_policy()
    filled_slots = _collect_pending_slot_answers(product_type, plan, policy)
    filled_slots.setdefault(
        "product_type",
        {
            "value": product_type,
            "source": "pending_clarification",
        },
    )

    confidence_by_field = dict(plan.confidence_by_field)
    confidence_by_field.setdefault("product_type", 0.86)

    route_hints = dict(plan.route_hints)
    route_hints["pending_clarification_answer"] = {
        "product_type": product_type,
        "rule_id": str(pending.get("rule_id", "")),
        "requested_slots": [
            str(item)
            for item in pending.get("requested_slots", [])
            if str(item).strip()
        ],
    }

    return plan.model_copy(
        update={
            "intent": "recommend" if plan.intent in {"bundle", "browse"} else plan.intent,
            "filters": _dedupe_semantic_filters(filters),
            "filled_slots": filled_slots,
            "confidence_by_field": confidence_by_field,
            "route_hints": route_hints,
            "needs_search": True,
        }
    )


def _has_explicit_product_scope(plan: SemanticPlan) -> bool:
    if any(item.kind in PRODUCT_SCOPE_FILTER_KINDS and item.value.strip() for item in plan.filters):
        return True
    if any(
        item.field in PRODUCT_SCOPE_CONSTRAINT_FIELDS
        and item.mode == "must"
        and item.value.strip()
        for item in plan.constraints
    ):
        return True

    product_type = plan.filled_slots.get("product_type")
    if isinstance(product_type, str) and product_type.strip():
        return True
    if isinstance(product_type, dict):
        value = product_type.get("value")
        values = product_type.get("values")
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(values, list) and any(str(item).strip() for item in values):
            return True
    return False


def _looks_like_pending_clarification_answer(plan: SemanticPlan, pending: dict[str, Any]) -> bool:
    requested_slots = [
        str(item)
        for item in pending.get("requested_slots", [])
        if str(item).strip()
    ]
    if requested_slots and any(requested_slot_is_filled(plan.filled_slots, slot) for slot in requested_slots):
        return True

    return any(item.kind in REFINEMENT_FILTER_KINDS and item.value.strip() for item in plan.filters)


def _collect_pending_slot_answers(
    product_type: str,
    plan: SemanticPlan,
    policy: CategoryClarificationPolicy,
) -> dict[str, Any]:
    raw_query = str(plan.evidence.get("raw_query", "")).strip() or plan.query
    filled_slots = policy.collect_filled_slots(
        product_type,
        raw_query,
        filled_slots=dict(plan.filled_slots),
    )
    use_case = filled_slots.get("use_case")
    if use_case and "preference" not in filled_slots:
        filled_slots["preference"] = {
            "source": "clarification_policy.use_case",
            "slot": "use_case",
            "value": use_case,
        }
    return filled_slots


def _dedupe_semantic_filters(filters: list[SemanticFilter]) -> list[SemanticFilter]:
    seen: set[tuple[str, str]] = set()
    result: list[SemanticFilter] = []
    for item in filters:
        key = (item.kind, item.value.strip())
        if not key[1] or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
