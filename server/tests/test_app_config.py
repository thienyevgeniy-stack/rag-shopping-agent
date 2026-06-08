from fastapi.middleware.cors import CORSMiddleware

from server.agent.orchestrator import create_session_store
from server.config import Settings
from server.main import create_app
from server.session.state import RedisSessionStore, SQLiteSessionStore, SessionStore


def test_production_settings_disable_debug_api_by_default() -> None:
    settings = Settings(_env_file=None, app_env="production", enable_debug_api=None)

    assert settings.debug_api_enabled is False


def test_create_app_omits_debug_routes_in_production() -> None:
    app = create_app(Settings(_env_file=None, app_env="production", enable_debug_api=None))

    paths = {route.path for route in app.routes}

    assert "/chat" in paths
    assert "/debug/traces" not in paths
    assert "/debug/traces/{trace_id}" not in paths


def test_create_app_uses_configured_cors_options() -> None:
    settings = Settings(
        _env_file=None,
        cors_allowed_origins="https://shop.example.com,http://localhost:5173",
        cors_allow_credentials=True,
    )

    app = create_app(settings)
    cors_middleware = next(item for item in app.user_middleware if item.cls is CORSMiddleware)

    assert cors_middleware.kwargs["allow_origins"] == [
        "https://shop.example.com",
        "http://localhost:5173",
    ]
    assert cors_middleware.kwargs["allow_credentials"] is True


def test_wildcard_cors_disables_credentials_even_if_requested() -> None:
    settings = Settings(
        _env_file=None,
        cors_allowed_origins="*",
        cors_allow_credentials=True,
    )

    app = create_app(settings)
    cors_middleware = next(item for item in app.user_middleware if item.cls is CORSMiddleware)

    assert cors_middleware.kwargs["allow_origins"] == ["*"]
    assert cors_middleware.kwargs["allow_credentials"] is False


def test_create_session_store_uses_memory_backend_by_default() -> None:
    settings = Settings(_env_file=None)

    store = create_session_store(settings)

    assert isinstance(store, SessionStore)


def test_create_session_store_uses_sqlite_backend(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        session_backend="sqlite",
        session_db_path=str(tmp_path / "sessions.sqlite3"),
    )

    store = create_session_store(settings)

    assert isinstance(store, SQLiteSessionStore)


def test_create_session_store_uses_redis_backend(monkeypatch) -> None:
    class FakeRedisSessionStore:
        def __init__(self, redis_url, *, max_items, ttl_seconds) -> None:
            self.redis_url = redis_url
            self.max_items = max_items
            self.ttl_seconds = ttl_seconds

    monkeypatch.setattr("server.agent.orchestrator.RedisSessionStore", FakeRedisSessionStore)
    settings = Settings(
        _env_file=None,
        session_backend="redis",
        session_redis_url="redis://redis.example:6379/1",
    )

    store = create_session_store(settings)

    assert isinstance(store, FakeRedisSessionStore)
    assert store.redis_url == "redis://redis.example:6379/1"
