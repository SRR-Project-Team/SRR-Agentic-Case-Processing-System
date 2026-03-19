from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse


def build_cases_router(
    *,
    db_manager,
    get_current_user_dep: Callable,
    user_role_resolver: Callable,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["cases"])

    @router.get("/cases")
    async def get_cases(
        limit: int = 100,
        offset: int = 0,
        current_user: dict = Depends(get_current_user_dep),
    ):
        cases = db_manager.get_cases_for_user(
            user_phone=current_user["phone_number"],
            role=user_role_resolver(current_user),
            limit=limit,
            offset=offset,
        )
        return {"cases": cases, "total": len(cases)}

    @router.get("/cases/{case_id}")
    async def get_case(case_id: int, current_user: dict = Depends(get_current_user_dep)):
        case = db_manager.get_case_for_user(
            case_id=case_id,
            user_phone=current_user["phone_number"],
            role=user_role_resolver(current_user),
        )
        if case:
            return case
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Case does not exist or forbidden"},
        )

    @router.get("/cases/{case_id}/details")
    async def get_case_details(
        case_id: int,
        current_user: dict = Depends(get_current_user_dep),
    ):
        case = db_manager.get_case_for_user(
            case_id=case_id,
            user_phone=current_user["phone_number"],
            role=user_role_resolver(current_user),
        )
        if not case:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "Case does not exist or forbidden"},
            )
        conversations = db_manager.get_conversations_by_case_for_user(
            case_id=case_id,
            user_phone=current_user["phone_number"],
            role=user_role_resolver(current_user),
        )
        return {
            "case": case,
            "conversations": conversations,
            "attachments": [
                {
                    "name": case.get("original_filename", ""),
                    "type": case.get("file_type", ""),
                    "note": "源案件文件",
                }
            ],
        }

    @router.get("/cases/search")
    async def search_cases(q: str, current_user: dict = Depends(get_current_user_dep)):
        cases = db_manager.search_cases_for_user(
            keyword=q,
            user_phone=current_user["phone_number"],
            role=user_role_resolver(current_user),
        )
        return {"cases": cases, "query": q}

    return router
