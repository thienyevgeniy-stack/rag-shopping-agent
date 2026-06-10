from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from server.agent.intent import UserIntent
from server.agent.semantic_schema import SemanticPlan
from server.llm.ark_client import LLMClient
from server.rag.post_process import SearchFilters
from server.session.state import SessionState
from server.tools.registry import ToolRegistry


@dataclass
class AgentTurnContext:
    trace_id: str
    session_id: str
    message: str
    intent: UserIntent
    query: str
    filters: SearchFilters
    plan: SemanticPlan
    session: SessionState
    registry: ToolRegistry
    llm_client: LLMClient | None
    recommendation_llm_budget_seconds: float = 0.0
    retrieval_timeout_seconds: float = 5.0
    selected_handler: str = ""
    scenario_match: object | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class AgentHandler(Protocol):
    def matches(self, context: AgentTurnContext) -> bool:
        ...

    async def handle(self, context: AgentTurnContext) -> AsyncIterator[dict]:
        ...


class AgentWorkflow:
    def __init__(self, handlers: Sequence[AgentHandler]) -> None:
        self.handlers = list(handlers)

    async def stream(self, context: AgentTurnContext) -> AsyncIterator[dict]:
        for handler in self.handlers:
            if handler.matches(context):
                context.selected_handler = handler.__class__.__name__
                async for item in handler.handle(context):
                    yield item
                return
        raise RuntimeError("No agent handler matched the turn.")
