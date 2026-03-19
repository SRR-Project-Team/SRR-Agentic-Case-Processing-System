"""
SRR Case Processing API Main Program

This program provides RESTful API interfaces for processing SRR case TXT files and extracting structured data.
Adopts modular design, separating data extraction and output logic into independent modules.

Main functions:
1. Receive TXT file uploads
2. Validate file types
3. Call data extraction modules to process file content
4. Call output modules to format results
5. Return JSON format processing results

API endpoints:
- POST /api/process-srr-file: Process SRR case files
- GET /health: Health check

Author: Project3 Team
Version: 1.0
"""
from fastapi import FastAPI, UploadFile, File, Form, Request, status, Depends, HTTPException, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import List, Dict, Any, Optional
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import queue
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.exceptions import RequestValidationError
import os
import re
import tempfile
import time
import traceback
import logging
import json
from pathlib import Path
from uuid import uuid4
from pydantic import BaseModel

# Calculate backend directory path (used for .env file and module imports)
# From main.py (backend/src/api/main.py), we need to go up 3 levels:
#   1st dirname: backend/src/api/main.py -> backend/src/api
#   2nd dirname: backend/src/api -> backend/src  
#   3rd dirname: backend/src -> backend
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import custom modules
# Set Python path to import project modules
import sys
import os
# Add backend/src to path for importing core modules (core, utils, services, database)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Add backend directory to path for importing config module
sys.path.append(backend_dir)

from src.services.text_splitter import split_text
from src.core.embedding import (
    embed_text,
    embed_texts,
    set_embedding_override,
    EMBEDDING_PROVIDER,
    OPENAI_EMBED_MODEL,
    OLLAMA_EMBED_MODEL,
    OPENAI_EMBED_MODELS,
    OLLAMA_EMBED_MODELS,
)
from src.core.pg_vector_store import PgVectorStore

class ChatRequest(BaseModel):
    query: str
    context: dict
    raw_content: str
    session_id: Optional[str] = None
    provider: Optional[str] = "openai"
    model: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None

# Authentication related request models
class UserRegisterRequest(BaseModel):
    phone_number: str
    password: str
    full_name: str
    department: Optional[str] = None
    role: Optional[str] = "user"
    email: Optional[str] = None

class LoginRequest(BaseModel):
    phone_number: str
    password: str

class ChatMessageRequest(BaseModel):
    session_id: str
    message_type: str  # 'user' or 'bot'
    content: str
    case_id: Optional[int] = None
    file_info: Optional[dict] = None


class CaseUploadPrecheckRequest(BaseModel):
    filename: str
    file_hash: Optional[str] = None


class CreateSessionRequest(BaseModel):
    title: Optional[str] = None


class UserFeedbackRequest(BaseModel):
    case_id: Optional[int] = None
    field_name: str
    incorrect_value: Optional[str] = None
    correct_value: str
    note: Optional[str] = None
    source_text: Optional[str] = None
    scope: Optional[str] = "global"


# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Configure logging for debug visibility
# Set logging level based on environment variable, default to INFO for production
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
if log_level == "DEBUG":
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    print("🔍 DEBUG logging enabled")
else:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


# Load environment variables from .env file (for local development)
# IMPORTANT: This must be done BEFORE importing config.settings
try:
    from dotenv import load_dotenv
    # Load .env file from backend directory
    env_path = os.path.join(backend_dir, '.env')
    if os.path.exists(env_path):
        # Use override=True to ensure .env file values take precedence
        # This is important if environment variables are already set
        load_dotenv(env_path, override=True)
        print(f"✅ Loaded environment variables from {env_path}", flush=True)
        
        # Debug: Check if OPENAI_API_KEY was loaded (masked for security)
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            print(f"   ✓ OPENAI_API_KEY found (starts with: {api_key[:7]}...)", flush=True)
        else:
            print(f"   ⚠️  OPENAI_API_KEY not found in .env file", flush=True)
    else:
        print(f"ℹ️  No .env file found at {env_path}, using system environment variables", flush=True)
        print(f"   Looking for .env at: {env_path}", flush=True)
except ImportError:
    print("ℹ️  python-dotenv not installed, using system environment variables only")
    print("   Install with: pip install python-dotenv")


# Import core processing modules
from core.extractFromTxt import extract_case_data_from_txt  # TXT file processor
from core.extractFromTMO import extract_case_data_from_pdf as extract_tmo_data  # TMO PDF processor
from core.extractFromRCC import extract_case_data_from_pdf as extract_rcc_data  # RCC PDF processor
from core.output import (  # Output formatting module
    create_structured_data, 
    create_success_result, 
    create_error_result,
    validate_file_type,
    get_file_type_error_message,
    ProcessingResult,
    StructuredCaseData
)
from utils.smart_file_pairing import SmartFilePairing  # Smart file pairing utility
from utils.file_utils import read_file_with_encoding,extract_text_from_pdf_fast,extract_content_with_multiple_methods
from utils.input_adapter import parse_uploaded_documents
from utils.file_sorter import sort_uploaded_files

# Set database module path
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from database import get_db_manager  # Database manager
from services.auth_service import (
    verify_password,
    get_password_hash,
    create_access_token,
    verify_token
)
from utils.hash_utils import calculate_file_hash

# Initialize database manager
# Create global database manager instance for storing and retrieving case data
db_manager = get_db_manager()

# Import LLM service
from services.llm_service import get_llm_service
from config.settings import (
    EXTERNAL_API_ENABLED,
    FEATURE_AGENT_ROUTER,
    FEATURE_DYNAMIC_KB,
    LLM_API_KEY,
    MAX_RAG_CHUNKS,
    OLLAMA_BASE_URL,
)
from agent import AgentTooling, TaskState, process_case, stream_chat_events
from services.knowledge_base_service import KnowledgeBaseService
from services.external_data_service import ExternalDataService
from services.slope_service import SlopeService
from services.tree_id_resolver import TreeIDResolver
from services.adaptive_rag_config import get_adaptive_rag_config
from services.user_feedback_service import UserFeedbackService
from api.routes.knowledge_base import build_knowledge_base_router
from utils.metrics import metrics_response

# Import template loader and language detector
from utils.template_loader import get_template_loader
from utils.language_detector import detect_language
from utils.slope_location_mapper import extract_slope_from_query, normalize_slope_core

# Log API key status at module load time
if LLM_API_KEY:
    print(f"📝 Module loaded: OPENAI_API_KEY is configured (starts with: {LLM_API_KEY[:7]}...)", flush=True)
else:
    print(f"⚠️  Module loaded: OPENAI_API_KEY is NOT configured", flush=True)

# Create FastAPI application instance
# Configure API basic information, including title and version
app = FastAPI(
    title="SRR Case Processing API (A-Q New Rules)", 
    version="1.0",
    description="Intelligent SRR case processing system, supports TXT, TMO PDF, and RCC PDF file formats"
)

# Enable remote debugging if DEBUG_PORT is set (for Cloud Run debugging)
DEBUG_PORT = os.getenv("DEBUG_PORT")
if DEBUG_PORT:
    try:
        import debugpy
        debugpy.listen(("0.0.0.0", int(DEBUG_PORT)))
        print(f"🐛 Remote debugger listening on port {DEBUG_PORT}", flush=True)
        # Optional: Wait for debugger to attach before continuing
        # debugpy.wait_for_client()  # Uncomment if you want to wait for debugger
    except ImportError:
        print(f"⚠️  debugpy not installed. Install with: pip install debugpy", flush=True)
    except Exception as e:
        print(f"⚠️  Failed to start debugger: {e}", flush=True)

# Configure CORS middleware
# Allow frontend application (React) to access API via CORS
# Read allowed origins from environment variables, support both development and production environments
# Format: CORS_ALLOWED_ORIGINS="http://localhost:3000,https://your-firebase-app.web.app"
cors_allowed_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "")
if cors_allowed_origins_env:
    # Parse multiple origins from environment variable (comma-separated)
    allowed_origins = [origin.strip() for origin in cors_allowed_origins_env.split(",") if origin.strip()]
else:
    # Default to allow local development addresses
    allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]

print(f"🌐 CORS allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # Frontend addresses read from environment variables (development and production)
    allow_credentials=True,  # Allow credentials
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all request headers
)

# Global exception handler - ensure CORS headers are returned even on errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler, ensures CORS headers are returned even on errors"""
    error_detail = {
        "type": type(exc).__name__,
        "path": str(request.url),
        "method": request.method
    }
    # Keep detailed diagnostics in server logs only
    print(f"❌ Global exception caught: {error_detail}, detail={exc}")
    traceback.print_exc()
    
    # Get the Origin header from the request
    origin = request.headers.get("origin")
    # Check if it's in the allowed origins list
    cors_headers = {}
    if origin and origin in allowed_origins:
        cors_headers = {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "true",
        }
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"status": "error", "message": "Internal server error"},
        headers=cors_headers
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Request validation exception handler"""
    origin = request.headers.get("origin")
    cors_headers = {}
    if origin and origin in allowed_origins:
        cors_headers = {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "true",
        }
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "body": exc.body},
        headers=cors_headers
    )

# Initialize LLM service on application startup
@app.on_event("startup")
async def startup_event():
    """Application startup event"""
    # Initialize LLM service
    from services.llm_service import init_llm_service
    # Re-import settings to get fresh values (in case .env was loaded)
    import importlib
    import config.settings as settings_module
    importlib.reload(settings_module)
    from config.settings import LLM_API_KEY, LLM_PROVIDER, OPENAI_PROXY_URL, OPENAI_USE_PROXY, ensure_security_config
    
    # Fail fast on missing/weak security config in secure mode
    ensure_security_config()

    # Also check directly from environment variable as fallback
    import os
    api_key = LLM_API_KEY or os.getenv("OPENAI_API_KEY")
    
    # Check if API key is configured
    if not api_key:
        print("⚠️  WARNING: OPENAI_API_KEY environment variable is not set!", flush=True)
        print("   AI summary generation will be disabled.", flush=True)
        print("   To enable AI features, please:", flush=True)
        print("   1. Set the OPENAI_API_KEY environment variable:", flush=True)
        print("      export OPENAI_API_KEY='your-api-key-here'", flush=True)
        print("   2. Or create a .env file in backend/ directory with:", flush=True)
        print("      OPENAI_API_KEY=your-api-key-here", flush=True)
        print("   3. Or set it in your shell before starting the server", flush=True)
    else:
        print(f"✅ OPENAI_API_KEY is configured (key starts with: {api_key[:7]}...)", flush=True)
    
    init_llm_service(api_key, LLM_PROVIDER, OPENAI_PROXY_URL, OPENAI_USE_PROXY)
    
    # Historical case matcher will be lazy-loaded on first use to avoid blocking startup
    print("ℹ️  Historical case matcher will be lazy-loaded on first request")

# Create temporary directory
# Used for storing uploaded files, automatically cleaned up after processing
TEMP_DIR = tempfile.mkdtemp()
print(f"📁 Temporary file directory: {TEMP_DIR}")


def _sanitize_filename(filename: str, max_length: int = 120) -> str:
    """Sanitize user-provided filename to prevent traversal and unsafe chars."""
    cleaned = Path(filename or "").name.replace("\x00", "").strip()
    if not cleaned:
        cleaned = "upload.bin"
    base, ext = os.path.splitext(cleaned)
    safe_base = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in base)
    safe_base = safe_base.strip("._") or "upload"
    safe_ext = "".join(ch for ch in ext[:10] if ch.isalnum() or ch == ".")
    return f"{safe_base[:max_length]}{safe_ext}"


def _build_safe_temp_path(filename: str) -> str:
    """Generate collision-resistant safe temp file path under TEMP_DIR."""
    safe_name = _sanitize_filename(filename)
    return os.path.join(TEMP_DIR, f"{uuid4().hex}_{safe_name}")


def _user_role(current_user: dict) -> str:
    return (current_user or {}).get("role", "user")


def determine_file_processing_type(filename: str, content_type: str) -> str:
    """
    Determine processing method based on filename and content type
    
    Args:
        filename (str): File name
        content_type (str): File MIME type
        
    Returns:
        str: Processing type ("txt", "tmo", "rcc", "unknown")
    
    Note:
        Excel files should be uploaded via /api/rag-files/upload for RAG processing
    """
    # Check file extension
    if filename.lower().endswith('.txt'):
        return "txt"
    elif filename.lower().endswith('.pdf'):
        # Determine PDF type based on filename prefix
        if filename.upper().startswith('ASD'):
            return "tmo"
        elif filename.upper().startswith('RCC'):
            return "rcc"
        else:
            return "unknown"
    else:
        return "unknown"


def validate_file_type_extended(content_type: str, filename: str) -> bool:
    """
    Extended file type validation for case files.
    Supports: TXT, PDF, DOCX (TMO/RCC), JPG/PNG (location maps, site photos), ZIP.
    
    Args:
        content_type (str): File MIME type
        filename (str): File name
        
    Returns:
        bool: Whether it's a supported case file type
        
    Note:
        Excel and other knowledge base files should be uploaded via /api/rag-files/upload
    """
    supported_types = [
        "text/plain",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # DOCX
        "image/jpeg",
        "image/png",
        "application/zip",
        "application/x-zip-compressed",
    ]
    return content_type in supported_types


def get_file_type_error_message_extended() -> str:
    """
    Get case file type error information
    
    Returns:
        str: File type error information
    """
    return "Supported: TXT, PDF, DOCX, JPG/PNG (location maps, site photos), ZIP (max 10MB each)"


def _run_extraction_and_save(
    file_path: str,
    filename: str,
    processing_type: str,
    file_hash: str,
    current_user: Optional[dict],
) -> tuple:
    """
    Sync helper: read content, extract, create_structured_data, save to DB.
    Returns (content, extracted_data, structured_data, case_id, is_new).
    Raises on error.
    """
    if processing_type == "txt":
        content = read_file_with_encoding(file_path)
        extracted_data = extract_case_data_from_txt(file_path)
    elif processing_type == "tmo":
        content = extract_text_from_pdf_fast(file_path)
        extracted_data = extract_tmo_data(file_path)
    elif processing_type == "rcc":
        content = extract_content_with_multiple_methods(file_path)
        extracted_data = extract_rcc_data(file_path)
    else:
        raise ValueError(f"Unknown processing type: {processing_type}")
    structured_data = create_structured_data(extracted_data)
    case_data = {
        "A_date_received": structured_data.A_date_received,
        "B_source": structured_data.B_source,
        "C_case_number": structured_data.C_case_number,
        "D_type": structured_data.D_type,
        "E_caller_name": structured_data.E_caller_name,
        "F_contact_no": structured_data.F_contact_no,
        "G_slope_no": structured_data.G_slope_no,
        "H_location": structured_data.H_location,
        "I_nature_of_request": structured_data.I_nature_of_request,
        "J_subject_matter": structured_data.J_subject_matter,
        "K_10day_rule_due_date": structured_data.K_10day_rule_due_date,
        "L_icc_interim_due": structured_data.L_icc_interim_due,
        "M_icc_final_due": structured_data.M_icc_final_due,
        "N_works_completion_due": structured_data.N_works_completion_due,
        "O1_fax_to_contractor": structured_data.O1_fax_to_contractor,
        "O2_email_send_time": structured_data.O2_email_send_time,
        "P_fax_pages": structured_data.P_fax_pages,
        "Q_case_details": structured_data.Q_case_details,
        "original_filename": filename,
        "file_type": processing_type,
    }
    user_phone = current_user["phone_number"] if current_user else None
    case_id, is_new = db_manager.save_case_with_dedup(case_data, file_hash, user_phone)
    return (content, extracted_data, structured_data, case_id, is_new)


async def process_paired_txt_file(main_file_path: str, email_file_path: str = None) -> dict:
    """
    Process paired TXT files (including optional email file)
    
    Args:
        main_file_path: Main TXT file path
        email_file_path: Email file path (optional)
        
    Returns:
        dict: Extracted case data
    """
    if email_file_path:
        # If email file exists, need to manually process pairing
        from core.extractFromTxt import extract_case_data_with_email
        from utils.file_utils import read_file_with_encoding
        
        # Read file content
        main_content = read_file_with_encoding(main_file_path)
        email_content = read_file_with_encoding(email_file_path)
        
        # Use paired processing
        return extract_case_data_with_email(main_content, email_content, main_content)
    else:
        # Process TXT file separately (will automatically detect email file)
        return extract_case_data_from_txt(main_file_path)

# The summary from field R
async def AI_summary_by_R(R_content: str, filename: str, case_data: dict) -> Dict[str, Any]:
    if R_content:
        llm_service = get_llm_service()
        reviewed = llm_service._review_sum_(R_content, case_data)
        summary = reviewed if reviewed else R_content
        # Guard: if review introduces placeholders (case_data keys left unreplaced), revert to original
        if case_data:
            for key in case_data:
                if key in summary:
                    summary = R_content
                    break
        return {
            "success": True,
            "summary": summary,
            "filename": filename,
            "source": "AI Summary"
        }


def generate_file_summary_stream(file_content: str, filename: str, file_path: str = None):
    """
    Generator that yields summary text chunks for SSE. Uses LLM stream.
    Caller must handle R_AI_Summary path separately (single full summary event).
    """
    llm = get_llm_service()
    if not llm.api_key or not llm.client:
        return
    if file_path and os.path.exists(file_path) and os.path.isfile(file_path):
        try:
            yield from llm.summarize_file_stream(file_path, max_length=150)
        except Exception:
            if file_content:
                yield from llm.summarize_text_stream(file_content, max_length=150)
    elif file_content:
        yield from llm.summarize_text_stream(file_content, max_length=150)


# ============== Authentication Dependency ==============

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    从JWT token获取当前登录用户
    
    Args:
        token: JWT token（从Authorization header自动提取）
        
    Returns:
        dict: 用户信息
        
    Raises:
        HTTPException: 401 if token invalid or user not found
    """
    from database.models import User
    
    # 验证token并获取电话号码
    phone_number = verify_token(token)
    if phone_number is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # 从数据库获取用户信息
    session = db_manager.get_session()
    try:
        user = session.query(User).filter(
            User.phone_number == phone_number,
            User.is_active == True
        ).first()
        
        if user is None:
            session.close()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_dict = {
            "phone_number": user.phone_number,
            "full_name": user.full_name,
            "department": user.department,
            "role": user.role,
            "email": user.email
        }
        
        session.close()
        return user_dict
        
    except HTTPException:
        raise
    except Exception as e:
        session.close()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )


_knowledge_base_service = None
if FEATURE_DYNAMIC_KB:
    _knowledge_base_service = KnowledgeBaseService()
    _vector_store = PgVectorStore()
    app.include_router(
        build_knowledge_base_router(
            kb_service=_knowledge_base_service,
            vector_store_client=_vector_store,
            get_current_user_dep=get_current_user,
            user_role_resolver=_user_role,
        )
    )


# ============== Authentication Endpoints ==============

@app.post("/api/auth/register")
async def register(user_data: UserRegisterRequest):
    """
    用户注册
    
    Args:
        user_data: 用户注册信息（电话号码、密码、姓名等）
        
    Returns:
        JSON response with user information
    """
    from database.models import User
    
    session = db_manager.get_session()
    try:
        # 检查电话号码是否已注册
        existing_user = session.query(User).filter(
            User.phone_number == user_data.phone_number
        ).first()
        
        if existing_user:
            session.close()
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "该电话号码已注册"
                }
            )
        
        # 创建新用户
        hashed_password = get_password_hash(user_data.password)
        new_user = User(
            phone_number=user_data.phone_number,
            password_hash=hashed_password,
            full_name=user_data.full_name,
            department=user_data.department,
            role=user_data.role or "user",
            email=user_data.email
        )
        
        session.add(new_user)
        session.commit()
        
        user_info = {
            "phone_number": new_user.phone_number,
            "full_name": new_user.full_name,
            "department": new_user.department,
            "role": new_user.role,
            "email": new_user.email
        }
        
        session.close()
        
        print(f"✅ 新用户注册成功: {user_data.phone_number}")
        
        return JSONResponse(
            status_code=201,
            content={
                "status": "success",
                "message": "注册成功",
                "user": user_info
            }
        )
        
    except Exception as e:
        session.rollback()
        session.close()
        print(f"❌ 用户注册失败: {e}")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"注册失败: {str(e)}"
            }
        )


@app.post("/api/auth/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    用户登录
    
    Args:
        form_data: OAuth2表单（username=电话号码, password=密码）
        
    Returns:
        JSON response with access token and user information
    """
    from database.models import User

    phone_number = form_data.username  # OAuth2使用username字段
    password = form_data.password

    session = db_manager.get_session()
    try:
        # 查询用户
        user = session.query(User).filter(
            User.phone_number == phone_number
        ).first()
        
        if not user:
            session.close()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="电话号码或密码错误",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 验证密码
        if not verify_password(password, user.password_hash):
            session.close()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="电话号码或密码错误",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 检查用户是否激活
        if not user.is_active:
            session.close()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账户已被禁用"
            )
        
        # 生成JWT token
        access_token = create_access_token(data={"sub": user.phone_number})
        
        user_info = {
            "phone_number": user.phone_number,
            "full_name": user.full_name,
            "department": user.department,
            "role": user.role,
            "email": user.email
        }
        
        session.close()

        print(f"✅ 用户登录成功: {phone_number}")

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": user_info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        session.close()
        print(f"❌ 登录失败: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"登录失败: {str(e)}"
        )


@app.get("/api/auth/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """
    获取当前登录用户信息
    
    Args:
        current_user: 当前用户（从token自动提取）
        
    Returns:
        JSON response with user information
    """
    return {
        "status": "success",
        "user": current_user
    }


@app.post("/api/auth/logout")
async def logout():
    """
    用户登出
    
    Note: JWT是无状态的，实际登出由前端清除token实现
    此端点主要用于日志记录和可能的后续扩展（如token黑名单）
    
    Returns:
        JSON response confirming logout
    """
    return {
        "status": "success",
        "message": "登出成功"
    }


# ============== Chat History Endpoints ==============

@app.get("/api/chat-history")
async def get_chat_history(
    session_id: Optional[str] = None,
    limit: int = 100,
    current_user: dict = Depends(get_current_user)
):
    """
    获取当前用户的聊天历史
    
    Args:
        session_id: 会话ID（可选）
        limit: 最大返回消息数
        current_user: 当前用户（从token自动提取）
        
    Returns:
        JSON response with chat messages
    """
    try:
        messages = db_manager.get_user_chat_history(
            user_phone=current_user['phone_number'],
            session_id=session_id,
            limit=limit
        )
        
        return {
            "status": "success",
            "messages": messages,
            "count": len(messages)
        }
        
    except Exception as e:
        print(f"❌ 获取聊天历史失败: {e}")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"获取聊天历史失败: {str(e)}"
            }
        )


@app.post("/api/chat-history")
async def save_chat_message(
    message: ChatMessageRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    保存聊天消息
    
    Args:
        message: 消息数据
        current_user: 当前用户（从token自动提取）
        
    Returns:
        JSON response with message ID
    """
    try:
        message_data = {
            'user_phone': current_user['phone_number'],
            'session_id': message.session_id,
            'message_type': message.message_type,
            'content': message.content,
            'case_id': message.case_id,
            'file_info': message.file_info
        }
        
        message_id = db_manager.save_chat_message(message_data)
        
        return {
            "status": "success",
            "message": "消息保存成功",
            "message_id": message_id
        }
        
    except Exception as e:
        print(f"❌ 保存聊天消息失败: {e}")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"保存聊天消息失败: {str(e)}"
            }
        )


@app.get("/api/chat-sessions")
async def get_user_sessions(current_user: dict = Depends(get_current_user)):
    """
    获取用户的会话列表
    
    Args:
        current_user: 当前用户（从token自动提取）
        
    Returns:
        JSON response with session list
    """
    try:
        sessions = db_manager.get_user_sessions(
            user_phone=current_user['phone_number']
        )
        
        return {
            "status": "success",
            "sessions": sessions,
            "count": len(sessions)
        }
        
    except Exception as e:
        print(f"❌ 获取会话列表失败: {e}")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"获取会话列表失败: {str(e)}"
            }
        )


@app.post("/api/chat-sessions")
async def create_chat_session(
    request: CreateSessionRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    创建新会话
    """
    try:
        session = db_manager.create_chat_session(
            user_phone=current_user['phone_number'],
            title=request.title
        )
        return {
            "status": "success",
            "session": session
        }
    except Exception as e:
        print(f"❌ 创建会话失败: {e}")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"创建会话失败: {str(e)}"
            }
        )


@app.delete("/api/chat-sessions/{session_id}")
async def delete_chat_session(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    删除当前用户的指定会话（删除该会话下所有消息）。
    """
    try:
        deleted = db_manager.delete_chat_session(
            user_phone=current_user['phone_number'],
            session_id=session_id
        )
        return {
            "status": "success",
            "message": "会话已删除",
            "deleted": deleted
        }
    except Exception as e:
        print(f"❌ 删除会话失败: {e}")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"删除会话失败: {str(e)}"
            }
        )


@app.get("/api/rag-metrics/summary")
async def rag_metrics_summary(
    days: int = 7,
    session_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Return aggregate RAG/CoT quality metrics for the current user."""
    try:
        summary = db_manager.get_quality_metrics_summary(
            user_phone=current_user["phone_number"],
            days=days,
            session_id=session_id,
        )
        return {"status": "success", "summary": summary}
    except Exception as e:
        print(f"❌ 获取RAG指标汇总失败: {e}")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"获取RAG指标汇总失败: {str(e)}"},
        )


@app.get("/api/rag-metrics/trend")
async def rag_metrics_trend(
    days: int = 7,
    session_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Return daily trend of RAG/CoT quality metrics for the current user."""
    try:
        trend = db_manager.get_quality_metrics_trend(
            user_phone=current_user["phone_number"],
            days=days,
            session_id=session_id,
        )
        return {"status": "success", "trend": trend}
    except Exception as e:
        print(f"❌ 获取RAG指标趋势失败: {e}")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"获取RAG指标趋势失败: {str(e)}"},
        )


# ============== File Processing Endpoints ==============

def _normalize_case_fields_for_agent(sd_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize field keys for create_case endpoint while keeping legacy keys.

    Existing extractors/store use SRR legacy names (e.g. K_10day_rule_due_date).
    Agent-style consumers expect aliases (e.g. K_action_due). We expose both.
    """
    fields = dict(sd_dict or {})
    alias_pairs = (
        ("K_10day_rule_due_date", "K_action_due"),
        ("N_works_completion_due", "N_interim_reply_due"),
        ("O1_fax_to_contractor", "O1_first_response_date"),
    )
    for legacy_key, alias_key in alias_pairs:
        if fields.get(legacy_key) and not fields.get(alias_key):
            fields[alias_key] = fields.get(legacy_key)
    return fields


def _extract_all_slope_nos(case_data: Dict[str, Any]) -> List[str]:
    """Extract potential slope numbers from structured fields."""
    pattern = re.compile(r"\b(?:\d{1,2}[A-Z]{2,3}-[A-Z0-9/()\-]+|SA\d+)\b", re.IGNORECASE)
    candidates: List[str] = []
    for key in ("G_slope_no", "H_location", "Q_case_details", "I_nature_of_request"):
        value = str((case_data or {}).get(key) or "")
        if not value:
            continue
        for match in pattern.findall(value):
            normalized = match.strip().upper()
            if normalized and normalized not in candidates:
                candidates.append(normalized)
    return candidates

@app.post("/api/process-srr-file")
async def process_srr_file(
    file: UploadFile = File(...),
    force_reprocess: bool = Form(False),
    embedding_provider: Optional[str] = Form(None),
    embedding_model: Optional[str] = Form(None),
    current_user: Optional[dict] = Depends(get_current_user)
):
    """
    Process SRR case files (SSE stream). Emits: extracted, summary/summary_chunk/summary_end, similar_cases, done.
    Duplicate/validation errors emit event: duplicate or error then close stream.
    """
    print(f"🎯 ENDPOINT HIT: /api/process-srr-file", flush=True)
    start_time = time.time()
    file_path = None

    def sse_event(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def event_stream():
        nonlocal file_path
        if embedding_provider or embedding_model:
            set_embedding_override(embedding_provider, embedding_model)
        try:
            print(f"📥 File upload request: {file.filename}")
            if not validate_file_type_extended(file.content_type, file.filename):
                yield sse_event("error", {"error": get_file_type_error_message_extended()})
                return
            processing_type = determine_file_processing_type(file.filename, file.content_type)
            if processing_type == "unknown":
                yield sse_event("error", {"error": "Unsupported file type or filename format. Supported: TXT files, or PDF files starting with ASD/RCC"})
                return

            file_path = _build_safe_temp_path(file.filename)
            file_size = 0
            file_content_bytes = b""
            with open(file_path, "wb") as buffer:
                chunk_size = 8192
                while True:
                    chunk = await file.read(chunk_size)
                    if not chunk:
                        break
                    buffer.write(chunk)
                    file_content_bytes += chunk
                    file_size += len(chunk)
            print(f"✅ File saved: {file.filename}, {file_size} bytes")
            file_hash = calculate_file_hash(file_content_bytes)
            if force_reprocess:
                # Force a fresh record for local validation workflows.
                # Keep 64-char hash length to satisfy DB schema.
                file_hash = calculate_file_hash(file_content_bytes + uuid4().hex.encode("utf-8"))

            existing_case = None if force_reprocess else db_manager.check_case_duplicate(file_hash)
            if existing_case:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    file_path = None
                sd_dict = {k: existing_case.get(k, "") for k in (
                    "A_date_received", "B_source", "C_case_number", "D_type", "E_caller_name", "F_contact_no",
                    "G_slope_no", "H_location", "I_nature_of_request", "J_subject_matter", "K_10day_rule_due_date",
                    "L_icc_interim_due", "M_icc_final_due", "N_works_completion_due", "O1_fax_to_contractor",
                    "O2_email_send_time", "P_fax_pages", "Q_case_details"
                )}
                payload = {
                    "filename": file.filename,
                    "status": "duplicate",
                    "message": f"File already processed for case number: {existing_case.get('C_case_number', 'N/A')}",
                    "structured_data": sd_dict,
                    "case_id": existing_case["id"],
                }
                yield sse_event("duplicate", payload)
                return

            loop = asyncio.get_event_loop()
            try:
                content, extracted_data, structured_data, case_id, is_new = await loop.run_in_executor(
                    None,
                    _run_extraction_and_save,
                    file_path,
                    file.filename,
                    processing_type,
                    file_hash,
                    current_user,
                )
                if is_new:
                    case_data_for_vec = getattr(structured_data, "model_dump", lambda: structured_data.dict())()
                    asyncio.create_task(_auto_vectorize_new_case(case_id, case_data_for_vec))
            except Exception as ext_err:
                traceback.print_exc()
                yield sse_event("error", {"error": f"Processing failed: {str(ext_err)}"})
                return

            case_data = getattr(structured_data, "model_dump", lambda: structured_data.dict())()
            sd_dict = case_data if isinstance(case_data, dict) else (structured_data.model_dump() if hasattr(structured_data, "model_dump") else structured_data.dict())
            yield sse_event("extracted", {
                "structured_data": sd_dict,
                "case_id": case_id,
                "raw_content": content[:50000] if content else "",
            })

            if EXTERNAL_API_ENABLED:
                try:
                    slope_service = SlopeService()
                    external_service = ExternalDataService()
                    primary_slope = (case_data.get("G_slope_no") or "").strip()
                    external_payload = await external_service.query_all(primary_slope or None)
                    if external_payload.get("enabled"):
                        yield sse_event("external_data", {"external_data": external_payload})

                    if primary_slope:
                        dept_result = await slope_service.determine_department(primary_slope)
                        case_data["department_routing"] = dept_result
                        yield sse_event("department_routing", dept_result)

                    all_slope_nos = _extract_all_slope_nos(case_data)
                    if len(all_slope_nos) > 1:
                        multi_result = await slope_service.check_multi_department(all_slope_nos)
                        if multi_result.get("split_needed"):
                            yield sse_event("multi_department", multi_result)
                except Exception as external_err:
                    print(f"⚠️ External data lookup failed: {external_err}", flush=True)

            summary_result = None
            if extracted_data.get("R_AI_Summary"):
                R_AI_Summary_value = extracted_data.pop("R_AI_Summary")
                summary_result = await AI_summary_by_R(R_AI_Summary_value, file.filename, extracted_data)
                if summary_result and summary_result.get("summary"):
                    yield sse_event("summary", {"summary": summary_result["summary"], "success": True})
            else:
                summary_queue = queue.Queue()

                def run_summary_stream():
                    try:
                        full = []
                        for c in generate_file_summary_stream(content, file.filename, file_path):
                            full.append(c)
                            summary_queue.put(c)
                        summary_queue.put(("end", "".join(full)))
                    except Exception as e:
                        summary_queue.put(("error", str(e)))

                loop.run_in_executor(None, run_summary_stream)
                full_summary = ""
                while True:
                    item = await loop.run_in_executor(None, summary_queue.get)
                    if isinstance(item, tuple):
                        if item[0] == "end":
                            full_summary = item[1]
                            break
                        if item[0] == "error":
                            yield sse_event("summary_end", {"success": False, "error": item[1]})
                            summary_result = {"success": False, "error": item[1]}
                            break
                    else:
                        full_summary += item
                        yield sse_event("summary_chunk", {"text": item})
                if full_summary and not summary_result:
                    summary_result = {"success": True, "summary": full_summary}
                    yield sse_event("summary_end", {"success": True, "summary": full_summary})

            similar_cases = []
            try:
                hybrid = _ensure_hybrid_search_service()
                similar_cases = await hybrid.find_similar_cases(current_case=case_data, limit=5, min_similarity=0.3)
            except Exception as hybrid_err:
                print(f"⚠️ Hybrid search failed: {hybrid_err}", flush=True)
            if not similar_cases:
                try:
                    from services.historical_case_matcher import get_historical_matcher
                    matcher = get_historical_matcher()
                    similar_cases = matcher.find_similar_cases(current_case=case_data, limit=5, min_similarity=0.3)
                except Exception as sc_err:
                    print(f"⚠️ Similar case search failed: {sc_err}", flush=True)

            location_stats = None
            if case_data.get("H_location"):
                try:
                    from services.historical_case_matcher import get_historical_matcher
                    matcher = get_historical_matcher()
                    location_stats = matcher.get_case_statistics(
                        location=case_data.get("H_location"),
                        slope_no=case_data.get("G_slope_no") or None,
                        venue=None,
                    )
                except Exception:
                    pass
            if case_id:
                ai_summary_text = (summary_result.get("summary") if summary_result else None) if isinstance(summary_result, dict) else None
                db_manager.update_case_metadata(case_id=case_id, ai_summary=ai_summary_text, similar_historical_cases=similar_cases, location_statistics=location_stats)

            yield sse_event("similar_cases", {"similar_cases": similar_cases})
            yield sse_event("done", {"filename": file.filename, "case_id": case_id})
        except Exception as e:
            traceback.print_exc()
            yield sse_event("error", {"error": str(e)})
        finally:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as cleanup_error:
                    print(f"⚠️ Cleanup failed: {cleanup_error}", flush=True)
            total_time = time.time() - start_time
            print(f"🎉 process-srr-file stream finished: {total_time:.2f}s", flush=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.post("/api/cases/create")
async def create_case_stream(
    file: UploadFile = File(...),
    force_reprocess: bool = Form(False),
    embedding_provider: Optional[str] = Form(None),
    embedding_model: Optional[str] = Form(None),
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    Agent-style create case stream endpoint.
    Emits SSE events: extracted, summary/summary_chunk/summary_end, similar_cases, done.
    """
    start_time = time.time()
    file_path = None

    def sse_event(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def event_stream():
        nonlocal file_path
        steps_done: List[str] = []
        if embedding_provider or embedding_model:
            set_embedding_override(embedding_provider, embedding_model)
        try:
            if not validate_file_type_extended(file.content_type, file.filename):
                yield sse_event("error", {"error": get_file_type_error_message_extended()})
                return

            processing_type = determine_file_processing_type(file.filename, file.content_type)
            if processing_type == "unknown":
                yield sse_event(
                    "error",
                    {"error": "Unsupported file type or filename format. Supported: TXT files, or PDF files starting with ASD/RCC"},
                )
                return

            file_path = _build_safe_temp_path(file.filename)
            file_content_bytes = b""
            with open(file_path, "wb") as buffer:
                while True:
                    chunk = await file.read(8192)
                    if not chunk:
                        break
                    buffer.write(chunk)
                    file_content_bytes += chunk

            file_hash = calculate_file_hash(file_content_bytes)
            if force_reprocess:
                # Force a fresh record for local validation workflows.
                file_hash = calculate_file_hash(file_content_bytes + uuid4().hex.encode("utf-8"))
            existing_case = None if force_reprocess else db_manager.check_case_duplicate(file_hash)
            if existing_case:
                fields = _normalize_case_fields_for_agent(
                    {k: existing_case.get(k, "") for k in (
                        "A_date_received", "B_source", "C_case_number", "D_type", "E_caller_name", "F_contact_no",
                        "G_slope_no", "H_location", "I_nature_of_request", "J_subject_matter", "K_10day_rule_due_date",
                        "L_icc_interim_due", "M_icc_final_due", "N_works_completion_due", "O1_fax_to_contractor",
                        "O2_email_send_time", "P_fax_pages", "Q_case_details"
                    )}
                )
                yield sse_event(
                    "duplicate",
                    {
                        "filename": file.filename,
                        "status": "duplicate",
                        "message": f"File already processed for case number: {existing_case.get('C_case_number', 'N/A')}",
                        "case_id": existing_case["id"],
                        "fields": fields,
                        "steps_done": ["extract_fields"],
                    },
                )
                return

            loop = asyncio.get_event_loop()
            content, extracted_data, structured_data, case_id, is_new = await loop.run_in_executor(
                None,
                _run_extraction_and_save,
                file_path,
                file.filename,
                processing_type,
                file_hash,
                current_user,
            )
            if is_new:
                case_data_for_vec = getattr(structured_data, "model_dump", lambda: structured_data.dict())()
                asyncio.create_task(_auto_vectorize_new_case(case_id, case_data_for_vec))

            case_data = getattr(structured_data, "model_dump", lambda: structured_data.dict())()
            sd_dict = case_data if isinstance(case_data, dict) else (
                structured_data.model_dump() if hasattr(structured_data, "model_dump") else structured_data.dict()
            )
            fields = _normalize_case_fields_for_agent(sd_dict)
            if (processing_type or "").lower() == "tmo":
                if extracted_data.get("tmo_form_type"):
                    fields["tmo_form_type"] = extracted_data.get("tmo_form_type")
                if extracted_data.get("tmo_form_conflicts") is not None:
                    fields["tmo_form_conflicts"] = extracted_data.get("tmo_form_conflicts")

            steps_done.append("extract_fields")
            yield sse_event(
                "extracted",
                {
                    "fields": fields,
                    "case_id": case_id,
                    "raw_content": content[:50000] if content else "",
                    "steps_done": list(steps_done),
                },
            )

            summary_text = ""
            similar_cases: List[Dict[str, Any]] = []
            try:
                source_type = {
                    "txt": "ICC",
                    "tmo": "TMO",
                    "rcc": "RCC",
                }.get((processing_type or "").lower(), "UNKNOWN")
                task_state = TaskState(
                    task_type="create_case",
                    source_type=source_type,
                    fields=dict(fields or {}),
                    raw_content=content or "",
                    file_path=file_path or "",
                    file_name=file.filename or "",
                    case_id=case_id,
                )
                task_state = await process_case(task_state)
                fields = dict(task_state.fields or {})
                summary_text = task_state.summary or ""
                similar_cases = list(task_state.similar_cases or [])
                steps_done = list(task_state.steps_done or [])

                if task_state.external_data:
                    external_payload = (
                        task_state.external_data.get("external_sources")
                        if isinstance(task_state.external_data, dict)
                        else None
                    )
                    yield sse_event(
                        "external_data",
                        {
                            "external_data": external_payload or task_state.external_data,
                            "steps_done": list(steps_done),
                        },
                    )

                if task_state.department_routing:
                    yield sse_event(
                        "department_routing",
                        {
                            "department_routing": task_state.department_routing,
                            "steps_done": list(steps_done),
                        },
                    )

                multi_payload = (task_state.external_data or {}).get("multi_slope_analysis")
                if multi_payload:
                    yield sse_event("multi_department", multi_payload)

                yield sse_event("summary", {"summary": summary_text, "success": bool(summary_text)})
                yield sse_event("similar_cases", {"similar_cases": similar_cases})

                if case_id:
                    db_manager.update_case_metadata(
                        case_id=case_id,
                        ai_summary=summary_text or None,
                        similar_historical_cases=similar_cases,
                        location_statistics=None,
                        duplicate_detection=(task_state.external_data or {}).get("duplicate_detection"),
                    )
            except Exception as orchestration_err:
                print(f"⚠️ process_case orchestration fallback: {orchestration_err}", flush=True)

            yield sse_event(
                "done",
                {
                    "filename": file.filename,
                    "case_id": case_id,
                    "fields": fields,
                    "summary": summary_text,
                    "steps_done": steps_done,
                },
            )
        except Exception as e:
            traceback.print_exc()
            yield sse_event("error", {"error": str(e)})
        finally:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as cleanup_error:
                    print(f"⚠️ Cleanup failed: {cleanup_error}", flush=True)
            total_time = time.time() - start_time
            print(f"🎉 create-case stream finished: {total_time:.2f}s", flush=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.post("/api/cases/create-from-folder")
async def create_case_from_folder(
    files: List[UploadFile] = File(...),
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    Process case folder: multiple files or a ZIP. Uses file sorter to classify
    (ICC mail, TMO/RCC form, location plan, site photo). Picks core document
    and processes with Vision-parsed attachments when available.
    """
    if not files:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "No files uploaded"},
        )
    file_tuples: List[tuple] = []
    for f in files:
        raw = await f.read()
        file_tuples.append((f.filename or "uploaded", raw))
    docs, manifest = sort_uploaded_files(file_tuples, skip_unknown=True)
    core_doc = None
    location_plans: List[dict] = []
    site_photos: List[dict] = []
    for d in docs:
        cat = d.file_category or "unknown"
        if cat in ("icc_mail", "tmo_rcc_form") and core_doc is None:
            core_doc = d
        elif cat == "location_plan":
            location_plans.append({"file": d.filename, "file_bytes": d.file_bytes})
        elif cat == "site_photo":
            site_photos.append({"file": d.filename, "file_bytes": d.file_bytes})
    if not core_doc:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "No core case document (ICC/TMO/RCC) found in folder",
                "manifest": {
                    "total_files": manifest.total_files,
                    "processed": manifest.processed,
                    "skipped": manifest.skipped,
                },
            },
        )
    try:
        from core.vision_image_parser import parse_image
    except ImportError:
        parse_image = None
    attachments: Dict[str, Any] = {
        "location_plans": [],
        "site_photos": [],
    }
    if parse_image:
        for item in location_plans:
            ext = parse_image(
                "location_plan",
                image_bytes=item.get("file_bytes"),
                filename=item.get("file", ""),
            )
            attachments["location_plans"].append({"file": item.get("file"), "extracted": ext})
        for item in site_photos:
            ext = parse_image(
                "site_photo",
                image_bytes=item.get("file_bytes"),
                filename=item.get("file", ""),
            )
            attachments["site_photos"].append({"file": item.get("file"), "extracted": ext})
    file_path = _build_safe_temp_path(core_doc.filename)
    try:
        with open(file_path, "wb") as buf:
            buf.write(core_doc.file_bytes)
        processing_type = determine_file_processing_type(core_doc.filename, core_doc.content_type)
        if processing_type == "unknown":
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Core document type not supported (TXT or ASD/RCC PDF)"},
            )
        file_hash = calculate_file_hash(core_doc.file_bytes)
        existing = db_manager.check_case_duplicate(file_hash)
        if existing:
            return {
                "status": "duplicate",
                "case_id": existing["id"],
                "message": f"File already processed for case {existing.get('C_case_number', 'N/A')}",
            }
        loop = asyncio.get_event_loop()
        content, extracted_data, structured_data, case_id, is_new = await loop.run_in_executor(
            None,
            _run_extraction_and_save,
            file_path,
            core_doc.filename,
            processing_type,
            file_hash,
            current_user,
        )
        if is_new:
            case_data = getattr(structured_data, "model_dump", lambda: structured_data.dict())()
            asyncio.create_task(_auto_vectorize_new_case(case_id, case_data))
        fields = _normalize_case_fields_for_agent(
            getattr(structured_data, "model_dump", lambda: structured_data.dict())()
        )
        source_type = {"txt": "ICC", "tmo": "TMO", "rcc": "RCC"}.get((processing_type or "").lower(), "UNKNOWN")
        task_state = TaskState(
            task_type="create_case",
            source_type=source_type,
            fields=dict(fields or {}),
            raw_content=content or "",
            file_path=file_path,
            file_name=core_doc.filename or "",
            case_id=case_id,
        )
        task_state.external_data = dict(task_state.external_data or {})
        task_state.external_data["attachments"] = attachments
        task_state = await process_case(task_state)
        return {
            "status": "success",
            "case_id": case_id,
            "fields": dict(task_state.fields or {}),
            "summary": task_state.summary or "",
            "similar_cases": task_state.similar_cases or [],
            "manifest": {
                "total_files": manifest.total_files,
                "processed": manifest.processed,
                "skipped": manifest.skipped,
                "from_zip": manifest.from_zip,
            },
        }
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass


@app.post("/api/user-feedback")
async def save_user_feedback(
    request: UserFeedbackRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """Persist field-level correction feedback for future retrieval."""
    try:
        service = UserFeedbackService()
        saved = await service.save_feedback(
            {
                "case_id": request.case_id,
                "field_name": request.field_name,
                "incorrect_value": request.incorrect_value or "",
                "correct_value": request.correct_value,
                "note": request.note or "",
                "source_text": request.source_text or "",
                "scope": request.scope or "global",
                "user_phone": (current_user or {}).get("phone_number"),
            }
        )
        return {"status": "success", "feedback": saved}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"保存反馈失败: {str(e)}"},
        )


@app.post("/api/process-multiple-files")
async def process_multiple_files(files: List[UploadFile] = File(...)):
    """
    Intelligently batch process multiple SRR case files
    
    Supports intelligent file pairing: automatically identifies TXT case files and corresponding email files for paired processing.
    - TXT file + corresponding emailcontent_*.txt file → Paired processing (includes email information)
    - Standalone TXT file → Independent processing (automatically detects email file)
    - Standalone PDF file → Independent processing
    - Standalone email file → Skip processing
    
    Args:
        files: List of uploaded files
        
    Returns:
        dict: Dictionary containing processing results for all files
        {
            "total_files": Total number of uploaded files,
            "processed_cases": Actual number of processed cases,
            "successful": Number of successfully processed cases,
            "failed": Number of failed cases,
            "skipped": Number of skipped files,
            "results": [
                {
                    "case_id": "Case ID",
                    "main_file": "Main file name",
                    "email_file": "Email file name (if any)",
                    "status": "success|error|skipped",
                    "message": "Processing message",
                    "structured_data": {...} // Only included on success
                },
                ...
            ]
        }
    """
    if not files:
        return {
            "total_files": 0,
            "processed_cases": 0,
            "successful": 0,
            "failed": 0,
            "skipped": 0,
            "results": [{
                "case_id": "none",
                "main_file": "none",
                "email_file": None,
                "status": "error",
                "message": "No files uploaded"
            }]
        }
    
    parsed_docs = await parse_uploaded_documents(files)
    print(f"🚀 Starting intelligent batch processing of {len(parsed_docs)} parsed documents...")
    
    # Step 1: Create intelligent file pairing
    try:
        pairing = SmartFilePairing()
        temp_files = {}
        for doc in parsed_docs:
            if not validate_file_type_extended(doc.content_type, doc.filename):
                print(f"⚠️ Skipping unsupported file type: {doc.filename}")
                continue
            file_path = _build_safe_temp_path(doc.filename)
            with open(file_path, "wb") as buffer:
                buffer.write(doc.file_bytes)
            temp_files[doc.filename] = file_path
            pairing.add_file(doc.filename, doc.content_type)
        processing_summary = pairing.get_processing_summary()
        processing_plan = processing_summary['processing_plan']
    except Exception as setup_e:
        raise
    
    print(f"📋 Intelligent pairing results:")
    print(f"   - Complete pairs: {processing_summary['txt_with_email']} files")
    print(f"   - Standalone TXT: {processing_summary['txt_only']} files")
    print(f"   - Skipped files: {processing_summary['skipped']} files")
    
    # Step 3: Execute according to processing plan
    results = []
    successful_count = 0
    failed_count = 0
    skipped_count = 0
    
    try:
        for i, plan in enumerate(processing_plan, 1):
            case_id = plan['case_id']
            plan_type = plan['type']
            main_file = plan['main_file']
            email_file = plan.get('email_file')
            
            print(f"\n📁 Processing plan {i}/{len(processing_plan)}: {plan['description']}")
            
            if plan_type == 'skip' and getattr(main_file, "is_email", False):
                # Skip standalone email file
                result = {
                    "case_id": case_id,
                    "main_file": main_file.filename,
                    "email_file": None,
                    "status": "skipped",
                    "message": f"Skipping standalone email file (no corresponding TXT file)"
                }
                results.append(result)
                skipped_count += 1
                print(f"⏭️ Skipping file: {main_file.filename}")
                continue
            elif plan_type == 'skip' and not getattr(main_file, "is_email", False):
                # Skip unhandleable file
                result = {
                    "case_id": case_id,
                    "main_file": main_file.filename,
                    "email_file": None,
                    "status": "skipped",
                    "message": f"Skipping unhandleable file "
                }
                results.append(result)
                skipped_count += 1
                print(f"⏭️ Skipping unhandleable file: {main_file.filename}")
                continue
            
            try:
                # Get file path
                main_file_path = temp_files.get(main_file.filename)
                email_file_path = temp_files.get(email_file.filename) if email_file else None
                
                if not main_file_path or not os.path.exists(main_file_path):
                    raise FileNotFoundError(f"Main file does not exist: {main_file.filename}")
                
                # Process based on file type
                if main_file.filename.lower().endswith('.txt'):
                    # Process TXT file (may include email pairing)
                    extracted_data = await process_paired_txt_file(main_file_path, email_file_path)
                    
                elif main_file.filename.lower().endswith('.pdf'):
                    # Process PDF file
                    processing_type = determine_file_processing_type(main_file.filename, main_file.content_type)
                    
                    if processing_type == "tmo":
                        extracted_data = extract_tmo_data(main_file_path)
                    elif processing_type == "rcc":
                        extracted_data = extract_rcc_data(main_file_path)
                    else:
                        raise ValueError(f"Unsupported PDF file type: {main_file.filename}")
                else:
                    raise ValueError(f"Unsupported file format: {main_file.filename}")
                
                # Create structured data
                structured_data = create_structured_data(extracted_data)
                
                # Success result
                result = {
                    "case_id": case_id,
                    "main_file": main_file.filename,
                    "email_file": email_file.filename if email_file else None,
                    "status": "success",
                    "message": f"Case {case_id} processed successfully" + (f" (includes email information)" if email_file else ""),
                    "structured_data": structured_data
                }
                results.append(result)
                successful_count += 1
                print(f"✅ Case {case_id} processed successfully")
        
            except Exception as e:
                # Processing failed
                result = {
                    "case_id": case_id,
                    "main_file": main_file.filename,
                    "email_file": email_file.filename if email_file else None,
                    "status": "error",
                    "message": f"Processing failed: {str(e)}"
                }
                results.append(result)
                failed_count += 1
                print(f"❌ Case {case_id} processing failed: {str(e)}")
    
    except Exception as outer_e:
        print(f"❌ Serious error occurred during batch processing: {str(outer_e)}")
    
    finally:
        # Clean up all temporary files
        for file_path in temp_files.values():
            if os.path.exists(file_path):
                os.remove(file_path)
    
    processed_cases = successful_count + failed_count
    print(f"\n📊 Intelligent batch processing completed:")
    print(f"   - Parsed documents: {len(parsed_docs)} files")
    print(f"   - Processed cases: {processed_cases} cases")
    print(f"   - Successful: {successful_count} cases")
    print(f"   - Failed: {failed_count} cases")
    print(f"   - Skipped: {skipped_count} files")
    
    return {
        "total_files": len(parsed_docs),
        "processed_cases": processed_cases,
        "successful": successful_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "results": results
    }


@app.post("/api/process-multiple-files/stream")
async def process_multiple_files_stream(files: List[UploadFile] = File(...)):
    """
    Batch process multiple SRR case files via SSE.
    Emits: file_result (per file), then batch_done (totals).
    """
    def sse_event(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def event_stream():
        temp_files = {}
        parsed_docs = await parse_uploaded_documents(files)
        if not files:
            yield sse_event("batch_done", {
                "total_files": 0, "processed_cases": 0, "successful": 0, "failed": 0, "skipped": 0,
                "results": [{"case_id": "none", "main_file": "none", "email_file": None, "status": "error", "message": "No files uploaded"}]
            })
            return
        try:
            pairing = SmartFilePairing()
            for doc in parsed_docs:
                if not validate_file_type_extended(doc.content_type, doc.filename):
                    continue
                file_path = _build_safe_temp_path(doc.filename)
                with open(file_path, "wb") as buffer:
                    buffer.write(doc.file_bytes)
                temp_files[doc.filename] = file_path
                pairing.add_file(doc.filename, doc.content_type)
            processing_summary = pairing.get_processing_summary()
            processing_plan = processing_summary['processing_plan']
        except Exception as setup_e:
            yield sse_event("error", {"error": str(setup_e)})
            for file_path in temp_files.values():
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass
            return

        results = []
        successful_count = 0
        failed_count = 0
        skipped_count = 0
        try:
            for i, plan in enumerate(processing_plan, 1):
                case_id = plan['case_id']
                plan_type = plan['type']
                main_file = plan['main_file']
                email_file = plan.get('email_file')

                if plan_type == 'skip' and getattr(main_file, "is_email", False):
                    result = {
                        "case_id": case_id, "main_file": main_file.filename, "email_file": None,
                        "status": "skipped", "message": "Skipping standalone email file (no corresponding TXT file)"
                    }
                    results.append(result)
                    skipped_count += 1
                    yield sse_event("file_result", result)
                    continue
                if plan_type == 'skip' and not getattr(main_file, "is_email", False):
                    result = {
                        "case_id": case_id, "main_file": main_file.filename, "email_file": None,
                        "status": "skipped", "message": "Skipping unhandleable file"
                    }
                    results.append(result)
                    skipped_count += 1
                    yield sse_event("file_result", result)
                    continue

                try:
                    main_file_path = temp_files.get(main_file.filename)
                    email_file_path = temp_files.get(email_file.filename) if email_file else None
                    if not main_file_path or not os.path.exists(main_file_path):
                        raise FileNotFoundError(f"Main file does not exist: {main_file.filename}")

                    if main_file.filename.lower().endswith('.txt'):
                        extracted_data = await process_paired_txt_file(main_file_path, email_file_path)
                    elif main_file.filename.lower().endswith('.pdf'):
                        processing_type = determine_file_processing_type(main_file.filename, main_file.content_type)
                        if processing_type == "tmo":
                            extracted_data = extract_tmo_data(main_file_path)
                        elif processing_type == "rcc":
                            extracted_data = extract_rcc_data(main_file_path)
                        else:
                            raise ValueError(f"Unsupported PDF file type: {main_file.filename}")
                    else:
                        raise ValueError(f"Unsupported file format: {main_file.filename}")

                    structured_data = create_structured_data(extracted_data)
                    sd_dict = getattr(structured_data, 'model_dump', lambda: structured_data.dict())()
                    result = {
                        "case_id": case_id, "main_file": main_file.filename,
                        "email_file": email_file.filename if email_file else None,
                        "status": "success", "message": f"Case {case_id} processed successfully" + (f" (includes email information)" if email_file else ""),
                        "structured_data": sd_dict
                    }
                    results.append(result)
                    successful_count += 1
                    yield sse_event("file_result", result)
                except Exception as e:
                    result = {
                        "case_id": case_id, "main_file": main_file.filename,
                        "email_file": email_file.filename if email_file else None,
                        "status": "error", "message": str(e)
                    }
                    results.append(result)
                    failed_count += 1
                    yield sse_event("file_result", result)
        except Exception as outer_e:
            yield sse_event("error", {"error": str(outer_e)})
        finally:
            for file_path in temp_files.values():
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass

        processed_cases = successful_count + failed_count
        yield sse_event("batch_done", {
            "total_files": len(parsed_docs), "processed_cases": processed_cases,
            "successful": successful_count, "failed": failed_count, "skipped": skipped_count,
            "results": results
        })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# Case management
@app.post("/api/cases/precheck-upload")
async def precheck_case_upload(
    payload: CaseUploadPrecheckRequest,
    current_user: dict = Depends(get_current_user),
):
    role = _user_role(current_user)
    result = db_manager.precheck_case_upload(
        filename=payload.filename,
        file_hash=(payload.file_hash or "").strip() or None,
        user_phone=current_user["phone_number"],
        role=role,
    )
    status = result.get("result", "NOT_FOUND")
    visible = bool(result.get("visible_to_user"))
    if status == "FOUND_SAME_HASH":
        if visible:
            result["message"] = "文件内容已存在，系统可直接复用该 Case。"
        else:
            result["message"] = "文件内容已存在（当前账号不可见）。"
    elif status == "FOUND_SAME_NAME_DIFF_HASH":
        result["message"] = "检测到同名文件，但内容已变化，可按新版本处理。"
    else:
        result["message"] = "未发现重复，可正常上传处理。"
    return {"status": "success", "data": result}


@app.get("/api/cases")
async def get_cases(
    limit: int = 100, 
    offset: int = 0,
    current_user: dict = Depends(get_current_user)
):
    """Get case list (requires authentication)"""
    cases = db_manager.get_cases_for_user(
        user_phone=current_user["phone_number"],
        role=_user_role(current_user),
        limit=limit,
        offset=offset
    )
    return {"cases": cases, "total": len(cases)}

@app.get("/api/cases/{case_id}")
async def get_case(case_id: int, current_user: dict = Depends(get_current_user)):
    """Get single case"""
    case = db_manager.get_case_for_user(
        case_id=case_id,
        user_phone=current_user["phone_number"],
        role=_user_role(current_user)
    )
    if case:
        return case
    return JSONResponse(status_code=404, content={"status": "error", "message": "Case does not exist or forbidden"})


@app.get("/api/cases/{case_id}/details")
async def get_case_details(
    case_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Get case with full details: basic info, processing info, conversations (draft replies), attachments (original file info)"""
    case = db_manager.get_case_for_user(
        case_id=case_id,
        user_phone=current_user["phone_number"],
        role=_user_role(current_user)
    )
    if not case:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Case does not exist or forbidden"})
    conversations = db_manager.get_conversations_by_case_for_user(
        case_id=case_id,
        user_phone=current_user["phone_number"],
        role=_user_role(current_user)
    )
    return {
        "case": case,
        "conversations": conversations,
        "attachments": [{"name": case.get("original_filename", ""), "type": case.get("file_type", ""), "note": "源案件文件"}]
    }

@app.get("/api/cases/search")
async def search_cases(q: str, current_user: dict = Depends(get_current_user)):
    """Search cases"""
    cases = db_manager.search_cases_for_user(
        keyword=q,
        user_phone=current_user["phone_number"],
        role=_user_role(current_user)
    )
    return {"cases": cases, "query": q}

def _ensure_hybrid_search_service():
    """Initialize hybrid search service on first use."""
    try:
        from services.hybrid_search_service import get_hybrid_search_service
        return get_hybrid_search_service()
    except RuntimeError:
        from services.historical_case_matcher import get_historical_matcher
        from services.hybrid_search_service import init_hybrid_search_service
        matcher = get_historical_matcher()
        vector_client = PgVectorStore()
        init_hybrid_search_service(vector_client, matcher)
        from services.hybrid_search_service import get_hybrid_search_service
        return get_hybrid_search_service()


@app.post("/api/find-similar-cases")
async def find_similar_cases(case_data: dict, current_user: dict = Depends(get_current_user)):
    """
    Find similar historical cases (hybrid: vector recall + weighted rerank).
    Falls back to weight-only search if vector store is empty. Results cached (max 100).
    """
    try:
        from services.historical_case_matcher import get_historical_matcher
        from services.search_cache import get_cached_response, set_cached_response

        limit = case_data.get("limit", 10)
        min_similarity = case_data.get("min_similarity", 0.3)
        cached = get_cached_response(case_data, limit, min_similarity)
        if cached is not None:
            return cached

        similar_cases = []
        used_hybrid = False

        try:
            hybrid = _ensure_hybrid_search_service()
            similar_cases = await hybrid.find_similar_cases(
                current_case=case_data,
                limit=limit,
                min_similarity=min_similarity,
            )
            if similar_cases:
                used_hybrid = True
        except Exception as hybrid_err:
            print(f"Hybrid search skipped: {hybrid_err}", flush=True)

        if not similar_cases:
            matcher = get_historical_matcher()
            similar_cases = matcher.find_similar_cases(
                current_case=case_data,
                limit=limit,
                min_similarity=min_similarity,
            )

        response = {
            "status": "success",
            "current_case_number": case_data.get("C_case_number"),
            "total_found": len(similar_cases),
            "similar_cases": similar_cases,
            "search_criteria": {
                "case_number": case_data.get("C_case_number"),
                "location": case_data.get("H_location"),
                "slope_no": case_data.get("G_slope_no"),
                "caller_name": case_data.get("E_caller_name"),
                "subject_matter": case_data.get("J_subject_matter"),
            },
            "data_sources": {
                "slopes_complaints_2021": "~2,893 cases",
                "srr_data_2021_2024": "~1,251 cases",
                "total_searchable": "~4,144 historical cases (PostgreSQL)",
            },
            "search_method": "hybrid (vector recall + weighted rerank)" if used_hybrid else "weighted only",
        }
        set_cached_response(case_data, limit, min_similarity, response)
        return response
    except Exception:
        traceback.print_exc()
        return {"status": "error", "message": "Failed to find similar cases"}


@app.get("/api/search-cache-stats")
async def get_search_cache_stats():
    """Return similar-case search cache stats for monitoring."""
    try:
        from services.search_cache import cache_stats
        return {"status": "success", "cache": cache_stats()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def _auto_vectorize_new_case(case_id: int, case_data: dict) -> None:
    """Add a new case to historical_cases_vectors for hybrid search (fire-and-forget safe)."""
    try:
        from src.core.embedding import embed_text
        parts = [
            f"Case ID: {case_id}." if case_id else "",
            case_data.get("C_case_number") or "",
            case_data.get("H_location") or "",
            case_data.get("G_slope_no") or "",
            case_data.get("J_subject_matter") or "",
            case_data.get("I_nature_of_request") or "",
            case_data.get("E_caller_name") or "",
        ]
        content = " ".join(p for p in parts if p).strip() or "case"
        content = content[:2000]
        vector = embed_text(content)
        client = PgVectorStore()
        slope_no = case_data.get("G_slope_no") or ""
        await client.add_to_collection(PgVectorStore.COLLECTION_HISTORICAL_CASES, {
            "case_id": str(case_id),
            "case_number": case_data.get("C_case_number") or "",
            "location": case_data.get("H_location") or "",
            "slope_no": slope_no,
            "content": content,
            "vector": vector,
            "source": "new_case",
            "metadata": {"knowledge_type": "case", "entity_id": slope_no},
        })
        print(f"✅ New case {case_id} auto-vectorized for hybrid search", flush=True)
    except Exception as e:
        print(f"⚠️ Auto-vectorize skipped for case {case_id}: {e}", flush=True)


async def _build_enhanced_chat_context(query: str, raw_content: str, context: dict):
    """
    Multi-source parallel retrieval: historical cases, tree inventory, knowledge docs.
    Returns (context_string, retrieval_metrics) where retrieval_metrics carry
    the original pgvector cosine similarity scores.
    """
    def _make_metric(source: str, doc: dict, idx: int) -> dict:
        content = (doc.get("content") or "").strip()
        similarity = float(doc.get("similarity", 0.0) or 0.0)
        return {
            "source": source,
            "doc_id": str(doc.get("case_id") or doc.get("case_number") or f"{source}-{idx}"),
            "doc_title": content[:80],
            "similarity_score": round(similarity, 4),
            "relevance_score": round(similarity, 4),
            "used_in_answer": False,
            "snippet": content[:320],
        }

    try:
        vector_store = PgVectorStore()
        search_query = f"Query: {query}\nRaw Content: {raw_content}" if raw_content else query
        ctx = context or {}
        location = (ctx.get("H_location") or "").strip() or None
        slope_no = (ctx.get("G_slope_no") or "").strip() or None

        resolver = TreeIDResolver()
        if not slope_no and query:
            # 方案 A: 从 query 提取 slope 编号（如 11SW-A/FR24(3)）
            extracted = extract_slope_from_query(query)
            if extracted:
                slope_no = extracted
            else:
                slope_id_match = re.search(r"\b(SA\d+)\b", query, re.IGNORECASE)
                if slope_id_match:
                    slope_id = slope_id_match.group(1).upper()
                    resolved = resolver.resolve_slope_no(slope_id)
                    if resolved:
                        slope_no = resolved

        # 规范化 slope_no：去掉末尾 (N)，使 11SW-A/FR24(3) 与 11SW-A/FR24 匹配
        if slope_no:
            slope_no = normalize_slope_core(slope_no) or slope_no

        tree_no = resolver.extract_tree_no(query) if query else None

        query_lower = query.lower()
        need_tree = bool(
            slope_no or location or "tree" in query_lower or "树" in query_lower
            or "樹" in query_lower or "樹木" in query_lower
        )
        external_data = {"smris": None, "cedd": None, "weather": []}
        if EXTERNAL_API_ENABLED and slope_no:
            try:
                external_data = await ExternalDataService().query_all(slope_no)
            except Exception:
                external_data = {"smris": None, "cedd": None, "weather": []}

        config = get_adaptive_rag_config()
        async def _historical():
            try:
                filters = {}
                if slope_no:
                    filters["slope_no"] = slope_no
                if location and "slope_no" not in filters:
                    filters["location"] = location
                filters = filters if filters else None
                return await vector_store.retrieve_from_collection(
                    PgVectorStore.COLLECTION_HISTORICAL_CASES,
                    search_query, config.max_historical_docs, filters=filters
                )
            except Exception:
                return []

        async def _trees():
            if not need_tree:
                return []
            try:
                filters = None
                if slope_no:
                    filters = {"slope_no": slope_no}
                    if tree_no:
                        filters["tree_no"] = tree_no
                elif location:
                    filters = {"location": location}
                return await vector_store.retrieve_from_collection(
                    PgVectorStore.COLLECTION_TREE_INVENTORY,
                    search_query, config.max_tree_docs, filters=filters
                )
            except Exception:
                return []

        async def _knowledge():
            try:
                return await vector_store.retrieve_from_collection(
                    PgVectorStore.COLLECTION_KNOWLEDGE_DOCS,
                    search_query, config.max_knowledge_docs
                )
            except Exception:
                return []

        async def _feedback():
            try:
                return await UserFeedbackService().retrieve_feedback(
                    search_query, top_k=5, min_similarity=max(config.min_score_knowledge, 0.25)
                )
            except Exception:
                return []

        results = await asyncio.gather(
            _historical(),
            _trees(),
            _knowledge(),
            _feedback(),
            return_exceptions=True,
        )
        historical = results[0] if not isinstance(results[0], Exception) else []
        trees = results[1] if not isinstance(results[1], Exception) else []
        knowledge = results[2] if not isinstance(results[2], Exception) else []
        feedback = results[3] if not isinstance(results[3], Exception) else []

        if slope_no and tree_no and need_tree:
            direct_tree = resolver.lookup_tree(slope_no, tree_no)
            if direct_tree:
                from services.tree_inventory_content_service import build_tree_content
                direct_content = build_tree_content(direct_tree)
                trees = [{"content": direct_content, "similarity": 1.0}]

        thresh_hist = config.min_score_historical
        thresh_tree = config.min_score_tree
        thresh_kb = config.min_score_knowledge

        parts = []
        retrieval_metrics = []
        metric_idx = 0

        if historical:
            hist_lines = []
            for c in historical:
                if c.get("similarity", 0) <= thresh_hist:
                    continue
                content = c.get("content") or ""
                case_id = c.get("case_id") or c.get("case_number") or ""
                if case_id:
                    hist_lines.append(f"[Case ID: {case_id}] {content}")
                else:
                    hist_lines.append(content)
                metric_idx += 1
                retrieval_metrics.append(_make_metric("historical_cases", c, metric_idx))
            if hist_lines:
                parts.append("=== Relevant historical cases ===\n" + "\n".join(hist_lines))

        if trees:
            tree_lines = [
                c["content"] for c in trees
                if c.get("similarity", 0) > thresh_tree
            ]
            accepted_trees = [
                c for c in trees
                if c.get("similarity", 0) > thresh_tree
            ]
            if tree_lines:
                parts.append("=== Tree inventory ===\n" + "\n".join(tree_lines))
                for c in accepted_trees:
                    metric_idx += 1
                    retrieval_metrics.append(_make_metric("tree_inventory", c, metric_idx))
            elif trees:
                top_trees = sorted(trees, key=lambda x: x.get("similarity", 0), reverse=True)[:2]
                if top_trees and top_trees[0].get("similarity", 0) > 0.2:
                    parts.append("=== Tree inventory ===\n" + "\n".join(
                        c["content"] for c in top_trees
                    ))
                    for c in top_trees:
                        metric_idx += 1
                        retrieval_metrics.append(_make_metric("tree_inventory", c, metric_idx))
        elif need_tree:
            try:
                fallback_chunks = await vector_store.retrieve_similar_sync(search_query, 12)
                tree_like = [
                    c for c in fallback_chunks
                    if c.get("similarity", 0) > thresh_tree
                    and ("tree" in (c.get("content") or "").lower() or "树" in (c.get("content") or ""))
                ][:3]
                if tree_like:
                    parts.append("=== Tree inventory (fallback) ===\n" + "\n".join(
                        c["content"] for c in tree_like
                    ))
                    for c in tree_like:
                        metric_idx += 1
                        retrieval_metrics.append(_make_metric("tree_inventory", c, metric_idx))
            except Exception:
                pass

        if knowledge:
            accepted_kb = [
                c for c in knowledge
                if c.get("similarity", 0) > thresh_kb
            ]
            if accepted_kb:
                parts.append("=== Reference knowledge ===\n" + "\n".join(
                    c["content"] for c in accepted_kb
                ))
                for c in accepted_kb:
                    metric_idx += 1
                    retrieval_metrics.append(_make_metric("knowledge_base", c, metric_idx))

        if feedback:
            feedback_lines = []
            for c in feedback:
                content = (c.get("content") or "").strip()
                if not content:
                    continue
                feedback_lines.append(content)
                metric_idx += 1
                retrieval_metrics.append(_make_metric("user_feedback", c, metric_idx))
            if feedback_lines:
                parts.append(
                    "=== User feedback corrections (high priority constraints) ===\n"
                    + "\n---\n".join(feedback_lines[:5])
                )

        external_lines = []
        if external_data.get("smris"):
            smris = external_data["smris"]
            external_lines.append(
                f"Slope {smris.get('slope_no', slope_no)} responsibility: "
                f"{smris.get('maintenance_responsible', 'unknown')}"
            )
        if external_data.get("cedd"):
            cedd = external_data["cedd"]
            external_lines.append(
                f"CEDD slope metadata: district={cedd.get('district', '')}, "
                f"type={cedd.get('slope_type', '')}, location={cedd.get('location', '')}"
            )
        weather_warnings = external_data.get("weather") or []
        if weather_warnings:
            top_codes = ", ".join(w.get("code", "") for w in weather_warnings[:3] if w.get("code"))
            if top_codes:
                external_lines.append(f"HKO active warnings: {top_codes}")
        if external_lines:
            parts.append("=== External data ===\n" + "\n".join(f"- {line}" for line in external_lines))

        his_context = "\n\n".join(parts)
        if historical or trees or knowledge or feedback:
            print(
                "✅ Multi-source retrieval: "
                f"{len(historical)} cases, {len(trees)} trees, {len(knowledge)} docs, {len(feedback)} feedback",
                flush=True,
            )
        return his_context, retrieval_metrics
    except Exception as e:
        print(f"⚠️ Enhanced context unavailable: {e}", flush=True)
        return "", []


OPENAI_MODEL_LIST = ["gpt-4o-mini", "gpt-4o"]


def _is_embedding_model(name: str) -> bool:
    """Exclude embedding models; chat dropdown should only show language models."""
    n = (name or "").lower()
    if "embed" in n:
        return True
    if "all-minilm" in n or "minilm" in n:
        return True
    if "bge-" in n or n.startswith("bge"):
        return True
    return False


@app.get("/api/llm-models")
async def get_llm_models():
    """
    Return available chat models: OpenAI (fixed list) and Ollama (from local Ollama API).
    Ollama: filters out embedding models (e.g. nomic-embed-text), only returns language/chat models.
    """
    result = {"openai": OPENAI_MODEL_LIST, "ollama": []}
    try:
        import httpx
        url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags"
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url)
            if r.status_code == 200:
                data = r.json()
                models = data.get("models") or []
                # Exclude embedding models; only include chat/generate models
                result["ollama"] = [
                    m.get("name", "").strip()
                    for m in models
                    if m.get("name") and not _is_embedding_model(m.get("name", ""))
                ]
    except Exception as e:
        print(f"⚠️ Ollama models unavailable: {e}", flush=True)
    return result


@app.get("/api/embedding-config")
async def get_embedding_config():
    """
    Return available embedding providers and models.
    Used by frontend embedding model selector.
    """
    result = {
        "provider": EMBEDDING_PROVIDER,
        "model": OPENAI_EMBED_MODEL if EMBEDDING_PROVIDER == "openai" else OLLAMA_EMBED_MODEL,
        "openai": OPENAI_EMBED_MODELS,
        "ollama": list(OLLAMA_EMBED_MODELS),
    }
    try:
        import httpx
        url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags"
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url)
            if r.status_code == 200:
                data = r.json()
                models = data.get("models") or []
                embed_names = [
                    m.get("name", "").strip()
                    for m in models
                    if m.get("name") and _is_embedding_model(m.get("name", ""))
                ]
                if embed_names:
                    result["ollama"] = list(set(OLLAMA_EMBED_MODELS) | set(embed_names))
    except Exception:
        pass
    return result


@app.post("/api/chat/stream")
async def chatClientStream(Request: ChatRequest):
    """
    Chat with the case management system (SSE streaming), enhanced with multi-source retrieval.
    Returns Server-Sent Events: data: {"text": "chunk"}\n\n
    """
    import json as json_mod

    def _chat_stream_chunks(
        query: str,
        context_str: str,
        raw_content_str: str,
        his_context: str,
        model: Optional[str],
        provider: Optional[str],
    ):
        llm_service = get_llm_service()
        return llm_service.chat_stream(
            query,
            context_str,
            raw_content_str,
            his_context,
            model=model,
            provider=provider,
        )

    async def legacy_event_stream():
        if Request.embedding_provider or Request.embedding_model:
            set_embedding_override(Request.embedding_provider, Request.embedding_model)
        his_context = await _build_enhanced_chat_context(
            Request.query, Request.raw_content or "", Request.context or {}
        )
        if not his_context:
            try:
                vector_store = PgVectorStore()
                search_query = (
                    f"Query: {Request.query}\nRaw Content: {Request.raw_content}"
                    if Request.raw_content
                    else Request.query
                )
                similar_cases = await vector_store.retrieve_similar_sync(search_query, 10)
                his_context = "\n".join([c["content"] for c in similar_cases if c.get("similarity", 0) > 0.5])
            except Exception:
                pass
        sync_chunk_queue = queue.Queue()
        loop = asyncio.get_event_loop()

        def run_chat_stream():
            try:
                context_str = json_mod.dumps(Request.context) if Request.context else "{}"
                raw_content_str = Request.raw_content if Request.raw_content else ""
                for chunk in _chat_stream_chunks(
                    Request.query,
                    context_str,
                    raw_content_str,
                    his_context,
                    Request.model,
                    Request.provider,
                ):
                    if chunk:
                        sync_chunk_queue.put(chunk)
            except Exception as e:
                sync_chunk_queue.put(("error", str(e)))
            finally:
                sync_chunk_queue.put(None)

        loop.run_in_executor(None, run_chat_stream)
        try:
            while True:
                item = await asyncio.get_event_loop().run_in_executor(None, sync_chunk_queue.get)
                if item is None:
                    break
                if isinstance(item, tuple) and item[0] == "error":
                    err_payload = json_mod.dumps({"error": item[1]})
                    yield f"data: {err_payload}\n\n"
                    break
                payload = json_mod.dumps({"text": item})
                yield f"data: {payload}\n\n"
        except Exception as e:
            err_payload = json_mod.dumps({"error": str(e)})
            yield f"data: {err_payload}\n\n"

    async def agent_event_stream():
        tools = AgentTooling(
            build_context=_build_enhanced_chat_context,
            chat_stream=_chat_stream_chunks,
        )
        emitted_text_or_error = False
        try:
            async for event in stream_chat_events(Request, tools):
                if isinstance(event, dict) and ("text" in event or "error" in event):
                    emitted_text_or_error = True
                yield f"data: {json_mod.dumps(event)}\n\n"
            # Backward-compatible SSE contract:
            # legacy consumers (including smoke tests) expect at least one text/error payload.
            if not emitted_text_or_error:
                yield f"data: {json_mod.dumps({'text': ''})}\n\n"
        except Exception as e:
            err_payload = json_mod.dumps({"error": str(e)})
            yield f"data: {err_payload}\n\n"

    event_stream = agent_event_stream if FEATURE_AGENT_ROUTER else legacy_event_stream

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/api/case-statistics")
async def get_case_statistics(
    location: str = None,
    slope_no: str = None,
    venue: str = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Get comprehensive statistics from historical cases (stored in PostgreSQL).
    Searches across:
    - Slopes Complaints 2021 (~2,893 cases)
    - SRR data 2021-2024 (~1,251 cases)
    Total: ~4,144 historical cases

    Query parameters:
        location: Location to filter by
        slope_no: Slope number to filter by
        venue: Venue name to filter by

    Returns:
        dict: Comprehensive statistics from historical data only
    """
    try:
        # Use the same module path as in startup_event to ensure the
        # global matcher singleton is shared and properly initialized
        from services.historical_case_matcher import get_historical_matcher
        
        matcher = get_historical_matcher()
        
        stats = matcher.get_case_statistics(
            location=location,
            slope_no=slope_no,
            venue=venue
        )
        
        return {
            "status": "success",
            "statistics": stats
        }
        
    except Exception:
        traceback.print_exc()
        return {
            "status": "error",
            "message": "Failed to get statistics"
        }


@app.get("/api/tree-info")
async def get_tree_info(slope_no: str, current_user: dict = Depends(get_current_user)):
    """
    Get tree information for a specific slope
    Searches tree inventory (32405 trees)
    
    Query parameters:
        slope_no: Slope number to search for
        
    Returns:
        dict: List of trees on the slope with details
    """
    try:
        # Use the same module path as in startup_event to ensure the
        # global matcher singleton is shared and properly initialized
        from services.historical_case_matcher import get_historical_matcher
        
        matcher = get_historical_matcher()
        trees = matcher.get_tree_info(slope_no)
        
        return {
            "status": "success",
            "slope_no": slope_no,
            "total_trees": len(trees),
            "trees": trees
        }
        
    except Exception:
        traceback.print_exc()
        return {
            "status": "error",
            "message": "Failed to get tree information"
        }


@app.get("/api/location-slopes")
async def get_location_slopes(location: str, current_user: dict = Depends(get_current_user)):
    """
    Get slope numbers associated with a location
    Uses historical learning from ~4,144 cases (PostgreSQL)
    
    Query parameters:
        location: Location name or partial match
        
    Returns:
        dict: List of slope numbers found at this location
    """
    try:
        # Use the same module path as in startup_event to ensure the
        # global matcher singleton is shared and properly initialized
        from services.historical_case_matcher import get_historical_matcher
        
        matcher = get_historical_matcher()
        slopes = matcher.get_slopes_for_location(location)
        
        return {
            "status": "success",
            "location": location,
            "total_slopes": len(slopes),
            "slopes": slopes,
            "note": "Learned from historical complaint records"
        }
        
    except Exception:
        traceback.print_exc()
        return {
            "status": "error",
            "message": "Failed to get slopes for location"
        }


# ======================= Reply Draft Generation Endpoints =======================

class ReplyDraftRequest(BaseModel):
    """回复草稿生成请求模型"""
    case_id: int
    reply_type: str  # interim, final, wrong_referral
    conversation_id: int = None
    user_message: str = None
    is_initial: bool = False
    skip_questions: bool = False  # 是否跳过询问直接生成


class UpdateDraftRequest(BaseModel):
    draft_reply: str


def _populate_draft_signature(draft_text: Optional[str], current_user: dict) -> str:
    """Fill common signature placeholders using current user info."""
    text = draft_text or ""
    if not text.strip():
        return text
    full_name = (current_user or {}).get("full_name") or "-"
    position = (current_user or {}).get("department") or (current_user or {}).get("role") or "-"
    phone = (current_user or {}).get("phone_number")
    email = (current_user or {}).get("email")
    contact_parts = []
    if phone:
        contact_parts.append(f"Tel: {phone}")
    if email:
        contact_parts.append(f"Email: {email}")
    contact_info = " | ".join(contact_parts) if contact_parts else "-"
    today = time.strftime("%d %B %Y")

    replacements = {
        r"\[\s*Your\s*Name\s*\]": str(full_name),
        r"\[\s*Your\s*Position\s*\]": str(position),
        r"\[\s*Contact\s*Information\s*\]": str(contact_info),
        r"\[\s*Date\s*\]": today,
    }
    for pattern, value in replacements.items():
        text = re.sub(pattern, value, text, flags=re.IGNORECASE)
    return text


@app.post("/api/generate-reply-draft")
async def generate_reply_draft(request: ReplyDraftRequest, current_user: dict = Depends(get_current_user)):
    """
    生成回复草稿或询问补充信息
    
    支持三种回复类型：
    - interim: 过渡回复
    - final: 最终回复
    - wrong_referral: 错误转介回复
    
    流程：
    1. 首次请求：返回询问补充资料的问题
    2. 后续请求：根据用户提供的信息生成草稿回复
    
    Args:
        request: ReplyDraftRequest对象
    
    Returns:
        dict: 包含对话ID、消息内容、是否为询问、草稿回复等信息
    """
    try:
        # 验证回复类型
        valid_types = ['interim', 'final', 'wrong_referral']
        if request.reply_type not in valid_types:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": f"Invalid reply_type. Must be one of: {', '.join(valid_types)}"
                }
            )
        
        # 获取案件数据
        case_data = db_manager.get_case(request.case_id)
        if not case_data:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "error",
                    "message": f"Case not found: {request.case_id}"
                }
            )
        
        # 获取模板内容：优先从 KnowledgeBase 读取，无则回退到 docs/templates
        template_content = None
        if _knowledge_base_service is not None:
            template_content = _knowledge_base_service.get_template_content_by_slot(request.reply_type)
        if not template_content:
            template_loader = get_template_loader()
            template_content = template_loader.load_template(request.reply_type)
        if not template_content:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Failed to load template for {request.reply_type}"
                }
            )
        
        # Use English for UI; detect language only from user message when in conversation
        language = 'en'
        if request.user_message:
            language = detect_language(request.user_message)
        
        # 获取或创建对话历史
        conversation_id = request.conversation_id
        conversation_history = []
        
        if conversation_id:
            # 获取现有对话
            conversation = db_manager.get_conversation_for_user(
                conversation_id=conversation_id,
                user_phone=current_user["phone_number"],
                role=_user_role(current_user)
            )
            if conversation:
                conversation_history = conversation.get('messages', [])
            else:
                return JSONResponse(
                    status_code=404,
                    content={
                        "status": "error",
                        "message": f"Conversation not found: {conversation_id}"
                    }
                )
        else:
            # 创建新对话
            conversation_data = {
                'case_id': request.case_id,
                'user_phone': current_user["phone_number"],
                'conversation_type': f"{request.reply_type}_reply",
                'language': language,
                'status': 'in_progress'
            }
            conversation_id = db_manager.save_conversation(conversation_data)
        
        # 调用LLM服务生成回复
        llm_service = get_llm_service()
        result = llm_service.generate_reply_draft(
            reply_type=request.reply_type,
            case_data=case_data,
            template_content=template_content,
            conversation_history=conversation_history,
            user_message=request.user_message,
            language=language,
            is_initial=request.is_initial,
            skip_questions=request.skip_questions
        )
        
        if not result:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": "Failed to generate reply draft"
                }
            )
        
        # 保存消息到对话历史
        if request.user_message and not request.is_initial:
            # 保存用户消息
            db_manager.add_message_to_conversation(
                conversation_id, 'user', request.user_message, language
            )
        
        # Normalize signature placeholders with current user info
        if result.get('draft_reply'):
            normalized_draft = _populate_draft_signature(result.get('draft_reply'), current_user)
            result['draft_reply'] = normalized_draft
            result['message'] = normalized_draft

        # 保存AI回复
        db_manager.add_message_to_conversation(
            conversation_id, 'assistant', result['message'], language
        )
        
        # 如果生成了草稿，更新对话状态
        if result.get('draft_reply'):
            db_manager.update_conversation(conversation_id, {
                'draft_reply': result['draft_reply'],
                'status': 'completed'
            })
        
        return {
            "status": "success",
            "conversation_id": conversation_id,
            "message": result['message'],
            "is_question": result['is_question'],
            "draft_reply": result.get('draft_reply'),
            "language": language,
            "reply_slip_selections": result.get("reply_slip_selections", {}),
            "deadline": result.get("deadline"),
        }
        
    except Exception:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Reply draft generation failed"
            }
        )


@app.post("/api/generate-reply-draft/stream")
async def generate_reply_draft_stream(request: ReplyDraftRequest, current_user: dict = Depends(get_current_user)):
    """
    Stream reply draft generation via SSE.
    Use when skip_questions=True (direct generate) or is_initial=False (generating from user answer).
    """
    import json as json_mod
    try:
        valid_types = ['interim', 'final', 'wrong_referral']
        if request.reply_type not in valid_types:
            return JSONResponse(status_code=400, content={"status": "error", "message": f"Invalid reply_type"})
        case_data = db_manager.get_case(request.case_id)
        if not case_data:
            return JSONResponse(status_code=404, content={"status": "error", "message": "Case not found"})
        template_content = None
        if _knowledge_base_service is not None:
            template_content = _knowledge_base_service.get_template_content_by_slot(request.reply_type)
        if not template_content:
            template_loader = get_template_loader()
            template_content = template_loader.load_template(request.reply_type)
        if not template_content:
            return JSONResponse(status_code=500, content={"status": "error", "message": "Failed to load template"})
        language = 'en'
        if request.user_message:
            language = detect_language(request.user_message)
        conversation_id = request.conversation_id
        conversation_history = []
        if conversation_id:
            conv = db_manager.get_conversation_for_user(
                conversation_id=conversation_id,
                user_phone=current_user["phone_number"],
                role=_user_role(current_user)
            )
            if conv:
                conversation_history = conv.get('messages', [])
            else:
                return JSONResponse(status_code=404, content={"status": "error", "message": "Conversation not found"})
        else:
            conv_data = {
                'case_id': request.case_id,
                'user_phone': current_user["phone_number"],
                'conversation_type': f"{request.reply_type}_reply",
                'language': language,
                'status': 'in_progress'
            }
            conversation_id = db_manager.save_conversation(conv_data)
        user_msg = request.user_message or ""
        if request.skip_questions:
            user_msg = ""
        if request.user_message and not request.is_initial:
            db_manager.add_message_to_conversation(conversation_id, 'user', request.user_message, language)
        llm_service = get_llm_service()
        full_draft = []

        async def event_stream():
            try:
                yield f"data: {json_mod.dumps({'type': 'meta', 'conversation_id': conversation_id})}\n\n"
                for chunk in llm_service.generate_reply_draft_stream(
                    request.reply_type, case_data, template_content,
                    conversation_history, user_msg, language
                ):
                    if chunk:
                        full_draft.append(chunk)
                        yield f"data: {json_mod.dumps({'type': 'text', 'text': chunk})}\n\n"
                    await asyncio.sleep(0)
                draft_text = ''.join(full_draft).strip()
                if draft_text:
                    draft_text = _populate_draft_signature(draft_text, current_user)
                    db_manager.add_message_to_conversation(conversation_id, 'assistant', draft_text, language)
                    db_manager.update_conversation(conversation_id, {'draft_reply': draft_text, 'status': 'completed'})
                yield f"data: {json_mod.dumps({'type': 'done', 'conversation_id': conversation_id})}\n\n"
            except Exception:
                traceback.print_exc()
                yield f"data: {json_mod.dumps({'type': 'error', 'error': 'Reply draft stream failed'})}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
    except Exception:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Reply draft stream failed"}
        )


@app.get("/api/conversation/{conversation_id}")
async def get_conversation(conversation_id: int, current_user: dict = Depends(get_current_user)):
    """
    获取对话历史
    
    Args:
        conversation_id: 对话ID
    
    Returns:
        dict: 对话历史数据
    """
    try:
        conversation = db_manager.get_conversation_for_user(
            conversation_id=conversation_id,
            user_phone=current_user["phone_number"],
            role=_user_role(current_user)
        )
        if not conversation:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "error",
                    "message": f"Conversation not found: {conversation_id}"
                }
            )
        
        return {
            "status": "success",
            "conversation": conversation
        }
        
    except Exception:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Failed to get conversation"
            }
        )


@app.delete("/api/conversation/{conversation_id}/draft")
async def delete_conversation_draft(conversation_id: int, current_user: dict = Depends(get_current_user)):
    """Clear the draft reply for a conversation. Does not delete the conversation or message history."""
    try:
        conversation = db_manager.get_conversation_for_user(
            conversation_id=conversation_id,
            user_phone=current_user["phone_number"],
            role=_user_role(current_user)
        )
        if not conversation:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": f"Conversation not found: {conversation_id}"}
            )
        db_manager.update_conversation(conversation_id, {"draft_reply": None})
        return {"status": "success", "message": "Draft deleted"}
    except Exception:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Failed to delete conversation draft"}
        )


@app.put("/api/conversation/{conversation_id}/draft")
async def update_conversation_draft(
    conversation_id: int,
    request: UpdateDraftRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update and save a draft reply for a conversation."""
    try:
        conversation = db_manager.get_conversation_for_user(
            conversation_id=conversation_id,
            user_phone=current_user["phone_number"],
            role=_user_role(current_user)
        )
        if not conversation:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": f"Conversation not found: {conversation_id}"}
            )
        normalized_draft = _populate_draft_signature(request.draft_reply, current_user)
        db_manager.update_conversation(conversation_id, {"draft_reply": normalized_draft, "status": "completed"})
        return {"status": "success", "draft_reply": normalized_draft}
    except Exception:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Failed to update conversation draft"}
        )


@app.post("/api/conversation/{conversation_id}/approve-draft-to-kb")
async def approve_draft_to_knowledge_base(
    conversation_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Approve a draft reply as a knowledge base source for RAG retrieval."""
    try:
        conversation = db_manager.get_conversation_for_user(
            conversation_id=conversation_id,
            user_phone=current_user["phone_number"],
            role=_user_role(current_user)
        )
        if not conversation:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": f"Conversation not found: {conversation_id}"}
            )
        draft = conversation.get("draft_reply") or ""
        if not draft.strip():
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "No draft reply to approve"}
            )
        if conversation.get("draft_approved_to_kb"):
            return {"status": "success", "message": "Already approved", "data": {"already_approved": True}}

        from src.services.embedding_service import generate_embedding
        vector_store = PgVectorStore()
        content = draft.strip()[:8000]
        embeddings = generate_embedding([content])
        rec = {
            "doc_type": "draft_reply",
            "filename": f"conv_{conversation_id}",
            "content": content,
            "vector": embeddings[0],
            "approved": True,
        }
        await vector_store.add_to_collection(PgVectorStore.COLLECTION_KNOWLEDGE_DOCS, rec)
        db_manager.update_conversation(conversation_id, {"draft_approved_to_kb": True})
        return {"status": "success", "message": "Draft approved as knowledge base source"}
    except Exception:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Failed to approve draft to knowledge base"}
        )


# ============== RAG Knowledge Base File Management Endpoints ==============

def _sync_extract_chunk_embed(full_path: str, file_type: str):
    """Sync helper for background task: extract text, split, embed (batched). Runs in thread pool."""
    from utils.file_processors import process_file
    text_content = process_file(full_path, file_type)
    chunk_size = 1500
    chunk_overlap = 150
    text_chunks = split_text(text_content, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    for _ in range(50):
        if len(text_chunks) <= MAX_RAG_CHUNKS:
            break
        chunk_size = max(chunk_size + 500, int(len(text_content) / MAX_RAG_CHUNKS) + chunk_overlap)
        text_chunks = split_text(text_content, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    embeddings = embed_texts(text_chunks)
    return (text_chunks, embeddings)


async def _process_rag_file_background(
    file_id: int,
    full_path: str,
    relative_path: str,
    file_type: str,
    file_size: int,
    content_type: str,
    filename: str,
    embedding_provider: Optional[str] = None,
    embedding_model: Optional[str] = None,
):
    """Background task: extract → chunk → embed → store vectors → update DB."""
    if embedding_provider or embedding_model:
        set_embedding_override(embedding_provider, embedding_model)
    try:
        from utils.file_storage import get_file_preview, get_local_path_for_reading
        from utils.file_processors import get_file_metadata
        from database.models import KnowledgeBaseFile
        from database.manager import get_db_manager

        local_path = get_local_path_for_reading(relative_path)
        if not local_path:
            raise FileNotFoundError(f"Cannot resolve file for processing: {relative_path}")

        loop = asyncio.get_event_loop()
        text_chunks, embeddings = await loop.run_in_executor(
            None, _sync_extract_chunk_embed, local_path, file_type
        )
        print(f"📦 Background: {len(text_chunks)} chunks, {len(embeddings)} embeddings for file_id={file_id}")

        metadata = get_file_metadata(local_path, file_type)
        preview_text = get_file_preview(relative_path, file_type, max_length=500)

        vector_store = PgVectorStore()
        vector_ids = await vector_store.add_vectors_with_file_id_sync(
            f"rag_file_{file_id}", text_chunks, embeddings
        )
        print(f"🔮 Stored {len(vector_ids)} vectors for file_id={file_id}")

        db_manager = get_db_manager()
        session = db_manager.get_session()
        try:
            kb_file = session.query(KnowledgeBaseFile).get(file_id)
            if kb_file:
                kb_file.processed = True
                kb_file.chunk_count = len(text_chunks)
                kb_file.preview_text = preview_text
                kb_file.set_metadata(metadata)
                kb_file.set_vector_ids(vector_ids)
                kb_file.processing_error = None
                session.commit()
        finally:
            session.close()
    except Exception as e:
        print(f"❌ Background RAG processing failed for file_id={file_id}: {e}")
        traceback.print_exc()
        try:
            from database.models import KnowledgeBaseFile
            from database.manager import get_db_manager
            db_manager = get_db_manager()
            session = db_manager.get_session()
            kb_file = session.query(KnowledgeBaseFile).get(file_id)
            if kb_file:
                kb_file.processing_error = str(e)
                session.commit()
        except Exception:
            traceback.print_exc()
        finally:
            try:
                session.close()
            except Exception:
                pass


@app.post("/api/rag-files/upload")
async def upload_rag_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    embedding_provider: Optional[str] = Form(None),
    embedding_model: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload RAG knowledge base file (processing runs in background).

    Supports: Excel, Word, PowerPoint, PDF, TXT, CSV, Images
    Returns 202 immediately with file record (processed=false). Chunking and embedding run in background.
    """
    try:
        from utils.file_storage import save_rag_file
        from utils.file_processors import detect_file_type_from_extension
        from database.models import KnowledgeBaseFile
        from database.manager import get_db_manager

        file_type = detect_file_type_from_extension(file.filename)
        if file_type == "unknown":
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": f"Unsupported file type: {file.filename}"},
            )

        file_content = await file.read()
        file_size = len(file_content)
        full_path, relative_path = save_rag_file(file_content, file.filename)
        print(f"📁 RAG file saved, queued for background processing: {file.filename} ({file_type})")

        db_manager = get_db_manager()
        session = db_manager.get_session()
        try:
            kb_file = KnowledgeBaseFile(
                filename=file.filename,
                file_type=file_type,
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
                "file_size": kb_file.file_size,
                "upload_time": kb_file.upload_time.isoformat(),
                "processed": False,
                "chunk_count": 0,
                "metadata": kb_file.get_metadata(),
            }
        finally:
            session.close()

        background_tasks.add_task(
            _process_rag_file_background,
            file_id,
            full_path,
            relative_path,
            file_type,
            file_size,
            file.content_type or "application/octet-stream",
            file.filename,
            embedding_provider,
            embedding_model,
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
        print("❌ Upload failed")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Upload failed"},
        )


@app.get("/api/rag-files")
async def get_rag_files(current_user: dict = Depends(get_current_user)):
    """
    Get all RAG knowledge base files list
    
    Returns:
        List of file information
    """
    try:
        files = db_manager.get_kb_files_for_user(
            user_phone=current_user["phone_number"],
            role=_user_role(current_user)
        )
        return JSONResponse(
            status_code=200,
            content={"status": "success", "data": files}
        )
    except Exception:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Get files failed"}
        )


@app.get("/api/rag-files/{file_id}")
async def get_rag_file_details(file_id: int, current_user: dict = Depends(get_current_user)):
    """
    Get single RAG file details
    
    Returns:
        Complete file information including preview and metadata
    """
    try:
        kb_file = db_manager.get_kb_file_for_user(
            file_id=file_id,
            user_phone=current_user["phone_number"],
            role=_user_role(current_user)
        )
        if not kb_file:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "File not found or forbidden"}
            )
        return JSONResponse(
            status_code=200,
            content={"status": "success", "data": kb_file}
        )
    except Exception:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Get file details failed"}
        )


@app.get("/api/rag-files/{file_id}/download")
async def download_rag_file(file_id: int, current_user: dict = Depends(get_current_user)):
    """
    Download original RAG file
    
    Returns:
        File download response (supports local and GCS storage)
    """
    try:
        from fastapi.responses import Response
        from utils.file_storage import file_exists, read_file_bytes

        kb_file = db_manager.get_kb_file_for_user(
            file_id=file_id,
            user_phone=current_user["phone_number"],
            role=_user_role(current_user)
        )
        if not kb_file:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "File not found or forbidden"}
            )

        file_path = kb_file["file_path"]
        if not file_exists(file_path):
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "Physical file not found"}
            )

        content = read_file_bytes(file_path)
        if content is None:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "Physical file not found"}
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
            status_code=500,
            content={"status": "error", "message": "Download file failed"}
        )


@app.delete("/api/rag-files/{file_id}")
async def delete_rag_file(file_id: int, current_user: dict = Depends(get_current_user)):
    """
    Delete RAG file
    
    Operations: Delete physical file → Delete pgvector vectors → Delete DB record
    """
    try:
        from utils.file_storage import delete_rag_file as delete_file_storage
        kb_file = db_manager.get_kb_file_for_user(
            file_id=file_id,
            user_phone=current_user["phone_number"],
            role=_user_role(current_user)
        )
        if not kb_file:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "File not found or forbidden"}
            )

        file_path = kb_file["file_path"]

        if kb_file["processed"] and kb_file["chunk_count"] > 0:
            try:
                vector_store = PgVectorStore()
                deleted_count = await vector_store.delete_vectors_by_file_id_sync(f"rag_file_{file_id}")
                print(f"🗑️ Deleted {deleted_count} vectors from pgvector")
            except Exception as vec_error:
                print(f"⚠️ Failed to delete vectors: {vec_error}")

        try:
            delete_file_storage(file_path)
        except Exception as file_error:
            print(f"⚠️ Failed to delete physical file: {file_error}")

        deleted = db_manager.soft_delete_kb_file_for_user(
            file_id=file_id,
            user_phone=current_user["phone_number"],
            role=_user_role(current_user)
        )
        if not deleted:
            return JSONResponse(
                status_code=403,
                content={"status": "error", "message": "Delete forbidden"}
            )

        return JSONResponse(
            status_code=200,
            content={"status": "success", "message": "File deleted successfully"}
        )
    except Exception:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Delete file failed"}
        )


@app.get("/api/rag-files/{file_id}/preview")
async def get_rag_file_preview(
    file_id: int,
    full: bool = False,
    offset: int = 0,
    limit: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Get file preview content.
    Default: first 500 chars from stored preview_text.
    With full=true or offset/limit: read from file (paginated or full).
    """
    try:
        from utils.file_storage import get_file_preview_slice
        kb_file = db_manager.get_kb_file_for_user(
            file_id=file_id,
            user_phone=current_user["phone_number"],
            role=_user_role(current_user)
        )
        if not kb_file:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "File not found or forbidden"}
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

        result = {
            "filename": kb_file["filename"],
            "file_type": file_type,
            "preview_content": preview_content,
            "total_length": total_length,
        }
        return JSONResponse(
            status_code=200,
            content={"status": "success", "data": result}
        )
    except Exception:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Get file preview failed"}
        )


@app.get("/api/rag-files/{file_id}/preview-pdf")
async def get_rag_file_preview_pdf(
    file_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Return PDF of Office file (excel/word/powerpoint) via LibreOffice."""
    try:
        from fastapi.responses import FileResponse
        from utils.file_storage import file_exists, get_local_path_for_reading
        from utils.office_to_pdf import convert_to_pdf, is_office_type, libreoffice_available

        kb_file = db_manager.get_kb_file_for_user(
            file_id=file_id,
            user_phone=current_user["phone_number"],
            role=_user_role(current_user),
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


@app.get("/metrics")
def get_metrics():
    return metrics_response()


@app.get("/health")
def health_check():
    """
    Health check endpoint
    
    Used to check if the API service is running normally, can be used by load balancers or monitoring systems
    Supports TXT and PDF file processing
    
    Returns:
        dict: Response containing service status
        
    Example:
        GET /health
        
        Response:
        {
            "status": "healthy",
            "message": "SRR case processing API is running normally"
        }
    """
    print(f"🏥 HEALTH CHECK HIT", flush=True)
    return {"status": "healthy", "message": "SRR case processing API is running normally, supports TXT and PDF files"}


if __name__ == "__main__":
    """
    Program entry point

    Start FastAPI server when running this file directly
    Configuration:
    - Host: 0.0.0.0 (allows external access)
    - Port: 8001
    - Auto reload: Enabled (development mode)

    Environment variables:
    - LOG_LEVEL=DEBUG: Enable debug logging (shows all debug messages)
    - PYTHONUNBUFFERED=1: Enable unbuffered output (immediate log visibility)

    Example:
        LOG_LEVEL=DEBUG python -u main.py
    """
    import uvicorn
    from config.settings import UVICORN_TIMEOUT_KEEP_ALIVE
    # reload=False: avoid worker process exit (returncode 1) under start.py monitor
    uvicorn.run(
        app="main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        timeout_keep_alive=UVICORN_TIMEOUT_KEEP_ALIVE,
    )
    