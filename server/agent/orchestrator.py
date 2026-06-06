from collections.abc import AsyncIterator
from functools import lru_cache

from server.agent.context import extract_contextual_filters
from server.agent.filters import extract_filters
from server.agent.handlers import AgentTurnContext, AgentWorkflow, build_default_workflow
from server.agent.query_rewriter import rewrite_query
from server.agent.semantic import SemanticPlanner
from server.config import get_settings
from server.inputs.processors import TextProcessor
from server.llm.ark_client import ArkChatClient, LLMClient
from server.rag.post_process import SearchFilters
from server.rag.vector_store import (
    ChromaStore,
    LocalJsonVectorStore,
    build_chroma_embedding_function,
    load_product_documents,
)
from server.session.state import SessionStore
from server.tools.cart import CartTool
from server.tools.product_compare import ProductCompareTool
from server.tools.product_search import ProductSearchTool
from server.tools.registry import ToolRegistry


class Orchestrator:
    def __init__(
        self,
        registry: ToolRegistry,
        sessions: SessionStore,
        llm_client: LLMClient | None = None,
        workflow: AgentWorkflow | None = None,
        semantic_planner: SemanticPlanner | None = None,
    ) -> None:
        self.registry = registry
        self.sessions = sessions
        self.llm_client = llm_client
        self.workflow = workflow or build_default_workflow()
        self.semantic_planner = semantic_planner or SemanticPlanner()
        self.input_processor = TextProcessor()

    async def stream_chat(
        self,
        session_id: str,
        user_message: str,
    ) -> AsyncIterator[dict]:
        session = self.sessions.get(session_id)
        session.add_user_message(user_message)

        processed = self.input_processor.process(user_message)
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
            yield item


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
    return Orchestrator(
        registry=registry,
        sessions=SessionStore(),
        llm_client=llm_client,
        semantic_planner=SemanticPlanner(semantic_client),
    )


def create_store(settings):
    if settings.use_chroma:
        try:
            embedding_function, collection_name = build_chroma_embedding_function(
                use_ark_embedding=settings.use_ark_embedding,
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
