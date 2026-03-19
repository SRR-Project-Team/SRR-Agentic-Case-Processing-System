from __future__ import annotations

from typing import Callable, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class KBRefreshRequest(BaseModel):
    category: Optional[str] = None
    file_id: Optional[int] = None


class KBUploadPrecheckRequest(BaseModel):
    filename: str
    file_hash: Optional[str] = None
    file_size: Optional[int] = None


class KBApproveRequest(BaseModel):
    doc_type: str
    filename: str


def build_knowledge_base_router(
    *,
    kb_service,
    vector_store_client,
    get_current_user_dep: Callable,
    user_role_resolver: Callable,
) -> APIRouter:
    """Phase5 split: knowledge-base management endpoints."""
    router = APIRouter(prefix="/api/knowledge-base", tags=["knowledge-base"])

    @router.post("/slope-data/upload")
    async def upload_slope_data_file(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        current_user: dict = Depends(get_current_user_dep),
    ):
        try:
            data = await kb_service.upload_file(
                file=file,
                uploaded_by=current_user["phone_number"],
                category="slope_data",
                background_tasks=background_tasks,
            )
            return JSONResponse(
                status_code=202,
                content={
                    "status": "success",
                    "message": "Slope data uploaded; processing in background.",
                    "data": data,
                },
            )
        except Exception as exc:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": str(exc)},
            )

    @router.post("/template/upload")
    async def upload_template_file(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        reply_type: str = Query(..., description="interim | final | wrong_referral"),
        current_user: dict = Depends(get_current_user_dep),
    ):
        try:
            data = await kb_service.upload_template_file(
                file=file,
                reply_type=reply_type.strip().lower(),
                uploaded_by=current_user["phone_number"],
                background_tasks=background_tasks,
            )
            return JSONResponse(
                status_code=202,
                content={
                    "status": "success",
                    "message": "Template uploaded; processing in background.",
                    "data": data,
                },
            )
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": str(exc)},
            )
        except Exception as exc:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": str(exc)},
            )

    @router.get("/templates")
    async def get_template_slots(current_user: dict = Depends(get_current_user_dep)):
        """Get status of all 3 template slots."""
        data = kb_service.get_template_slots_status()
        return {"status": "success", "data": data}

    @router.post("/tree-inventory/upload")
    async def upload_tree_inventory_file(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        current_user: dict = Depends(get_current_user_dep),
    ):
        try:
            data = await kb_service.upload_file(
                file=file,
                uploaded_by=current_user["phone_number"],
                category="tree_inventory",
                background_tasks=background_tasks,
            )
            return JSONResponse(
                status_code=202,
                content={
                    "status": "success",
                    "message": "Tree inventory uploaded; processing in background.",
                    "data": data,
                },
            )
        except Exception as exc:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": str(exc)},
            )

    @router.post("/precheck-upload")
    async def precheck_knowledge_base_upload(
        payload: KBUploadPrecheckRequest,
        current_user: dict = Depends(get_current_user_dep),
    ):
        data = kb_service.precheck_upload(
            filename=payload.filename,
            file_hash=(payload.file_hash or "").strip() or None,
            file_size=payload.file_size,
            user_phone=current_user["phone_number"],
            role=user_role_resolver(current_user),
        )
        return {"status": "success", "data": data}

    @router.get("/stats")
    async def get_knowledge_base_stats(current_user: dict = Depends(get_current_user_dep)):
        stats = kb_service.get_stats(
            user_phone=current_user["phone_number"],
            role=user_role_resolver(current_user),
        )
        return {"status": "success", "data": stats}

    @router.post("/refresh")
    async def refresh_knowledge_base(
        payload: KBRefreshRequest,
        background_tasks: BackgroundTasks,
        current_user: dict = Depends(get_current_user_dep),
    ):
        result = kb_service.refresh(
            background_tasks=background_tasks,
            user_phone=current_user["phone_number"],
            role=user_role_resolver(current_user),
            category=payload.category,
            file_id=payload.file_id,
        )
        return {
            "status": "success",
            "message": "Refresh tasks queued",
            "data": result,
        }

    @router.get("/pending-approval")
    async def get_pending_approval(current_user: dict = Depends(get_current_user_dep)):
        """List knowledge docs (e.g. reply templates) awaiting user approval for retrieval."""
        items = vector_store_client.list_pending_knowledge_docs()
        return {
            "status": "success",
            "data": [
                {
                    "id": r.get("id"),
                    "doc_type": r.get("doc_type"),
                    "filename": r.get("filename"),
                    "content_preview": (r.get("content") or "")[:200],
                    "create_time": r.get("create_time"),
                }
                for r in items
            ],
        }

    @router.post("/approve")
    async def approve_knowledge_doc(
        payload: KBApproveRequest,
        current_user: dict = Depends(get_current_user_dep),
    ):
        """Approve a knowledge doc so it becomes available for RAG retrieval."""
        count = vector_store_client.approve_knowledge_doc(
            doc_type=payload.doc_type,
            filename=payload.filename,
        )
        if count == 0:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "Document not found"},
            )
        return {"status": "success", "message": "Approved", "data": {"updated": count}}

    return router
