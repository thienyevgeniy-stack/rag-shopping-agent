from collections.abc import AsyncIterator
from functools import lru_cache
import time

from server.agent.context import extract_contextual_filters
from server.agent.filters import extract_filters
from server.agent.handlers import AgentTurnContext, AgentWorkflow, build_default_workflow
from server.agent.query_rewriter import rewrite_query
from server.agent.scenarios import load_scenario_catalog
from server.agent.semantic import SemanticPlanner
from server.agent.tracing import InMemoryTraceStore, build_trace
from server.config import get_settings
from server.inputs.processors import MultimodalInputProcessor, TextProcessor
from server.inputs.visual_embedding import ProductVisualEmbeddingIndex
from server.llm.ark_client import ArkChatClient, LLMClient
from server.rag.embedding_cache import EmbeddingCache
from server.rag.post_process import SearchFilters
from server.rag.vector_store import (
    ArkMultimodalEmbeddingFunction,
    ChromaStore,
    LocalJsonVectorStore,
    build_chroma_embedding_function,
    load_product_documents,
)
from server.session.state import PersistentSessionStore, RedisSessionStore, SQLiteSessionStore, SessionStore
from server.tools.cart import CartTool
from server.tools.product_compare import ProductCompareTool
from server.tools.product_search import ProductSearchTool
from server.tools.registry import ToolRegistry


class Orchestrator:
    def __init__(
        self,
        registry: ToolRegistry,
        sessions: PersistentSessionStore,
        llm_client: LLMClient | None = None,
        workflow: AgentWorkflow | None = None,
        semantic_planner: SemanticPlanner | None = None,
        trace_store: InMemoryTraceStore | None = None,
        input_processor: TextProcessor | MultimodalInputProcessor | None = None,
    ) -> None:
        self.registry = registry
        self.sessions = sessions
        self.llm_client = llm_client
        self.workflow = workflow or build_default_workflow()
        self.semantic_planner = semantic_planner or SemanticPlanner()
        self.trace_store = trace_store or InMemoryTraceStore()
        self.input_processor = input_processor or TextProcessor()

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
        session = self.sessions.get(session_id)
        try:
            session.add_user_message(user_message)

            emitted: list[dict] = []
            status_event = {
                "event": "status",
                "data": {"state": "thinking", "text": "正在思考"},
            }
            emitted.append(status_event)
            yield status_event

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
            session.merge_filters(extracted)

            intent = plan.to_user_intent()
            query = plan.query or rewrite_query(processed.text, session)
            filters = SearchFilters.from_session(session)

            context = AgentTurnContext(
                session_id=session_id,
                message=processed.text,
                intent=intent,
                query=query,
                filters=filters,
                plan=plan,
                session=session,
                registry=self.registry,
                llm_client=self.llm_client,
            )

            async for item in self.workflow.stream(context):
                emitted.append(item)
                yield item

            self.trace_store.add(
                build_trace(
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
            self.sessions.save(session)


@lru_cache
def get_orchestrator() -> Orchestrator:
    settings = get_settings()
    store = create_store(settings)
    llm_client = create_llm_client(settings)
    registry = ToolRegistry()
    search_tool = ProductSearchTool(store, public_base_url=settings.public_base_url)
    registry.register(search_tool)
    registry.register(ProductCompareTool(search_tool))
    registry.register(CartTool())
    semantic_client = llm_client if settings.use_semantic_llm else None
    scenario_catalog = load_scenario_catalog(str(settings.scenario_bundle_file))
    return Orchestrator(
        registry=registry,
        sessions=create_session_store(settings),
        llm_client=llm_client,
        workflow=build_default_workflow(scenario_catalog),
        semantic_planner=SemanticPlanner(semantic_client),
        trace_store=InMemoryTraceStore(max_items=settings.trace_max_items),
        input_processor=create_input_processor(settings),
    )


def create_session_store(settings) -> PersistentSessionStore:
    backend = settings.normalized_session_backend
    if backend in {"memory", "inmemory", "in-memory"}:
        return SessionStore(
            max_items=settings.session_max_items,
            ttl_seconds=settings.session_ttl_seconds,
        )
    if backend in {"sqlite", "sqlite3", "db"}:
        return SQLiteSessionStore(
            settings.session_db_file,
            max_items=settings.session_max_items,
            ttl_seconds=settings.session_ttl_seconds,
        )
    if backend == "redis":
        return RedisSessionStore(
            settings.session_redis_url,
            max_items=settings.session_max_items,
            ttl_seconds=settings.session_ttl_seconds,
        )
    raise ValueError(f"Unsupported SESSION_BACKEND: {settings.session_backend}")


def create_store(settings):
    if settings.use_chroma:
        try:
            embedding_function, collection_name = build_chroma_embedding_function(
                use_ark_embedding=settings.use_ark_embedding,
                embedding_api=settings.ark_embedding_api,
                api_key=settings.ark_api_key,
                base_url=settings.ark_base_url,
                model=settings.ark_embedding_model,
                timeout_seconds=settings.embedding_timeout_seconds,
                batch_size=settings.embedding_batch_size,
                collection_name=settings.chroma_collection_name,
            )
            if settings.use_ark_embedding and not settings.ark_api_key:
                print("USE_ARK_EMBEDDING=true but ARK_API_KEY is empty; using local hashing embedding.")
            store = ChromaStore(
                settings.chroma_path,
                collection_name=collection_name,
                embedding_function=embedding_function,
            )
            if store.count() == 0:
                store.add(load_product_documents(settings.product_data_file))
            return store
        except RuntimeError as exc:
            print(f"Chroma unavailable, falling back to local JSON search: {exc}")
    return LocalJsonVectorStore(settings.product_data_file)


def create_llm_client(settings) -> LLMClient | None:
    if not settings.use_llm:
        return None
    if not settings.ark_api_key:
        print("USE_LLM=true but ARK_API_KEY is empty; falling back to template answers.")
        return None
    return ArkChatClient(
        api_key=settings.ark_api_key,
        base_url=settings.ark_base_url,
        model=settings.ark_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )


def create_input_processor(settings) -> MultimodalInputProcessor:
    visual_embedding_index = None
    if settings.use_visual_embedding:
        if not settings.ark_api_key:
            print("USE_VISUAL_EMBEDDING=true but ARK_API_KEY is empty; using signature image fallback.")
        else:
            model = settings.visual_embedding_model_name
            embedder = ArkMultimodalEmbeddingFunction(
                api_key=settings.ark_api_key,
                base_url=settings.ark_base_url,
                model=model,
                timeout_seconds=settings.embedding_timeout_seconds,
                batch_size=1,
            )
            visual_embedding_index = ProductVisualEmbeddingIndex(
                settings.visual_embedding_index_file,
                embedder=embedder,
                cache=EmbeddingCache(settings.embedding_cache_file),
                model=model,
            )
            if not visual_embedding_index.entries:
                print(
                    "Visual embedding index is empty; run scripts/build_visual_embedding_index.py "
                    "or use signature image fallback."
                )

    return MultimodalInputProcessor(
        settings.product_data_file,
        settings.product_image_path,
        visual_embedding_index=visual_embedding_index,
    )
