from __future__ import annotations

import os
import traceback
from typing import Callable, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse


def build_files_router(
    *,
    db_manager,
    get_current_user_dep: Callable,
    user_role_resolver: Callable,
    process_rag_file_background_fn: Callable,
    create_vector_client_fn: Callable,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["files"])

    @router.post("/rag-files/upload")
    async def upload_rag_file(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        category: Optional[str] = Form(None),
        current_user: dict = Depends(get_current_user_dep),
    ):
        try:
            from utils.file_processors import detect_file_type_from_extension
            from utils.file_storage import save_rag_file
            from utils.hash_utils import calculate_file_hash
            from database.models import KnowledgeBaseFile

            file_type = detect_file_type_from_extension(file.filename)
            if file_type == "unknown":
                return JSONResponse(
                    status_code=400,
                    content={"status": "error", "message": f"Unsupported file type: {file.filename}"},
                )

            file_content = await file.read()
            file_size = len(file_content)
            file_hash = calculate_file_hash(file_content)
            existing = db_manager.check_kb_file_duplicate(
                file_hash,
                filename=file.filename,
                file_size=file_size,
            )
            if existing:
                return JSONResponse(
                    status_code=409,
                    content={
                        "status": "error",
                        "message": "文件已存在，请勿重复上传",
                        "existing_id": existing["id"],
                        "existing_filename": existing["filename"],
                    },
                )

            full_path, relative_path = save_rag_file(file_content, file.filename)

            session = db_manager.get_session()
            try:
                kb_file = KnowledgeBaseFile(
                    filename=file.filename,
                    file_type=file_type,
                    file_hash=file_hash,
                    category=(category or "general"),
                    file_path=relative_path,
                    file_size=file_size,
                    mime_type=file.content_type or "application/octet-stream",
                    uploaded_by=current_user["phone_number"],
                    processed=False,
                )
                session.add(kb_file)
                session.commit()
                file_id = kb_file.id
                result = {
                    "id": kb_file.id,
                    "filename": kb_file.filename,
                    "file_type": kb_file.file_type,
                    "category": kb_file.category,
                    "file_size": kb_file.file_size,
                    "upload_time": kb_file.upload_time.isoformat(),
                    "processed": False,
                    "chunk_count": 0,
                    "metadata": kb_file.get_metadata(),
                }
            finally:
                session.close()

            background_tasks.add_task(
                process_rag_file_background_fn,
                file_id,
                full_path,
                relative_path,
                file_type,
                file_size,
                file.content_type or "application/octet-stream",
                file.filename,
            )

            return JSONResponse(
                status_code=202,
                content={
                    "status": "success",
                    "message": "File uploaded; processing in background (chunking and embedding).",
                    "data": result,
                },
            )
        except Exception:
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Upload failed"},
            )

    @router.get("/rag-files")
    async def get_rag_files(current_user: dict = Depends(get_current_user_dep)):
        try:
            files = db_manager.get_kb_files_for_user(
                user_phone=current_user["phone_number"],
                role=user_role_resolver(current_user),
            )
            return JSONResponse(status_code=200, content={"status": "success", "data": files})
        except Exception:
            traceback.print_exc()
            return JSONResponse(
                status_code=500, content={"status": "error", "message": "Get files failed"}
            )

    @router.get("/rag-files/{file_id}")
    async def get_rag_file_details(file_id: int, current_user: dict = Depends(get_current_user_dep)):
        try:
            kb_file = db_manager.get_kb_file_for_user(
                file_id=file_id,
                user_phone=current_user["phone_number"],
                role=user_role_resolver(current_user),
            )
            if not kb_file:
                return JSONResponse(
                    status_code=404,
                    content={"status": "error", "message": "File not found or forbidden"},
                )
            return JSONResponse(status_code=200, content={"status": "success", "data": kb_file})
        except Exception:
            traceback.print_exc()
            return JSONResponse(
                status_code=500, content={"status": "error", "message": "Get file details failed"}
            )

    @router.get("/rag-files/{file_id}/download")
    async def download_rag_file(file_id: int, current_user: dict = Depends(get_current_user_dep)):
        try:
            from fastapi.responses import Response
            from utils.file_storage import file_exists, read_file_bytes

            kb_file = db_manager.get_kb_file_for_user(
                file_id=file_id,
                user_phone=current_user["phone_number"],
                role=user_role_resolver(current_user),
            )
            if not kb_file:
                return JSONResponse(
                    status_code=404,
                    content={"status": "error", "message": "File not found or forbidden"},
                )

            file_path = kb_file["file_path"]
            if not file_exists(file_path):
                return JSONResponse(
                    status_code=404, content={"status": "error", "message": "Physical file not found"}
                )

            content = read_file_bytes(file_path)
            if content is None:
                return JSONResponse(
                    status_code=404, content={"status": "error", "message": "Physical file not found"}
                )

            filename = kb_file["filename"]
            return Response(
                content=content,
                media_type=kb_file["mime_type"],
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        except Exception:
            traceback.print_exc()
            return JSONResponse(
                status_code=500, content={"status": "error", "message": "Download file failed"}
            )

    @router.delete("/rag-files/{file_id}")
    async def delete_rag_file(file_id: int, current_user: dict = Depends(get_current_user_dep)):
        try:
            from utils.file_storage import delete_rag_file as delete_file_storage

            kb_file = db_manager.get_kb_file_for_user(
                file_id=file_id,
                user_phone=current_user["phone_number"],
                role=user_role_resolver(current_user),
            )
            if not kb_file:
                return JSONResponse(
                    status_code=404,
                    content={"status": "error", "message": "File not found or forbidden"},
                )

            file_path = kb_file["file_path"]

            if kb_file["processed"] and kb_file["chunk_count"] > 0:
                try:
                    vector_store = create_vector_client_fn()
                    await vector_store.delete_vectors_by_file_id_sync(f"rag_file_{file_id}")
                except Exception as vec_error:
                    print(f"⚠️ Failed to delete vectors: {vec_error}")

            try:
                delete_file_storage(file_path)
            except Exception as file_error:
                print(f"⚠️ Failed to delete physical file: {file_error}")

            deleted = db_manager.soft_delete_kb_file_for_user(
                file_id=file_id,
                user_phone=current_user["phone_number"],
                role=user_role_resolver(current_user),
            )
            if not deleted:
                return JSONResponse(
                    status_code=403, content={"status": "error", "message": "Delete forbidden"}
                )

            return JSONResponse(
                status_code=200, content={"status": "success", "message": "File deleted successfully"}
            )
        except Exception:
            traceback.print_exc()
            return JSONResponse(
                status_code=500, content={"status": "error", "message": "Delete file failed"}
            )

    @router.get("/rag-files/{file_id}/preview")
    async def get_rag_file_preview(
        file_id: int,
        full: bool = False,
        offset: int = 0,
        limit: Optional[int] = None,
        current_user: dict = Depends(get_current_user_dep),
    ):
        try:
            from utils.file_storage import get_file_preview_slice

            kb_file = db_manager.get_kb_file_for_user(
                file_id=file_id,
                user_phone=current_user["phone_number"],
                role=user_role_resolver(current_user),
            )
            if not kb_file:
                return JSONResponse(
                    status_code=404,
                    content={"status": "error", "message": "File not found or forbidden"},
                )

            file_path = kb_file["file_path"]
            file_type = kb_file["file_type"]
            if full or limit is not None or offset > 0:
                read_limit = None if full and limit is None else (limit or 100_000)
                preview_content, total_length = get_file_preview_slice(
                    file_path, file_type, offset=offset, limit=read_limit
                )
                if preview_content is None:
                    preview_content = kb_file.get("preview_text") or ""
                    total_length = len(preview_content)
            else:
                preview_content = kb_file.get("preview_text") or ""
                total_length = len(preview_content)

            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "data": {
                        "filename": kb_file["filename"],
                        "file_type": file_type,
                        "preview_content": preview_content,
                        "total_length": total_length,
                    },
                },
            )
        except Exception:
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Get file preview failed"},
            )

    @router.get("/rag-files/{file_id}/preview-pdf")
    async def get_rag_file_preview_pdf(
        file_id: int,
        current_user: dict = Depends(get_current_user_dep),
    ):
        """Return a PDF rendering of an Office file (excel/word/powerpoint).

        Uses LibreOffice headless for conversion. Returns 404 if the file is
        not an Office type, and 503 if LibreOffice is not installed.
        """
        try:
            from fastapi.responses import FileResponse
            from utils.file_storage import file_exists, get_local_path_for_reading
            from utils.office_to_pdf import convert_to_pdf, is_office_type, libreoffice_available

            kb_file = db_manager.get_kb_file_for_user(
                file_id=file_id,
                user_phone=current_user["phone_number"],
                role=user_role_resolver(current_user),
            )
            if not kb_file:
                return JSONResponse(
                    status_code=404,
                    content={"status": "error", "message": "File not found or forbidden"},
                )

            file_type = kb_file["file_type"]
            if not is_office_type(file_type):
                return JSONResponse(
                    status_code=400,
                    content={"status": "error", "message": "Not an Office file type"},
                )

            if not libreoffice_available():
                return JSONResponse(
                    status_code=503,
                    content={"status": "error", "message": "LibreOffice is not installed on the server"},
                )

            if not file_exists(kb_file["file_path"]):
                return JSONResponse(
                    status_code=404,
                    content={"status": "error", "message": "Physical file not found"},
                )

            source_path = get_local_path_for_reading(kb_file["file_path"])
            if not source_path:
                return JSONResponse(
                    status_code=404,
                    content={"status": "error", "message": "Physical file not found"},
                )

            pdf_path = convert_to_pdf(source_path)
            if pdf_path is None or not os.path.isfile(pdf_path):
                return JSONResponse(
                    status_code=500,
                    content={"status": "error", "message": "PDF conversion failed"},
                )

            pdf_name = os.path.splitext(kb_file["filename"])[0] + ".pdf"
            return FileResponse(
                path=pdf_path,
                filename=pdf_name,
                media_type="application/pdf",
            )
        except Exception:
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Preview PDF failed"},
            )

    return router
