import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from server.agent.orchestrator import Orchestrator, get_orchestrator


router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    session_id: str = Field(default="default", min_length=1, max_length=128)
    image_base64: str = Field(default="", max_length=4_500_000)
    image_mime_type: str = Field(default="", max_length=80)
    image_filename: str = Field(default="", max_length=200)


def sse(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("/chat")
async def chat(
    request: ChatRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        async for item in orchestrator.stream_chat(
            session_id=request.session_id,
            user_message=request.message,
            image_base64=request.image_base64,
            image_mime_type=request.image_mime_type,
            image_filename=request.image_filename,
        ):
            yield sse(item["event"], item["data"])

    return StreamingResponse(event_stream(), media_type="text/event-stream")
