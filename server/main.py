from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.api.admin import router as admin_router
from server.api.cart import router as cart_router
from server.api.chat import router as chat_router
from server.api.debug import router as debug_router
from server.api.products import router as products_router
from server.api.sessions import router as sessions_router
from server.api.uploads import router as uploads_router
from server.config import Settings
from server.config import get_settings
from server.app_container import create_commerce_fact_provider, get_orchestrator
from server.commerce.facts import configure_fact_provider
from server.gateway.middleware import RequestGovernanceMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_orchestrator()
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_fact_provider(create_commerce_fact_provider(settings))
    app = FastAPI(title="RAG Shopping Agent", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        RequestGovernanceMiddleware,
        max_concurrent_requests=settings.max_concurrent_requests,
        request_timeout_seconds=settings.request_timeout_seconds,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_credentials_enabled,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(chat_router)
    app.include_router(cart_router)
    app.include_router(products_router)
    app.include_router(sessions_router)
    app.include_router(uploads_router)
    if settings.debug_api_enabled:
        app.include_router(debug_router)
    if settings.admin_console_enabled:
        app.include_router(admin_router)
    settings.product_image_path.mkdir(parents=True, exist_ok=True)
    settings.upload_image_path.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/assets/products",
        StaticFiles(directory=settings.product_image_path, check_dir=False),
        name="product_images",
    )

    @app.get("/health")
    async def health() -> dict[str, str | bool]:
        return {
            "status": "ok",
            "env": settings.app_env,
            "debug_api_enabled": settings.debug_api_enabled,
            "session_backend": settings.normalized_session_backend,
        }

    return app


settings = get_settings()
app = create_app(settings)
