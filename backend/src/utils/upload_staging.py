from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import UploadFile


@dataclass
class StagedUpload:
    filename: str
    content_type: str
    temp_path: str
    file_bytes: bytes


async def stage_upload_file(
    upload: UploadFile,
    *,
    temp_path: str,
    chunk_size: int = 8192,
) -> StagedUpload:
    """Persist an UploadFile before returning a streaming response.

    Starlette may close request-bound UploadFile objects once the endpoint
    returns a StreamingResponse. Staging the payload eagerly keeps later SSE
    processing independent from the request lifecycle.
    """

    filename = upload.filename or os.path.basename(temp_path) or "uploaded-file"
    content_type = upload.content_type or "application/octet-stream"
    file_bytes = b""

    try:
        with open(temp_path, "wb") as buffer:
            while True:
                chunk = await upload.read(chunk_size)
                if not chunk:
                    break
                buffer.write(chunk)
                file_bytes += chunk
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise

    return StagedUpload(
        filename=filename,
        content_type=content_type,
        temp_path=temp_path,
        file_bytes=file_bytes,
    )
