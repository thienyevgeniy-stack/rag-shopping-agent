from typing import Any

from server.agent.semantic_schema import SemanticPlan
from server.session.state import SessionState, product_type_values


def update_session_slot_state(session: SessionState, plan: SemanticPlan) -> None:
    """Persist filled slots under the active product scope.

    The planner extracts slots from the current turn, but dialogue policies need
    them across turns. We keep them keyed by canonical product_type so a phone
    budget or use case cannot leak into a later shoes/skincare request.
    """

    scopes = resolve_product_type_scopes(session=session, plan=plan)
    if not scopes:
        return

    for product_type in scopes:
        session.remember_filled_slots(product_type, plan.filled_slots)

    clear_completed_pending_clarification(session)


def resolve_product_type_scopes(session: SessionState, plan: SemanticPlan | None = None) -> list[str]:
    values: list[str] = []
    if plan is not None:
        values.extend(product_type_values_from_filled_slots(plan.filled_slots))
        values.extend(item.value for item in plan.filters if item.kind == "product_type" and item.value)
        values.extend(
            item.value
            for item in plan.constraints
            if item.field == "product_type" and item.mode == "must" and item.value
        )

    if not values:
        values.extend(product_type_values(session.filters))

    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def product_type_values_from_filled_slots(slots: dict[str, Any]) -> list[str]:
    product_type = slots.get("product_type")
    if isinstance(product_type, dict):
        if isinstance(product_type.get("value"), str) and product_type.get("value"):
            return [str(product_type["value"])]
        values = product_type.get("values")
        if isinstance(values, list):
            return [str(item) for item in values if str(item).strip()]
    if isinstance(product_type, str) and product_type.strip():
        return [product_type.strip()]
    return []


def clear_completed_pending_clarification(session: SessionState) -> None:
    pending = session.pending_clarification
    if not pending:
        return

    product_type = str(pending.get("product_type", ""))
    if not product_type:
        return

    requested_slots = [
        str(item)
        for item in pending.get("requested_slots", [])
        if str(item).strip()
    ]
    if not requested_slots:
        return

    slots = session.filled_slots_for_scope(product_type)
    if all(requested_slot_is_filled(slots, slot) for slot in requested_slots):
        session.clear_pending_clarification()


def requested_slot_is_filled(slots: dict[str, Any], slot: str) -> bool:
    if slot_value_is_filled(slots.get(slot)):
        return True
    if slot == "use_case":
        return slot_value_is_filled(slots.get("preference"))
    return False


def slot_value_is_filled(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True
