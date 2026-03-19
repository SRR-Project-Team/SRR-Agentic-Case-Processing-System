from __future__ import annotations

import traceback
from typing import Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel


class UserRegisterRequest(BaseModel):
    phone_number: str
    password: str
    full_name: str
    department: Optional[str] = None
    role: Optional[str] = "user"
    email: Optional[str] = None


def build_auth_router(
    *,
    db_manager,
    get_current_user_dep: Callable,
    verify_password_fn: Callable,
    get_password_hash_fn: Callable,
    create_access_token_fn: Callable,
) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"])

    @router.post("/register")
    async def register(user_data: UserRegisterRequest):
        from database.models import User

        session = db_manager.get_session()
        try:
            existing_user = session.query(User).filter(
                User.phone_number == user_data.phone_number
            ).first()

            if existing_user:
                session.close()
                return JSONResponse(
                    status_code=400,
                    content={"status": "error", "message": "该电话号码已注册"},
                )

            hashed_password = get_password_hash_fn(user_data.password)
            new_user = User(
                phone_number=user_data.phone_number,
                password_hash=hashed_password,
                full_name=user_data.full_name,
                department=user_data.department,
                role=user_data.role or "user",
                email=user_data.email,
            )

            session.add(new_user)
            session.commit()

            user_info = {
                "phone_number": new_user.phone_number,
                "full_name": new_user.full_name,
                "department": new_user.department,
                "role": new_user.role,
                "email": new_user.email,
            }

            session.close()
            return JSONResponse(
                status_code=201,
                content={
                    "status": "success",
                    "message": "注册成功",
                    "user": user_info,
                },
            )
        except Exception as e:
            session.rollback()
            session.close()
            print(f"❌ 用户注册失败: {e}")
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": f"注册失败: {str(e)}"},
            )

    @router.post("/login")
    async def login(form_data: OAuth2PasswordRequestForm = Depends()):
        from database.models import User

        phone_number = form_data.username
        password = form_data.password

        session = db_manager.get_session()
        try:
            user = session.query(User).filter(User.phone_number == phone_number).first()

            if not user:
                session.close()
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="电话号码或密码错误",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            if not verify_password_fn(password, user.password_hash):
                session.close()
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="电话号码或密码错误",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            if not user.is_active:
                session.close()
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="账户已被禁用",
                )

            access_token = create_access_token_fn(data={"sub": user.phone_number})
            user_info = {
                "phone_number": user.phone_number,
                "full_name": user.full_name,
                "department": user.department,
                "role": user.role,
                "email": user.email,
            }
            session.close()

            return {
                "access_token": access_token,
                "token_type": "bearer",
                "user": user_info,
            }
        except HTTPException:
            raise
        except Exception as e:
            session.close()
            print(f"❌ 登录失败: {e}")
            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"登录失败: {str(e)}",
            )

    @router.get("/me")
    async def get_current_user_info(current_user: dict = Depends(get_current_user_dep)):
        return {"status": "success", "user": current_user}

    @router.post("/logout")
    async def logout():
        return {"status": "success", "message": "登出成功"}

    return router
