import asyncio
from functools import partial

import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.config import get_settings
from app.core.dependencies import require_admin

router = APIRouter(prefix="/media", tags=["media"])

MAX_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/avif",
    "image/svg+xml",
    "image/bmp",
    "image/tiff",
    "image/heic",
    "image/heif",
}


def _configure_cloudinary() -> None:
    s = get_settings()
    cloudinary.config(
        cloud_name=s.cloudinary_cloud_name,
        api_key=s.cloudinary_api_key,
        api_secret=s.cloudinary_api_secret,
        secure=True,
    )


@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    _: dict = Depends(require_admin),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Upload an image file.",
        )

    contents = await file.read()

    if len(contents) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds the 10 MB limit.")

    _configure_cloudinary()

    loop = asyncio.get_event_loop()
    upload_fn = partial(
        cloudinary.uploader.upload,
        contents,
        folder="crimax-sports/news",
        resource_type="image",
        overwrite=False,
    )

    try:
        result = await loop.run_in_executor(None, upload_fn)
    except Exception as exc:
        msg = str(exc)
        if any(k in msg for k in ("No route to host", "Max retries", "ConnectionError", "NewConnection")):
            raise HTTPException(status_code=502, detail="Could not reach the image server. Check your internet connection and try again.")
        if "Invalid" in msg or "401" in msg or "Must supply" in msg:
            raise HTTPException(status_code=502, detail="Image server authentication failed. Check Cloudinary credentials.")
        raise HTTPException(status_code=502, detail="Image upload failed. Please try again.")

    raw_url: str = result["secure_url"]
    optimized_url = raw_url.replace("/upload/", "/upload/q_auto:best,f_auto/")

    return {"url": optimized_url, "public_id": result["public_id"]}
