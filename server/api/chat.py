import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from server.agent.orchestrator import Orchestrator, get_orchestrator
from server.config import Settings, get_settings
from server.inputs.upload_store import ImageUploadStore


router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=1000)
    session_id: str = Field(default="default", min_length=1, max_length=128)
    image_base64: str = Field(default="", max_length=4_500_000)
    image_id: str = Field(default="", max_length=64)
    image_mime_type: str = Field(default="", max_length=80)
    image_filename: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def require_message_or_image(self) -> "ChatRequest":
        if not self.message.strip() and not self.image_base64.strip() and not self.image_id.strip():
            raise ValueError("message or image is required")
        return self


def sse(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("/chat")
async def chat(
    request: ChatRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        image_bytes = b""
        image_mime_type = request.image_mime_type
        image_filename = request.image_filename
        if request.image_id:
            store = ImageUploadStore(
                settings.upload_image_path,
                max_bytes=settings.upload_image_max_bytes,
                ttl_seconds=settings.upload_image_ttl_seconds,
            )
            stored = store.read_bytes(request.image_id)
            if stored is not None:
                image_bytes, metadata = stored
                image_mime_type = metadata.mime_type
                image_filename = metadata.filename

        async for item in orchestrator.stream_chat(
            session_id=request.session_id,
            user_message=request.message,
            image_base64=request.image_base64,
            image_bytes=image_bytes,
            image_mime_type=image_mime_type,
            image_filename=image_filename,
        ):
            yield sse(item["event"], item["data"])

    return StreamingResponse(event_stream(), media_type="text/event-stream")
