from __future__ import annotations

import traceback
from typing import Callable, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ChatMessageRequest(BaseModel):
    session_id: str
    message_type: str
    content: str
    case_id: Optional[int] = None
    file_info: Optional[dict] = None


class CreateSessionRequest(BaseModel):
    title: Optional[str] = None


def build_chat_router(*, db_manager, get_current_user_dep: Callable) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["chat"])

    @router.get("/chat-history")
    async def get_chat_history(
        session_id: Optional[str] = None,
        limit: int = 100,
        current_user: dict = Depends(get_current_user_dep),
    ):
        try:
            messages = db_manager.get_user_chat_history(
                user_phone=current_user["phone_number"],
                session_id=session_id,
                limit=limit,
            )
            return {"status": "success", "messages": messages, "count": len(messages)}
        except Exception as e:
            print(f"❌ 获取聊天历史失败: {e}")
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": f"获取聊天历史失败: {str(e)}"},
            )

    @router.post("/chat-history")
    async def save_chat_message(
        message: ChatMessageRequest,
        current_user: dict = Depends(get_current_user_dep),
    ):
        try:
            message_data = {
                "user_phone": current_user["phone_number"],
                "session_id": message.session_id,
                "message_type": message.message_type,
                "content": message.content,
                "case_id": message.case_id,
                "file_info": message.file_info,
            }
            message_id = db_manager.save_chat_message(message_data)
            return {"status": "success", "message": "消息保存成功", "message_id": message_id}
        except Exception as e:
            print(f"❌ 保存聊天消息失败: {e}")
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": f"保存聊天消息失败: {str(e)}"},
            )

    @router.get("/chat-sessions")
    async def get_user_sessions(current_user: dict = Depends(get_current_user_dep)):
        try:
            sessions = db_manager.get_user_sessions(user_phone=current_user["phone_number"])
            return {"status": "success", "sessions": sessions, "count": len(sessions)}
        except Exception as e:
            print(f"❌ 获取会话列表失败: {e}")
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": f"获取会话列表失败: {str(e)}"},
            )

    @router.post("/chat-sessions")
    async def create_chat_session(
        request: CreateSessionRequest,
        current_user: dict = Depends(get_current_user_dep),
    ):
        try:
            session = db_manager.create_chat_session(
                user_phone=current_user["phone_number"], title=request.title
            )
            return {"status": "success", "session": session}
        except Exception as e:
            print(f"❌ 创建会话失败: {e}")
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": f"创建会话失败: {str(e)}"},
            )

    @router.delete("/chat-sessions/{session_id}")
    async def delete_chat_session(
        session_id: str,
        current_user: dict = Depends(get_current_user_dep),
    ):
        try:
            deleted = db_manager.delete_chat_session(
                user_phone=current_user["phone_number"], session_id=session_id
            )
            return {"status": "success", "message": "会话已删除", "deleted": deleted}
        except Exception as e:
            print(f"❌ 删除会话失败: {e}")
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": f"删除会话失败: {str(e)}"},
            )

    return router
