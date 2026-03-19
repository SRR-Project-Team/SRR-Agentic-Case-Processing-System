from .system import build_system_router
from .auth import build_auth_router
from .cases import build_cases_router
from .chat import build_chat_router
from .files import build_files_router
from .knowledge_base import build_knowledge_base_router

__all__ = [
    "build_system_router",
    "build_auth_router",
    "build_cases_router",
    "build_chat_router",
    "build_files_router",
    "build_knowledge_base_router",
]
