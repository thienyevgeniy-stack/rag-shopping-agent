from collections.abc import AsyncIterator
import time
from uuid import uuid4

from server.agent.context import extract_contextual_filters
from server.agent.filters import extract_filters
from server.agent.default_handlers import build_default_workflow
from server.agent.workflow import AgentTurnContext, AgentWorkflow
from server.agent.query_rewriter import rewrite_query
from server.agent.query_feedback import QueryFeedbackStore, build_query_feedback_event
from server.agent.semantic_llm import SemanticPlanner
from server.agent.slot_state import update_session_slot_state
from server.agent.scope_transition import ScopeTransitionPolicy
from server.agent.tracing import InMemoryTraceStore, build_trace
from server.inputs.base import TextProcessor
from server.inputs.multimodal import MultimodalInputProcessor
from server.llm.ark_client import LLMClient
from server.rag.post_process import SearchFilters
from server.session.memory import refresh_session_memory
from server.session.state import PersistentSessionStore
from server.tools.registry import ToolRegistry


class Orchestrator:
    def __init__(
        self,
        registry: ToolRegistry,
        sessions: PersistentSessionStore,
        llm_client: LLMClient | None = None,
        workflow: AgentWorkflow | None = None,
        semantic_planner: SemanticPlanner | None = None,
        scope_transition_policy: ScopeTransitionPolicy | None = None,
        trace_store: InMemoryTraceStore | None = None,
        query_feedback_store: QueryFeedbackStore | None = None,
        input_processor: TextProcessor | MultimodalInputProcessor | None = None,
        recommendation_llm_budget_seconds: float = 0.0,
        retrieval_timeout_seconds: float = 5.0,
    ) -> None:
        self.registry = registry
        self.sessions = sessions
        self.llm_client = llm_client
        self.workflow = workflow or build_default_workflow()
        self.semantic_planner = semantic_planner or SemanticPlanner()
        self.scope_transition_policy = scope_transition_policy or ScopeTransitionPolicy()
        self.trace_store = trace_store or InMemoryTraceStore()
        self.query_feedback_store = query_feedback_store
        self.input_processor = input_processor or TextProcessor()
        self.recommendation_llm_budget_seconds = recommendation_llm_budget_seconds
        self.retrieval_timeout_seconds = max(0.0, retrieval_timeout_seconds)

    async def stream_chat(
        self,
        session_id: str,
        user_message: str,
        image_base64: str = "",
        image_bytes: bytes = b"",
        image_mime_type: str = "",
        image_filename: str = "",
    ) -> AsyncIterator[dict]:
        started_at = time.time()
        trace_id = uuid4().hex
        session = None
        emitted: list[dict] = []
        status_event = {
            "event": "status",
            "data": {"state": "thinking", "text": "正在思考"},
        }
        emitted.append(status_event)
        yield status_event

        session = self.sessions.get(session_id)
        try:
            session.add_user_message(user_message)

            processed = self.input_processor.process(
                user_message,
                image_base64=image_base64,
                image_bytes=image_bytes,
                image_mime_type=image_mime_type,
                image_filename=image_filename,
            )
            if processed.image_summary:
                image_event = {
                    "event": "image_analysis",
                    "data": {
                        "summary": processed.image_summary,
                        "matches": processed.visual_matches,
                    },
                }
                emitted.append(image_event)
                yield image_event
            plan = await self.semantic_planner.plan(processed.text, session)
            extracted = plan.to_filter_conditions()
            extracted.extend(extract_contextual_filters(processed.text, session, plan))
            scope_transition = self.scope_transition_policy.decide(
                processed.text,
                plan,
                session,
                extracted,
            )
            self.scope_transition_policy.apply(session, scope_transition)
            session.merge_filters(extracted, auto_scope_reset=False)
            update_session_slot_state(session, plan)

            intent = plan.to_user_intent()
            query = plan.query or rewrite_query(processed.text, session)
            filters = SearchFilters.from_session(session)

            context = AgentTurnContext(
                trace_id=trace_id,
                session_id=session_id,
                message=processed.text,
                intent=intent,
                query=query,
                filters=filters,
                plan=plan,
                session=session,
                registry=self.registry,
                llm_client=self.llm_client,
                recommendation_llm_budget_seconds=self.recommendation_llm_budget_seconds,
                retrieval_timeout_seconds=self.retrieval_timeout_seconds,
            )
            if plan.query_understanding:
                context.metadata["query_understanding"] = plan.query_understanding
            context.metadata["nlu"] = {
                "confidence_by_field": dict(plan.confidence_by_field),
                "filled_slots": dict(plan.filled_slots),
                "filled_slots_by_scope": dict(session.filled_slots_by_scope),
                "evidence": dict(plan.evidence),
            }
            if session.pending_clarification:
                context.metadata["pending_clarification"] = dict(session.pending_clarification)
            context.metadata["scope_transition"] = scope_transition.as_metadata()

            async for item in self.workflow.stream(context):
                emitted.append(item)
                yield item

            feedback_event = build_query_feedback_event(
                trace_id=trace_id,
                session_id=session_id,
                message=processed.text,
                plan=plan,
                filters=filters,
                events=emitted,
                metadata=context.metadata,
            )
            if feedback_event is not None:
                context.metadata["query_feedback"] = {
                    "recorded": self.query_feedback_store is not None,
                    "reasons": list(feedback_event.reasons),
                }
                if self.query_feedback_store is not None:
                    self.query_feedback_store.record(feedback_event)

            self.trace_store.add(
                build_trace(
                    trace_id=trace_id,
                    session_id=session_id,
                    message=processed.text,
                    handler=context.selected_handler,
                    plan=plan,
                    query=query,
                    filters=filters,
                    events=emitted,
                    started_at=started_at,
                    metadata=context.metadata,
                )
            )
        finally:
            if session is not None:
                refresh_session_memory(session)
                self.sessions.save(session)


def get_orchestrator() -> Orchestrator:
    from server.app_container import get_orchestrator as get_app_orchestrator

    return get_app_orchestrator()


def create_session_store(settings) -> PersistentSessionStore:
    from server.app_container import create_session_store as create_app_session_store

    return create_app_session_store(settings)


def create_store(settings):
    from server.app_container import create_store as create_app_store

    return create_app_store(settings)


def create_llm_client(settings) -> LLMClient | None:
    from server.app_container import create_llm_client as create_app_llm_client

    return create_app_llm_client(settings)


def create_input_processor(settings) -> MultimodalInputProcessor:
    from server.app_container import create_input_processor as create_app_input_processor

    return create_app_input_processor(settings)
