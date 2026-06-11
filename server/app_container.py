import logging
from functools import lru_cache

from server.agent.default_handlers import build_default_workflow
from server.agent.orchestrator import Orchestrator
from server.agent.query_feedback import QueryFeedbackStore
from server.agent.scenario_classifier import EmbeddingScenarioClassifier, HybridScenarioClassifier
from server.agent.scenarios import load_scenario_catalog
from server.agent.semantic_llm import SemanticPlanner
from server.agent.tracing import InMemoryTraceStore
from server.commerce.facts import CommerceFactProvider, LocalMockCommerceProvider, configure_fact_provider
from server.config import Settings, get_settings
from server.inputs.multimodal import MultimodalInputProcessor
from server.inputs.visual_embedding import ProductVisualEmbeddingIndex
from server.llm.ark_client import ArkChatClient, LLMClient
from server.nlu.clarification_policy import CategoryClarificationPolicy
from server.rag.embedding_cache import EmbeddingCache
from server.rag.embeddings import ArkEmbeddingFunction
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
from server.commerce.facts import get_commerce_gateway


logger = logging.getLogger(__name__)


@lru_cache
def get_orchestrator() -> Orchestrator:
    settings = get_settings()
    configure_fact_provider(create_commerce_fact_provider(settings))
    commerce_gateway = get_commerce_gateway()
    store = create_store(settings)
    llm_client = create_llm_client(settings)
    registry = ToolRegistry()
    search_tool = ProductSearchTool(
        store,
        public_base_url=settings.public_base_url,
        commerce_gateway=commerce_gateway,
    )
    registry.register(search_tool)
    registry.register(ProductCompareTool(search_tool))
    registry.register(CartTool())
    semantic_client = llm_client if settings.use_semantic_llm else None
    scenario_catalog = create_scenario_catalog(settings)
    clarification_policy = create_clarification_policy(settings)
    return Orchestrator(
        registry=registry,
        sessions=create_session_store(settings),
        llm_client=llm_client,
        workflow=build_default_workflow(scenario_catalog, clarification_policy),
        clarification_policy=clarification_policy,
        semantic_planner=SemanticPlanner(
            semantic_client,
            timeout_seconds=settings.semantic_llm_budget_seconds,
        ),
        trace_store=InMemoryTraceStore(max_items=settings.trace_max_items),
        query_feedback_store=create_query_feedback_store(settings),
        input_processor=create_input_processor(settings),
        recommendation_llm_budget_seconds=settings.recommendation_llm_budget_seconds,
        retrieval_timeout_seconds=settings.retrieval_timeout_seconds,
    )


def create_query_feedback_store(settings: Settings) -> QueryFeedbackStore | None:
    if not settings.enable_query_feedback_log:
        return None
    return QueryFeedbackStore(settings.query_feedback_log_file, enabled=True)


def create_scenario_catalog(settings: Settings):
    classifier = create_scenario_classifier(settings)
    return load_scenario_catalog(str(settings.scenario_bundle_file), classifier=classifier)


def create_clarification_policy(settings: Settings) -> CategoryClarificationPolicy:
    return CategoryClarificationPolicy.from_file(settings.clarification_policy_file)


def create_scenario_classifier(settings: Settings) -> HybridScenarioClassifier:
    if not settings.use_scenario_embedding:
        return HybridScenarioClassifier()
    if not settings.ark_api_key:
        logger.warning("USE_SCENARIO_EMBEDDING=true but ARK_API_KEY is empty; using rule scenario routing only.")
        return HybridScenarioClassifier()
    embedder = ArkEmbeddingFunction(
        api_key=settings.ark_api_key,
        base_url=settings.ark_base_url,
        model=settings.ark_embedding_model,
        timeout_seconds=settings.embedding_timeout_seconds,
        batch_size=min(max(1, settings.embedding_batch_size), 32),
    )
    return HybridScenarioClassifier(
        embedding_classifier=EmbeddingScenarioClassifier(
            embedder,
            min_similarity=settings.scenario_embedding_min_similarity,
            margin=settings.scenario_embedding_margin,
        )
    )


def create_commerce_fact_provider(settings: Settings) -> CommerceFactProvider:
    backend = settings.normalized_commerce_fact_backend
    if backend in {"mock", "local_mock", "local"}:
        return LocalMockCommerceProvider(settings.commerce_mock_data_file)
    raise ValueError(f"Unsupported COMMERCE_FACT_BACKEND: {settings.commerce_fact_backend}")


def create_session_store(settings: Settings) -> PersistentSessionStore:
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


def create_store(settings: Settings):
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
                logger.warning("USE_ARK_EMBEDDING=true but ARK_API_KEY is empty; using local hashing embedding.")
            store = ChromaStore(
                settings.chroma_path,
                collection_name=collection_name,
                embedding_function=embedding_function,
            )
            if store.count() == 0:
                store.add(load_product_documents(settings.product_data_file))
            return store
        except RuntimeError as exc:
            logger.warning("Chroma unavailable, falling back to local JSON search: %s", exc)
    return LocalJsonVectorStore(settings.product_data_file)


def create_llm_client(settings: Settings) -> LLMClient | None:
    if not settings.use_llm:
        return None
    if not settings.ark_api_key:
        logger.warning("USE_LLM=true but ARK_API_KEY is empty; falling back to template answers.")
        return None
    return ArkChatClient(
        api_key=settings.ark_api_key,
        base_url=settings.ark_base_url,
        model=settings.ark_model,
        timeout_seconds=settings.llm_timeout_seconds,
        retry_attempts=settings.llm_retry_attempts,
        circuit_breaker_failures=settings.llm_circuit_breaker_failures,
        circuit_breaker_reset_seconds=settings.llm_circuit_breaker_reset_seconds,
    )


def create_input_processor(settings: Settings) -> MultimodalInputProcessor:
    visual_embedding_index = None
    if settings.use_visual_embedding:
        if not settings.ark_api_key:
            logger.warning("USE_VISUAL_EMBEDDING=true but ARK_API_KEY is empty; using signature image fallback.")
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
                logger.warning(
                    "Visual embedding index is empty; run scripts/build_visual_embedding_index.py "
                    "or use signature image fallback."
                )

    return MultimodalInputProcessor(
        settings.product_data_file,
        settings.product_image_path,
        visual_embedding_index=visual_embedding_index,
    )
