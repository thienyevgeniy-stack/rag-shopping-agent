import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from typing import Any

import httpx


DEFAULT_CASES = [
    {"name": "eye_cream", "message": "推荐一款保湿眼霜，预算250以内"},
    {"name": "sports_shoes", "message": "推荐一款运动鞋"},
    {"name": "sanya_bundle", "message": "下周去三亚度假，帮我搭配一套从防晒到穿搭的方案"},
    {"name": "phone_clarify", "message": "推荐一款手机"},
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark SSE first-token latency for /chat.")
    parser.add_argument("--url", default="http://127.0.0.1:8000/chat")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--threshold-ms", type=float, default=1000.0)
    parser.add_argument("--wait-done", action="store_true", help="Wait for the full SSE response instead of closing after first token.")
    parser.add_argument("--case-file", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    cases = load_cases(args.case_file) if args.case_file else DEFAULT_CASES
    results = []
    print("case\truns\tp50_first_ms\tp95_first_ms\tavg_first_ms\tmax_first_ms\tpass")
    for case in cases:
        for index in range(args.warmup):
            session_id = f"first-token-warmup-{case['name']}-{index}-{int(time.time() * 1000)}"
            measure_first_token(args.url, session_id, case, stop_after_first=True)

        first_latencies = []
        total_latencies = []
        for index in range(args.runs):
            session_id = f"first-token-{case['name']}-{index}-{int(time.time() * 1000)}"
            metrics = measure_first_token(args.url, session_id, case, stop_after_first=not args.wait_done)
            first_latencies.append(metrics["first_token_ms"])
            total_latencies.append(metrics["total_ms"])

        summary = summarize(first_latencies)
        passed = summary["p95_ms"] <= args.threshold_ms
        results.append(
            {
                "case": case["name"],
                "message": case["message"],
                "runs": args.runs,
                "warmup": args.warmup,
                "threshold_ms": args.threshold_ms,
                "first_token": summary,
                "total": summarize(total_latencies),
                "pass": passed,
            }
        )
        print(
            f"{case['name']}\t{args.runs}\t{summary['p50_ms']:.2f}\t{summary['p95_ms']:.2f}\t"
            f"{summary['avg_ms']:.2f}\t{summary['max_ms']:.2f}\t{passed}"
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "url": args.url,
        "threshold_ms": args.threshold_ms,
        "warmup": args.warmup,
        "results": results,
    }
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        print(f"\nWrote report to {args.output}")

    return 0 if all(item["pass"] for item in results) else 1


def measure_first_token(
    url: str,
    session_id: str,
    case: dict[str, Any],
    stop_after_first: bool,
) -> dict[str, float]:
    payload = {
        "session_id": session_id,
        "message": case["message"],
    }
    if case.get("image_base64"):
        payload["image_base64"] = case["image_base64"]
        payload["image_mime_type"] = case.get("image_mime_type", "")
        payload["image_filename"] = case.get("image_filename", "")

    started = time.perf_counter()
    first_token_ms: float | None = None
    current_event = ""
    with httpx.stream(
        "POST",
        url,
        json=payload,
        timeout=httpx.Timeout(120.0, read=120.0),
        trust_env=False,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            if line.startswith("event: "):
                current_event = line.removeprefix("event: ").strip()
            elif line.startswith("data: ") and current_event == "token" and first_token_ms is None:
                first_token_ms = (time.perf_counter() - started) * 1000
                if stop_after_first:
                    break
            if current_event == "done":
                break

    total_ms = (time.perf_counter() - started) * 1000
    return {
        "first_token_ms": first_token_ms if first_token_ms is not None else total_ms,
        "total_ms": total_ms,
    }


def load_cases(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "p50_ms": percentile(values, 50),
        "p95_ms": percentile(values, 95),
        "avg_ms": statistics.fmean(values),
        "min_ms": min(values),
        "max_ms": max(values),
    }


def percentile(values: list[float], percentile_value: int) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile_value / 100
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


if __name__ == "__main__":
    raise SystemExit(main())
