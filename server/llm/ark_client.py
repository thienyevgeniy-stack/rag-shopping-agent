import json
from collections.abc import AsyncIterator
from typing import Protocol

import httpx

from server.llm.prompt import build_grounded_messages


class LLMClient(Protocol):
    async def stream_answer(
        self,
        user_message: str,
        cards: list[dict],
        intent: str,
    ) -> AsyncIterator[str]:
        ...


class ArkChatClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 45.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def stream_answer(
        self,
        user_message: str,
        cards: list[dict],
        intent: str,
    ) -> AsyncIterator[str]:
        messages = build_grounded_messages(user_message=user_message, cards=cards, intent=intent)
        async for token in self.stream_messages(messages):
            yield token

    async def stream_messages(self, messages: list[dict]) -> AsyncIterator[str]:
        if not self.api_key:
            raise RuntimeError("ARK_API_KEY is not configured.")

        timeout = httpx.Timeout(self.timeout_seconds, read=None)
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    token = parse_openai_sse_line(line)
                    if token:
                        yield token


def parse_openai_sse_line(line: str) -> str:
    if not line.startswith("data:"):
        return ""

    data = line.removeprefix("data:").strip()
    if not data or data == "[DONE]":
        return ""

    payload = json.loads(data)
    choices = payload.get("choices") or []
    if not choices:
        return ""

    delta = choices[0].get("delta") or {}
    return delta.get("content") or ""
