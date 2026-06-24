from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    app_env: str = "development"
    server_host: str = "127.0.0.1"
    server_port: int = 8000
    enable_debug_api: bool | None = None
    enable_admin_console: bool | None = None
    cors_allowed_origins: str = "http://127.0.0.1:8000,http://localhost:8000"
    cors_allow_credentials: bool = False
    session_backend: str = "sqlite"
    session_db_path: str = "server/runtime/sessions.sqlite3"
    session_redis_url: str = "redis://localhost:6379/0"
    session_ttl_seconds: int = 43200
    session_max_items: int = 500
    trace_max_items: int = 200
    enable_query_feedback_log: bool = True
    query_feedback_log_path: str = "server/runtime/query_failures.jsonl"
    max_concurrent_requests: int = 100
    request_timeout_seconds: float = 30.0
    retrieval_timeout_seconds: float = 5.0

    ark_api_key: str = ""
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_model: str = "ep-20260514111645-lmgt2"
    use_llm: bool = False
    use_semantic_llm: bool = False
    semantic_llm_budget_seconds: float = 0.25
    llm_timeout_seconds: float = 45.0
    llm_max_tokens: int = 256
    llm_retry_attempts: int = 2
    llm_circuit_breaker_failures: int = 3
    llm_circuit_breaker_reset_seconds: float = 30.0
    recommendation_llm_budget_seconds: float = 0.0
    recommendation_llm_async_enabled: bool = False
    recommendation_llm_async_budget_seconds: float = 20.0
    use_ark_embedding: bool = False
    ark_embedding_api: str = "text"
    ark_embedding_model: str = "doubao-embedding-text-240515"
    embedding_timeout_seconds: float = 60.0
    embedding_batch_size: int = 4
    use_scenario_embedding: bool = False
    scenario_embedding_min_similarity: float = 0.72
    scenario_embedding_margin: float = 0.06

    use_chroma: bool = False
    chroma_dir: str = "server/chroma_db"
    chroma_collection_name: str = "products"
    product_data_path: str = "data/products_ref.json"
    product_image_dir: str = "data/product_images"
    use_visual_embedding: bool = False
    visual_embedding_model: str = ""
    visual_embedding_index_path: str = "server/runtime/product_image_vectors.json"
    embedding_cache_path: str = "server/runtime/embedding_cache.sqlite3"
    upload_image_dir: str = "server/runtime/uploads/images"
    upload_image_max_bytes: int = 4_500_000
    upload_image_ttl_seconds: int = 86_400
    scenario_bundle_path: str = "data/scenario_bundles.json"
    clarification_policy_path: str = "data/clarification_policy.json"
    public_base_url: str = "http://127.0.0.1:8000"
    commerce_fact_backend: str = "mock"
    commerce_mock_data_path: str = "data/commerce_mock.json"
    taxonomy_eval_cases_path: str = "server/eval/taxonomy_query_cases.json"

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("enable_debug_api", "enable_admin_console", mode="before")
    @classmethod
    def blank_optional_bool_to_none(cls, value):
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @property
    def product_data_file(self) -> Path:
        path = Path(self.product_data_path)
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def chroma_path(self) -> Path:
        path = Path(self.chroma_dir)
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def session_db_file(self) -> Path:
        path = Path(self.session_db_path)
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def normalized_session_backend(self) -> str:
        return self.session_backend.strip().lower()

    @property
    def product_image_path(self) -> Path:
        path = Path(self.product_image_dir)
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def visual_embedding_model_name(self) -> str:
        return self.visual_embedding_model.strip() or self.ark_embedding_model

    @property
    def visual_embedding_index_file(self) -> Path:
        path = Path(self.visual_embedding_index_path)
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def embedding_cache_file(self) -> Path:
        path = Path(self.embedding_cache_path)
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def upload_image_path(self) -> Path:
        path = Path(self.upload_image_dir)
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def scenario_bundle_file(self) -> Path:
        path = Path(self.scenario_bundle_path)
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def clarification_policy_file(self) -> Path:
        path = Path(self.clarification_policy_path)
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def commerce_mock_data_file(self) -> Path:
        path = Path(self.commerce_mock_data_path)
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def taxonomy_eval_cases_file(self) -> Path:
        path = Path(self.taxonomy_eval_cases_path)
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def query_feedback_log_file(self) -> Path:
        path = Path(self.query_feedback_log_path)
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def normalized_commerce_fact_backend(self) -> str:
        return self.commerce_fact_backend.strip().lower()

    @property
    def debug_api_enabled(self) -> bool:
        if self.enable_debug_api is not None:
            return self.enable_debug_api
        return self.app_env.lower() not in {"prod", "production"}

    @property
    def admin_console_enabled(self) -> bool:
        if self.enable_admin_console is not None:
            return self.enable_admin_console
        return self.app_env.lower() not in {"prod", "production"}

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def cors_credentials_enabled(self) -> bool:
        return self.cors_allow_credentials and "*" not in self.cors_origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
