import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError, model_validator

from server.agent.orchestrator import Orchestrator
from server.app_container import get_orchestrator
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
        image_bytes, image_mime_type, image_filename = resolve_image_payload(request, settings)

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


@router.websocket("/ws/chat")
async def chat_websocket(
    websocket: WebSocket,
    orchestrator: Orchestrator = Depends(get_orchestrator),
    settings: Settings = Depends(get_settings),
) -> None:
    await websocket.accept()
    try:
        while True:
            payload = await websocket.receive_json()
            try:
                request = ChatRequest.model_validate(payload)
            except ValidationError as exc:
                await websocket.send_json(
                    {
                        "event": "error",
                        "data": {
                            "code": "invalid_request",
                            "message": "请求参数不完整或格式不正确。",
                            "details": exc.errors(),
                        },
                    }
                )
                continue

            image_bytes, image_mime_type, image_filename = resolve_image_payload(request, settings)
            async for item in orchestrator.stream_chat(
                session_id=request.session_id,
                user_message=request.message,
                image_base64=request.image_base64,
                image_bytes=image_bytes,
                image_mime_type=image_mime_type,
                image_filename=image_filename,
            ):
                await websocket.send_json(item)
    except WebSocketDisconnect:
        return


def resolve_image_payload(request: ChatRequest, settings: Settings) -> tuple[bytes, str, str]:
    image_bytes = b""
    image_mime_type = request.image_mime_type
    image_filename = request.image_filename
    if not request.image_id:
        return image_bytes, image_mime_type, image_filename

    store = ImageUploadStore(
        settings.upload_image_path,
        max_bytes=settings.upload_image_max_bytes,
        ttl_seconds=settings.upload_image_ttl_seconds,
    )
    stored = store.read_bytes(request.image_id, session_id=request.session_id)
    if stored is None:
        return image_bytes, image_mime_type, image_filename

    image_bytes, metadata = stored
    return image_bytes, metadata.mime_type, metadata.filename
