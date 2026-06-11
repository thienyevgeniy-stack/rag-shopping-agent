import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("USE_LLM", "false")
os.environ.setdefault("USE_SEMANTIC_LLM", "false")

from server.agent.orchestrator import get_orchestrator


@dataclass
class TurnResult:
    ok: bool
    failures: list[str]
    events: list[dict]
    trace: dict


async def collect_events(session_id: str, message: str) -> list[dict]:
    orchestrator = get_orchestrator()
    return [item async for item in orchestrator.stream_chat(session_id=session_id, user_message=message)]


def token_text(events: list[dict]) -> str:
    return "".join(item["data"]["text"] for item in events if item["event"] == "token")


def latest_trace(session_id: str) -> dict:
    orchestrator = get_orchestrator()
    traces = orchestrator.trace_store.list(session_id=session_id, limit=1)
    return traces[0].model_dump() if traces else {}


async def evaluate_case(case: dict) -> tuple[bool, list[TurnResult]]:
    session_id = f"eval-{case['case_id']}"
    reset_eval_session(session_id)
    results: list[TurnResult] = []
    case_ok = True
    for turn in case["turns"]:
        events = await collect_events(session_id, turn["message"])
        trace = latest_trace(session_id)
        failures = check_expectations(turn.get("expect", {}), events, trace)
        ok = not failures
        case_ok = case_ok and ok
        results.append(TurnResult(ok=ok, failures=failures, events=events, trace=trace))
    return case_ok, results


def reset_eval_session(session_id: str) -> None:
    orchestrator = get_orchestrator()
    if hasattr(orchestrator.sessions, "delete"):
        orchestrator.sessions.delete(session_id)


def check_expectations(expect: dict[str, Any], events: list[dict], trace: dict) -> list[str]:
    failures: list[str] = []
    event_names = [item["event"] for item in events]
    text = token_text(events)
    product_cards = [item["data"] for item in events if item["event"] == "product_card"]

    if expect.get("handler") and trace.get("handler") != expect["handler"]:
        failures.append(f"handler expected {expect['handler']}, got {trace.get('handler')}")

    for event in expect.get("events", []):
        if event not in event_names:
            failures.append(f"missing event {event}")

    for product_id in expect.get("product_ids", []):
        if product_id not in trace.get("product_ids", []) and product_id not in trace.get("comparison_product_ids", []):
            failures.append(f"missing product id {product_id}")

    for needle in expect.get("text_contains", []):
        if needle not in text:
            failures.append(f"missing text {needle}")

    for needle in expect.get("text_not_contains", []):
        if needle in text:
            failures.append(f"unexpected text {needle}")

    if "cart_total_quantity" in expect and trace.get("cart_total_quantity") != expect["cart_total_quantity"]:
        failures.append(
            f"cart_total_quantity expected {expect['cart_total_quantity']}, got {trace.get('cart_total_quantity')}"
        )

    if "needs_clarification" in expect:
        done_events = [item for item in events if item["event"] == "done"]
        actual = done_events[-1]["data"].get("needs_clarification") if done_events else None
        if actual != expect["needs_clarification"]:
            failures.append(f"needs_clarification expected {expect['needs_clarification']}, got {actual}")

    done_data = latest_done_data(events)
    expected_pending = expect.get("pending_clarification", {})
    if expected_pending:
        actual_pending = done_data.get("pending_clarification", {}) if done_data else {}
        for key, expected_value in expected_pending.items():
            actual_value = actual_pending.get(key)
            if isinstance(expected_value, list):
                missing = [item for item in expected_value if item not in (actual_value or [])]
                if missing:
                    failures.append(f"pending_clarification.{key} missing {missing}, actual={actual_value}")
            elif actual_value != expected_value:
                failures.append(f"pending_clarification.{key} expected {expected_value!r}, got {actual_value!r}")

    for slot in expect.get("plan_filled_slots", []):
        if slot not in trace.get("plan", {}).get("filled_slots", {}):
            failures.append(f"plan filled slot missing {slot}")

    expected_scope_slots = expect.get("scope_filled_slots", {})
    if expected_scope_slots:
        actual_scope_slots = (
            trace.get("metadata", {})
            .get("nlu", {})
            .get("filled_slots_by_scope", {})
        )
        for product_type, expected_slots in expected_scope_slots.items():
            actual_slots = actual_scope_slots.get(product_type, {})
            for slot in expected_slots:
                if slot not in actual_slots:
                    failures.append(f"scope {product_type} filled slot missing {slot}")

    actual_filters = trace.get("filters", {})
    expected_filters = expect.get("filters", {})
    for key, values in expected_filters.items():
        actual_values = filter_values(actual_filters.get(key))
        for value in values:
            if value not in actual_values:
                failures.append(f"filter {key} missing {value}")

    forbidden_filters = expect.get("filters_not", {})
    for key, values in forbidden_filters.items():
        actual_values = filter_values(actual_filters.get(key))
        for value in values:
            if value in actual_values:
                failures.append(f"filter {key} unexpectedly contains {value}")

    allowed_card_product_types = set(expect.get("allowed_card_product_types", []))
    if allowed_card_product_types:
        for card in product_cards:
            card_types = set(card.get("product_types", []))
            if not card_types & allowed_card_product_types:
                failures.append(
                    f"product card {card.get('id')} has product_types {sorted(card_types)}, "
                    f"expected one of {sorted(allowed_card_product_types)}"
                )

    card_type_union = {product_type for card in product_cards for product_type in card.get("product_types", [])}
    for product_type in expect.get("required_card_product_types", []):
        if product_type not in card_type_union:
            failures.append(f"missing product card type {product_type}")

    return failures


def latest_done_data(events: list[dict]) -> dict[str, Any]:
    for item in reversed(events):
        if item.get("event") == "done":
            data = item.get("data", {})
            return data if isinstance(data, dict) else {}
    return {}


def filter_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def load_cases(path: Path) -> list[dict]:
    cases = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


async def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the local RAG shopping agent with JSONL cases.")
    parser.add_argument("--cases", default=str(ROOT_DIR / "data" / "eval_queries.jsonl"))
    args = parser.parse_args()

    cases = load_cases(Path(args.cases))
    total_turns = 0
    passed_turns = 0
    failed_cases: list[str] = []

    for case in cases:
        case_ok, results = await evaluate_case(case)
        total_turns += len(results)
        passed_turns += sum(1 for item in results if item.ok)
        status = "PASS" if case_ok else "FAIL"
        print(f"[{status}] {case['case_id']}")
        for index, result in enumerate(results, 1):
            if not result.ok:
                print(f"  turn {index}: " + "; ".join(result.failures))
        if not case_ok:
            failed_cases.append(case["case_id"])

    print(f"\nTurns: {passed_turns}/{total_turns} passed")
    if failed_cases:
        print("Failed cases: " + ", ".join(failed_cases))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
