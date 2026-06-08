from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from server.config import Settings, get_settings
from server.inputs.upload_store import ImageUploadStore


router = APIRouter(prefix="/uploads", tags=["uploads"])


class ImageUploadResponse(BaseModel):
    image_id: str
    filename: str
    mime_type: str
    size_bytes: int


@router.post("/images", response_model=ImageUploadResponse)
async def upload_image(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
) -> ImageUploadResponse:
    content = await file.read(settings.upload_image_max_bytes + 1)
    store = ImageUploadStore(
        settings.upload_image_path,
        max_bytes=settings.upload_image_max_bytes,
        ttl_seconds=settings.upload_image_ttl_seconds,
    )
    try:
        stored = store.save(
            filename=file.filename or "upload",
            mime_type=file.content_type or "",
            content=content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ImageUploadResponse(
        image_id=stored.image_id,
        filename=stored.filename,
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
    )
