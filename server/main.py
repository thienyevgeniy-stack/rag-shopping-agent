from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.api.chat import router as chat_router
from server.config import get_settings


settings = get_settings()

app = FastAPI(title="RAG Shopping Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}
