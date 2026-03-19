"""
data库manager
"""
from sqlalchemy import create_engine, func, text, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from .models import (
    Base,
    SRRCase,
    ConversationHistory,
    KnowledgeBaseFile,
    User,
    ChatMessage,
    ChatSession,
    ChatQualityMetric,
)
import os
import uuid
from datetime import datetime, timedelta
import pytz
from typing import Optional, List, Dict, Any
import json


def _get_database_url() -> str:
    """Resolve database URL: prefer DATABASE_URL env, fallback to SQLite."""
    url = os.getenv("DATABASE_URL", "").strip()
    if url and "postgresql" in url:
        return url
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))
    db_path = os.path.join(project_root, "data", "srr_cases.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return f"sqlite:///{db_path}"


def _is_postgres(engine) -> bool:
    return "postgresql" in str(engine.url)


class DatabaseManager:
    """data库管理器"""

    def __init__(self, database_url: Optional[str] = None):
        url = database_url or _get_database_url()
        self._use_postgres = "postgresql" in url
        self.db_path = url
        connect_args = {}
        if self._use_postgres:
            # 方案B：将 PostgreSQL 会话时区固定为东8区，统一所有 NOW()/隐式时间行为
            connect_args = {"options": "-c timezone=Asia/Shanghai"}
        self.engine = create_engine(url, echo=False, pool_pre_ping=True, connect_args=connect_args)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        Base.metadata.create_all(bind=self.engine)

        self._migrate_add_missing_columns()
        self._migrate_add_missing_indexes()
        self._migrate_sync_sessions()

        if self._use_postgres:
            self._sync_all_sequences()

        print(f"✅ data库initialize完成: {'PostgreSQL' if self._use_postgres else url}")

    def _migrate_sync_sessions(self):
        """将现有消息中的会话ID同步到ChatSession表"""
        session = self.get_session()
        try:
            if self._use_postgres:
                stmt = text("""
                    INSERT INTO chat_sessions (session_id, user_phone, created_at, updated_at, is_active)
                    SELECT DISTINCT session_id, user_phone, MIN(created_at), MAX(created_at), true
                    FROM chat_messages
                    GROUP BY session_id, user_phone
                    ON CONFLICT (session_id) DO NOTHING
                """)
            else:
                stmt = text("""
                    INSERT OR IGNORE INTO chat_sessions (session_id, user_phone, created_at, updated_at, is_active)
                    SELECT DISTINCT session_id, user_phone, MIN(created_at), MAX(created_at), 1
                    FROM chat_messages
                    GROUP BY session_id, user_phone
                """)
            session.execute(stmt)
            session.commit()
            print("✅ 会话数据同步完成")
        except Exception as e:
            session.rollback()
            print(f"⚠️ 会话数据同步失败 (可能表已存在): {e}")
        finally:
            session.close()
    
    def _migrate_add_missing_columns(self):
        """检查并添加模型中定义但数据库表中缺失的列"""
        from sqlalchemy import inspect, text
        inspector = inspect(self.engine)

        datetime_type = "TIMESTAMP" if self._use_postgres else "DATETIME"
        migration_map = {
            "srr_cases": {
                "file_hash": "VARCHAR(64)",
                "uploaded_by": "VARCHAR(20)",
                "processing_time": datetime_type,
                "ai_summary": "TEXT",
                "similar_historical_cases": "TEXT",
                "location_statistics": "TEXT",
                "duplicate_status": "VARCHAR(50)",
                "duplicate_case_number": "VARCHAR(50)",
                "duplicate_case_id": "INTEGER",
            },
            "conversation_history": {"user_phone": "VARCHAR(20)"},
            "knowledge_base_files": {
                "uploaded_by": "VARCHAR(20)",
                "category": "VARCHAR(50)",
                "file_hash": "VARCHAR(64)",
            },
            "chat_sessions": {
                "session_state": "TEXT",
            },
            "chat_quality_metrics": {
                "eval_method": "VARCHAR(20)",
            },
        }

        with self.engine.connect() as conn:
            for table_name, columns in migration_map.items():
                if not inspector.has_table(table_name):
                    continue
                existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
                for col_name, col_type in columns.items():
                    if col_name not in existing_columns:
                        try:
                            stmt = text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}")
                            conn.execute(stmt)
                            conn.commit()
                            print(f"✅ 迁移: 为 {table_name} 添加列 {col_name} ({col_type})")
                        except Exception as e:
                            conn.rollback()
                            if "already exists" not in str(e).lower() and "duplicate" not in str(e).lower():
                                print(f"⚠️ 迁移列 {table_name}.{col_name}: {e}")

    def _migrate_add_missing_indexes(self):
        """Ensure performance-critical indexes exist on chat_messages."""
        from sqlalchemy import inspect, text
        inspector = inspect(self.engine)
        if not inspector.has_table("chat_messages"):
            return
        existing = {idx["name"] for idx in inspector.get_indexes("chat_messages")}
        needed = {
            "ix_chat_messages_user_phone": "user_phone",
            "ix_chat_messages_session_id": "session_id",
            "ix_chat_messages_created_at": "created_at",
        }
        with self.engine.connect() as conn:
            for idx_name, col_name in needed.items():
                if idx_name not in existing:
                    try:
                        conn.execute(text(f'CREATE INDEX "{idx_name}" ON chat_messages ({col_name})'))
                        conn.commit()
                        print(f"✅ 索引迁移: chat_messages.{col_name} ({idx_name})")
                    except Exception as e:
                        conn.rollback()
                        if "already exists" not in str(e).lower():
                            print(f"⚠️ 索引迁移 {idx_name}: {e}")

    def get_session(self):
        """获取data库session"""
        return self.SessionLocal()

    def _is_chat_message_pk_conflict(self, err: Exception) -> bool:
        """
        判断是否为 chat_messages 主键冲突（通常由 PG sequence 落后导致）。
        """
        msg = str(err).lower()
        return (
            "chat_messages_pkey" in msg
            or (
                "duplicate key value violates unique constraint" in msg
                and "chat_messages" in msg
                and "key (id)=" in msg
            )
        )

    _SERIAL_TABLES = frozenset({
        "srr_cases", "chat_messages", "conversation_history", "knowledge_base_files", "chat_quality_metrics",
    })

    def _sync_postgres_sequence(self, session, table_name: str, pk_col: str = "id") -> None:
        """
        将 PostgreSQL 序列推进到当前最大主键，修复 sequence 落后问题。
        支持 _SERIAL_TABLES 白名单中的所有自增主键表。
        """
        if not self._use_postgres:
            return
        if table_name not in self._SERIAL_TABLES or pk_col != "id":
            return
        session.execute(
            text(
                f"SELECT setval("
                f"pg_get_serial_sequence(:tbl, :col), "
                f"COALESCE((SELECT MAX(id) FROM {table_name}), 0) + 1, "
                f"false)"
            ),
            {"tbl": table_name, "col": pk_col},
        )
        session.commit()

    def _sync_all_sequences(self) -> None:
        """启动时同步所有自增主键表的序列，防止迁移/手动导入导致的主键冲突。"""
        session = self.get_session()
        try:
            for table_name in self._SERIAL_TABLES:
                try:
                    self._sync_postgres_sequence(session, table_name, "id")
                except Exception as e:
                    print(f"⚠️ 序列同步跳过 {table_name}: {e}")
            print("✅ PostgreSQL 序列同步完成")
        finally:
            session.close()

    def save_case(self, case_data: dict) -> int:
        """保存案件data"""
        session = self.get_session()
        try:
            case = SRRCase(**case_data)
            session.add(case)
            session.commit()
            case_id = case.id
            print(f"✅ 案件保存success，ID: {case_id}")
            return case_id
        except Exception as e:
            session.rollback()
            print(f"❌ 案件保存failed: {e}")
            raise e
        finally:
            session.close()
    
    def get_case(self, case_id: int) -> dict:
        """获取单个案件"""
        session = self.get_session()
        try:
            case = session.query(SRRCase).filter(SRRCase.id == case_id).first()
            if case:
                return self._case_to_dict(case)
            return None
        finally:
            session.close()

    def get_case_for_user(self, case_id: int, user_phone: str, role: str = "user") -> Optional[dict]:
        """按用户/角色获取单个案件，避免越权访问。"""
        session = self.get_session()
        try:
            query = session.query(SRRCase).filter(
                SRRCase.id == case_id,
                SRRCase.is_active == True
            )
            if role not in ("admin", "manager"):
                query = query.filter(SRRCase.uploaded_by == user_phone)
            case = query.first()
            return self._case_to_dict(case) if case else None
        finally:
            session.close()
    
    def get_cases(self, limit=100, offset=0, deduplicate_by_case_number: bool = True) -> list:
        """
        获取案件列表
        deduplicate_by_case_number: 若为True，对相同案件编号(C_case_number)的记录去重，仅保留最新一条(以updated_at或created_at最晚为准)
        """
        session = self.get_session()
        try:
            order_col = func.coalesce(SRRCase.updated_at, SRRCase.created_at).desc()
            cases = session.query(SRRCase).filter(SRRCase.is_active == True)\
                .order_by(order_col, SRRCase.id.desc())\
                .offset(offset).limit(limit * 3 if deduplicate_by_case_number else limit).all()  # 多取一些以便去重后够数
            case_dicts = [self._case_to_dict(case) for case in cases]
            if deduplicate_by_case_number:
                seen = {}
                for c in case_dicts:
                    cn = (c.get('C_case_number') or '').strip()
                    if not cn:
                        seen[f'_empty_{c["id"]}'] = c  # 无案件编号的各自保留
                        continue
                    if cn not in seen:
                        seen[cn] = c  # 已按updated_at desc排序，首次遇到即为最新
                case_dicts = list(seen.values())
                case_dicts.sort(key=lambda x: (x.get('updated_at') or x.get('created_at') or ''), reverse=True)
                case_dicts = case_dicts[:limit]
            return case_dicts
        finally:
            session.close()

    def get_cases_for_user(
        self,
        user_phone: str,
        role: str = "user",
        limit: int = 100,
        offset: int = 0,
        deduplicate_by_case_number: bool = True
    ) -> List[dict]:
        """按用户/角色获取案件列表。"""
        session = self.get_session()
        try:
            order_col = func.coalesce(SRRCase.updated_at, SRRCase.created_at).desc()
            query = session.query(SRRCase).filter(SRRCase.is_active == True)
            if role not in ("admin", "manager"):
                query = query.filter(SRRCase.uploaded_by == user_phone)
            cases = query.order_by(order_col, SRRCase.id.desc()) \
                .offset(offset).limit(limit * 3 if deduplicate_by_case_number else limit).all()
            case_dicts = [self._case_to_dict(case) for case in cases]
            if deduplicate_by_case_number:
                seen = {}
                for c in case_dicts:
                    cn = (c.get('C_case_number') or '').strip()
                    if not cn:
                        seen[f'_empty_{c["id"]}'] = c
                        continue
                    if cn not in seen:
                        seen[cn] = c
                case_dicts = list(seen.values())
                case_dicts.sort(key=lambda x: (x.get('updated_at') or x.get('created_at') or ''), reverse=True)
                case_dicts = case_dicts[:limit]
            return case_dicts
        finally:
            session.close()
    
    def search_cases(self, keyword: str) -> list:
        """搜索案件"""
        session = self.get_session()
        try:
            cases = session.query(SRRCase).filter(
                SRRCase.is_active == True,
                (SRRCase.E_caller_name.contains(keyword) |
                 SRRCase.G_slope_no.contains(keyword) |
                 SRRCase.H_location.contains(keyword) |
                 SRRCase.I_nature_of_request.contains(keyword))
            ).all()
            return [self._case_to_dict(case) for case in cases]
        finally:
            session.close()

    def search_cases_for_user(self, keyword: str, user_phone: str, role: str = "user") -> List[dict]:
        """按用户/角色搜索案件，普通用户仅可搜索自己上传的数据。"""
        session = self.get_session()
        try:
            query = session.query(SRRCase).filter(
                SRRCase.is_active == True,
                (SRRCase.E_caller_name.contains(keyword) |
                 SRRCase.G_slope_no.contains(keyword) |
                 SRRCase.H_location.contains(keyword) |
                 SRRCase.I_nature_of_request.contains(keyword))
            )
            if role not in ("admin", "manager"):
                query = query.filter(SRRCase.uploaded_by == user_phone)
            return [self._case_to_dict(case) for case in query.all()]
        finally:
            session.close()
    
    def get_case_count(self) -> int:
        """获取 srr_cases 表记录数（用于 historical_case_matcher 排除已入库案件）"""
        session = self.get_session()
        try:
            return session.query(func.count(SRRCase.id)).scalar() or 0
        finally:
            session.close()

    def get_stats(self) -> dict:
        """获取统计information"""
        session = self.get_session()
        try:
            total_cases = session.query(SRRCase).filter(SRRCase.is_active == True).count()
            txt_cases = session.query(SRRCase).filter(SRRCase.file_type == 'txt').count()
            tmo_cases = session.query(SRRCase).filter(SRRCase.file_type == 'tmo').count()
            rcc_cases = session.query(SRRCase).filter(SRRCase.file_type == 'rcc').count()
            
            return {
                'total_cases': total_cases,
                'txt_cases': txt_cases,
                'tmo_cases': tmo_cases,
                'rcc_cases': rcc_cases
            }
        finally:
            session.close()
    
    def _case_to_dict(self, case) -> dict:
        """将案件object转换为字典"""
        return {
            'id': case.id,
            'A_date_received': case.A_date_received,
            'B_source': case.B_source,
            'C_case_number': case.C_case_number,
            'D_type': case.D_type,
            'E_caller_name': case.E_caller_name,
            'F_contact_no': case.F_contact_no,
            'G_slope_no': case.G_slope_no,
            'H_location': case.H_location,
            'I_nature_of_request': case.I_nature_of_request,
            'J_subject_matter': case.J_subject_matter,
            'K_10day_rule_due_date': case.K_10day_rule_due_date,
            'L_icc_interim_due': case.L_icc_interim_due,
            'M_icc_final_due': case.M_icc_final_due,
            'N_works_completion_due': case.N_works_completion_due,
            'O1_fax_to_contractor': case.O1_fax_to_contractor,
            'O2_email_send_time': case.O2_email_send_time,
            'P_fax_pages': case.P_fax_pages,
            'Q_case_details': case.Q_case_details,
            'ai_summary': getattr(case, 'ai_summary', None),
            'similar_historical_cases': self._parse_json_field(getattr(case, 'similar_historical_cases', None)),
            'location_statistics': self._parse_json_field(getattr(case, 'location_statistics', None)),
            'duplicate_status': getattr(case, 'duplicate_status', None),
            'duplicate_case_number': getattr(case, 'duplicate_case_number', None),
            'duplicate_case_id': getattr(case, 'duplicate_case_id', None),
            'original_filename': case.original_filename,
            'file_type': case.file_type,
            'uploaded_by': getattr(case, 'uploaded_by', None),
            'processing_time': self._format_beijing_time(case.processing_time),
            'created_at': self._format_beijing_time(case.created_at),
            'updated_at': self._format_beijing_time(case.updated_at)
        }
    
    def _parse_json_field(self, val):
        """解析 JSON 字串，失敗時回傳 None"""
        if val is None or (isinstance(val, str) and not val.strip()):
            return None
        if isinstance(val, (list, dict)):
            return val
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return None

    def _format_beijing_time(self, dt):
        """格式化北京时间为友好显示"""
        if dt is None:
            return None
        
        # 如果已经是带时区的时间，转换为北京时间
        if dt.tzinfo is not None:
            beijing_tz = pytz.timezone('Asia/Shanghai')
            beijing_time = dt.astimezone(beijing_tz)
        else:
            # 如果是naive时间，假设已经是北京时间
            beijing_tz = pytz.timezone('Asia/Shanghai')
            beijing_time = beijing_tz.localize(dt)
        
        return beijing_time.strftime('%Y-%m-%d %H:%M:%S CST')
    
    # ============== 对话历史管理方法 ==============
    
    def save_conversation(self, conversation_data: dict) -> int:
        """
        保存对话记录
        
        Args:
            conversation_data: 对话数据字典，包含：
                - case_id: 案件ID
                - conversation_type: 对话类型（interim_reply/final_reply/wrong_referral_reply）
                - messages: 消息列表（可选）
                - language: 语言代码（可选，默认zh）
                - status: 状态（可选，默认pending）
        
        Returns:
            对话ID
        """
        session = self.get_session()
        try:
            conversation = ConversationHistory(**conversation_data)
            session.add(conversation)
            session.commit()
            conversation_id = conversation.id
            print(f"✅ 对话保存成功，ID: {conversation_id}")
            return conversation_id
        except Exception as e:
            session.rollback()
            print(f"❌ 对话保存失败: {e}")
            raise e
        finally:
            session.close()
    
    def get_conversation(self, conversation_id: int) -> Optional[dict]:
        """
        获取对话记录
        
        Args:
            conversation_id: 对话ID
        
        Returns:
            对话数据字典，如不存在返回None
        """
        session = self.get_session()
        try:
            conversation = session.query(ConversationHistory).filter(
                ConversationHistory.id == conversation_id
            ).first()
            if conversation:
                return self._conversation_to_dict(conversation)
            return None
        finally:
            session.close()

    def get_conversation_for_user(self, conversation_id: int, user_phone: str, role: str = "user") -> Optional[dict]:
        """按用户获取对话，防止IDOR。"""
        session = self.get_session()
        try:
            query = session.query(ConversationHistory).filter(
                ConversationHistory.id == conversation_id
            )
            if role not in ("admin", "manager"):
                query = query.filter(ConversationHistory.user_phone == user_phone)
            conversation = query.first()
            if conversation:
                return self._conversation_to_dict(conversation)
            return None
        finally:
            session.close()
    
    def update_conversation(self, conversation_id: int, update_data: dict) -> bool:
        """
        更新对话记录
        
        Args:
            conversation_id: 对话ID
            update_data: 要更新的数据字典（可包含messages, draft_reply, status等）
        
        Returns:
            成功返回True，失败返回False
        """
        session = self.get_session()
        try:
            conversation = session.query(ConversationHistory).filter(
                ConversationHistory.id == conversation_id
            ).first()
            
            if not conversation:
                print(f"❌ 对话不存在: {conversation_id}")
                return False
            
            # 更新字段
            for key, value in update_data.items():
                if hasattr(conversation, key):
                    setattr(conversation, key, value)
            
            session.commit()
            print(f"✅ 对话更新成功: {conversation_id}")
            return True
        except Exception as e:
            session.rollback()
            print(f"❌ 对话更新失败: {e}")
            return False
        finally:
            session.close()
    
    def add_message_to_conversation(self, conversation_id: int, role: str, content: str, language: str = 'zh') -> bool:
        """
        向对话添加新消息
        
        Args:
            conversation_id: 对话ID
            role: 角色（user/assistant）
            content: 消息内容
            language: 语言代码
        
        Returns:
            成功返回True，失败返回False
        """
        session = self.get_session()
        try:
            conversation = session.query(ConversationHistory).filter(
                ConversationHistory.id == conversation_id
            ).first()
            
            if not conversation:
                print(f"❌ 对话不存在: {conversation_id}")
                return False
            
            # 添加消息
            conversation.add_message(role, content, language)
            session.commit()
            print(f"✅ 消息添加成功到对话: {conversation_id}")
            return True
        except Exception as e:
            session.rollback()
            print(f"❌ 消息添加失败: {e}")
            return False
        finally:
            session.close()
    
    def get_conversations_by_case(self, case_id: int) -> List[dict]:
        """
        获取案件的所有对话
        
        Args:
            case_id: 案件ID
        
        Returns:
            对话列表
        """
        session = self.get_session()
        try:
            conversations = session.query(ConversationHistory).filter(
                ConversationHistory.case_id == case_id
            ).order_by(ConversationHistory.created_at.desc()).all()
            return [self._conversation_to_dict(conv) for conv in conversations]
        finally:
            session.close()

    def get_conversations_by_case_for_user(self, case_id: int, user_phone: str, role: str = "user") -> List[dict]:
        """按用户/角色获取案件对话列表。"""
        session = self.get_session()
        try:
            query = session.query(ConversationHistory).filter(
                ConversationHistory.case_id == case_id
            )
            if role not in ("admin", "manager"):
                query = query.filter(ConversationHistory.user_phone == user_phone)
            conversations = query.order_by(ConversationHistory.created_at.desc()).all()
            return [self._conversation_to_dict(conv) for conv in conversations]
        finally:
            session.close()
    
    def get_active_conversation(self, case_id: int, conversation_type: str) -> Optional[dict]:
        """
        获取案件的活跃对话（状态为pending或in_progress）
        
        Args:
            case_id: 案件ID
            conversation_type: 对话类型
        
        Returns:
            对话数据字典，如不存在返回None
        """
        session = self.get_session()
        try:
            conversation = session.query(ConversationHistory).filter(
                ConversationHistory.case_id == case_id,
                ConversationHistory.conversation_type == conversation_type,
                ConversationHistory.status.in_(['pending', 'in_progress'])
            ).order_by(ConversationHistory.created_at.desc()).first()
            
            if conversation:
                return self._conversation_to_dict(conversation)
            return None
        finally:
            session.close()
    
    def _conversation_to_dict(self, conversation: ConversationHistory) -> dict:
        """将对话对象转换为字典"""
        return {
            'id': conversation.id,
            'case_id': conversation.case_id,
            'user_phone': conversation.user_phone,
            'conversation_type': conversation.conversation_type,
            'messages': conversation.get_messages(),
            'language': conversation.language,
            'draft_reply': conversation.draft_reply,
            'draft_approved_to_kb': getattr(conversation, 'draft_approved_to_kb', False),
            'status': conversation.status,
            'created_at': self._format_beijing_time(conversation.created_at),
            'updated_at': self._format_beijing_time(conversation.updated_at)
        }
    
    # ============== 用户管理方法 ==============
    
    def create_user(self, user_data: dict) -> str:
        """
        创建新用户
        
        Args:
            user_data: 用户数据字典
        
        Returns:
            str: 用户电话号码（主键）
        """
        session = self.get_session()
        try:
            user = User(**user_data)
            session.add(user)
            session.commit()
            phone_number = user.phone_number
            print(f"✅ 用户创建成功: {phone_number}")
            return phone_number
        except Exception as e:
            session.rollback()
            print(f"❌ 用户创建失败: {e}")
            raise e
        finally:
            session.close()
    
    def get_user(self, phone_number: str) -> Optional[dict]:
        """
        获取用户信息
        
        Args:
            phone_number: 用户电话号码
        
        Returns:
            dict: 用户信息字典，不存在返回None
        """
        session = self.get_session()
        try:
            user = session.query(User).filter(
                User.phone_number == phone_number,
                User.is_active == True
            ).first()
            
            if user:
                return {
                    'phone_number': user.phone_number,
                    'full_name': user.full_name,
                    'department': user.department,
                    'role': user.role,
                    'email': user.email,
                    'created_at': self._format_beijing_time(user.created_at)
                }
            return None
        finally:
            session.close()
    
    def update_user(self, phone_number: str, update_data: dict) -> bool:
        """
        更新用户信息
        
        Args:
            phone_number: 用户电话号码
            update_data: 要更新的数据
        
        Returns:
            bool: 成功返回True，失败返回False
        """
        session = self.get_session()
        try:
            user = session.query(User).filter(
                User.phone_number == phone_number
            ).first()
            
            if not user:
                print(f"❌ 用户不存在: {phone_number}")
                return False
            
            for key, value in update_data.items():
                if hasattr(user, key) and key != 'phone_number':  # 不允许修改主键
                    setattr(user, key, value)
            
            session.commit()
            print(f"✅ 用户更新成功: {phone_number}")
            return True
        except Exception as e:
            session.rollback()
            print(f"❌ 用户更新失败: {e}")
            return False
        finally:
            session.close()
    
    # ============== 聊天消息管理方法 ==============
    
    def save_chat_message(self, message_data: dict) -> int:
        """
        保存聊天消息
        
        Args:
            message_data: 消息数据字典
        
        Returns:
            int: 消息ID
        """
        session = self.get_session()
        try:
            # 最多尝试两次：第一次正常写入；若命中主键冲突则同步序列后重试一次。
            for attempt in range(2):
                try:
                    if 'file_info' in message_data and isinstance(message_data['file_info'], dict):
                        message = ChatMessage(**{k: v for k, v in message_data.items() if k != 'file_info'})
                        message.set_file_info(message_data['file_info'])
                    else:
                        message = ChatMessage(**message_data)

                    session.add(message)
                    session.commit()
                    message_id = message.id
                    print(f"✅ 聊天消息保存成功: {message_id}")
                    return message_id
                except IntegrityError as e:
                    session.rollback()
                    if attempt == 0 and self._is_chat_message_pk_conflict(e):
                        print("⚠️ 检测到 chat_messages 主键冲突，正在同步序列后重试...")
                        self._sync_postgres_sequence(session, "chat_messages", "id")
                        continue
                    raise
        except Exception as e:
            session.rollback()
            print(f"❌ 聊天消息保存失败: {e}")
            raise e
        finally:
            session.close()
    
    def get_user_chat_history(self, user_phone: str, session_id: str = None, limit: int = 100) -> List[dict]:
        """
        获取用户聊天历史
        
        Args:
            user_phone: 用户电话号码
            session_id: 会话ID（可选，不提供则返回所有会话）
            limit: 最大返回消息数
        
        Returns:
            List[dict]: 消息列表
        """
        session = self.get_session()
        try:
            query = session.query(ChatMessage).filter(
                ChatMessage.user_phone == user_phone
            )
            
            if session_id:
                query = query.filter(ChatMessage.session_id == session_id)
            
            messages = query.order_by(ChatMessage.created_at.asc()).limit(limit).all()
            
            result = []
            for msg in messages:
                result.append({
                    'id': msg.id,
                    'user_phone': msg.user_phone,
                    'session_id': msg.session_id,
                    'message_type': msg.message_type,
                    'content': msg.content,
                    'case_id': msg.case_id,
                    'file_info': msg.get_file_info(),
                    'created_at': self._format_beijing_time(msg.created_at)
                })
            
            return result
        finally:
            session.close()
    
    def delete_session_messages(self, user_phone: str, session_id: str) -> int:
        """
        删除指定用户、指定会话下的所有消息。
        
        Args:
            user_phone: 用户电话号码
            session_id: 会话ID
            
        Returns:
            int: 删除的消息条数
        """
        session = self.get_session()
        try:
            deleted = session.query(ChatMessage).filter(
                ChatMessage.user_phone == user_phone,
                ChatMessage.session_id == session_id
            ).delete(synchronize_session=False)
            session.commit()
            return deleted
        except Exception as e:
            session.rollback()
            print(f"❌ 删除会话消息失败: {e}")
            raise e
        finally:
            session.close()
    
    def get_user_sessions(self, user_phone: str) -> List[dict]:
        """
        获取用户的所有会话列表
        
        Args:
            user_phone: 用户电话号码
        
        Returns:
            List[dict]: 会话列表
        """
        session = self.get_session()
        try:
            # 查询ChatSession表
            chat_sessions = session.query(ChatSession).filter(
                ChatSession.user_phone == user_phone,
                ChatSession.is_active == True
            ).order_by(ChatSession.updated_at.desc()).all()
            
            result = []
            for sess in chat_sessions:
                # 查询消息数量
                msg_count = session.query(func.count(ChatMessage.id)).filter(
                    ChatMessage.session_id == sess.session_id
                ).scalar()
                
                result.append({
                    'session_id': sess.session_id,
                    'title': sess.title,
                    'message_count': msg_count,
                    'created_at': self._format_beijing_time(sess.created_at),
                    'last_message_time': self._format_beijing_time(sess.updated_at)
                })
            
            return result
        finally:
            session.close()

    def create_chat_session(self, user_phone: str, title: Optional[str] = None) -> dict:
        """
        创建新会话。
        """
        session = self.get_session()
        try:
            session_id = str(uuid.uuid4())
            chat_session = ChatSession(
                session_id=session_id,
                user_phone=user_phone,
                title=title or None,
                session_state="{}",
            )
            session.add(chat_session)
            session.commit()
            return {
                'session_id': session_id,
                'title': title,
                'created_at': self._format_beijing_time(chat_session.created_at)
            }
        except Exception as e:
            session.rollback()
            print(f"❌ 创建会话失败: {e}")
            raise e
        finally:
            session.close()

    def delete_chat_session(self, user_phone: str, session_id: str) -> int:
        """
        删除指定用户的指定会话（删除该会话下所有消息并软删除会话）。
        返回删除的消息条数。
        """
        session = self.get_session()
        try:
            deleted = session.query(ChatMessage).filter(
                ChatMessage.user_phone == user_phone,
                ChatMessage.session_id == session_id
            ).delete(synchronize_session=False)
            sess = session.query(ChatSession).filter(
                ChatSession.session_id == session_id,
                ChatSession.user_phone == user_phone
            ).first()
            if sess:
                sess.is_active = False
            session.commit()
            return deleted
        except Exception as e:
            session.rollback()
            print(f"❌ 删除会话失败: {e}")
            raise e
        finally:
            session.close()

    # ============== Chat quality metrics ==============

    def get_session_owner_phone(self, session_id: str) -> Optional[str]:
        """Resolve session owner for metrics attribution."""
        session = self.get_session()
        try:
            row = session.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            return row.user_phone if row else None
        finally:
            session.close()

    def save_chat_quality_metric(self, metric_data: Dict[str, Any]) -> int:
        """Persist one chat quality metric record."""
        session = self.get_session()
        try:
            rag_eval = metric_data.get("rag_evaluation") or {}
            retrieval_metrics = rag_eval.get("retrieval_metrics", [])
            thinking_steps = metric_data.get("thinking_steps") or []
            row = ChatQualityMetric(
                session_id=metric_data.get("session_id"),
                user_phone=metric_data.get("user_phone"),
                query=metric_data.get("query", ""),
                intent=metric_data.get("intent"),
                provider=metric_data.get("provider"),
                model=metric_data.get("model"),
                response_length=int(metric_data.get("response_length") or 0),
                stream_error=metric_data.get("stream_error"),
                retrieval_latency_ms=int(rag_eval.get("retrieval_latency_ms") or 0),
                generation_latency_ms=int(rag_eval.get("generation_latency_ms") or 0),
                total_latency_ms=int(rag_eval.get("total_latency_ms") or 0),
                context_relevance=float(rag_eval.get("context_relevance") or 0.0),
                answer_faithfulness=float(rag_eval.get("answer_faithfulness") or 0.0),
                answer_coverage=float(rag_eval.get("answer_coverage") or 0.0),
                quality_score=float(rag_eval.get("quality_score") or 0.0),
                total_docs_retrieved=int(rag_eval.get("total_docs_retrieved") or 0),
                total_docs_used=int(rag_eval.get("total_docs_used") or 0),
                eval_method=str(rag_eval.get("eval_method") or "keyword_overlap"),
                retrieval_metrics=json.dumps(retrieval_metrics, ensure_ascii=False),
                thinking_steps=json.dumps(thinking_steps, ensure_ascii=False),
            )
            session.add(row)
            session.commit()
            return row.id
        except Exception as e:
            session.rollback()
            print(f"❌ 保存聊天质量指标失败: {e}")
            return 0
        finally:
            session.close()

    def _metrics_base_query(self, session, user_phone: str, session_id: Optional[str] = None):
        query = session.query(ChatQualityMetric).filter(ChatQualityMetric.user_phone == user_phone)
        if session_id:
            query = query.filter(ChatQualityMetric.session_id == session_id)
        return query

    def get_quality_metrics_summary(
        self,
        *,
        user_phone: str,
        days: int = 7,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return aggregate quality summary in a rolling window."""
        session = self.get_session()
        try:
            since = datetime.now(pytz.timezone("Asia/Shanghai")) - timedelta(days=max(days, 1))
            rows = (
                self._metrics_base_query(session, user_phone, session_id)
                .filter(ChatQualityMetric.created_at >= since)
                .order_by(ChatQualityMetric.created_at.asc())
                .all()
            )
            total = len(rows)
            if total == 0:
                return {
                    "total_queries": 0,
                    "success_rate": 0.0,
                    "avg_quality_score": 0.0,
                    "avg_context_relevance": 0.0,
                    "avg_faithfulness": 0.0,
                    "avg_coverage": 0.0,
                    "p95_total_latency_ms": 0,
                }

            ok_count = sum(1 for row in rows if not row.stream_error)
            latency_values = sorted(int(row.total_latency_ms or 0) for row in rows)
            p95_idx = min(len(latency_values) - 1, int(len(latency_values) * 0.95))
            return {
                "total_queries": total,
                "success_rate": round(ok_count / total, 4),
                "avg_quality_score": round(sum(float(row.quality_score or 0.0) for row in rows) / total, 4),
                "avg_context_relevance": round(sum(float(row.context_relevance or 0.0) for row in rows) / total, 4),
                "avg_faithfulness": round(sum(float(row.answer_faithfulness or 0.0) for row in rows) / total, 4),
                "avg_coverage": round(sum(float(row.answer_coverage or 0.0) for row in rows) / total, 4),
                "p95_total_latency_ms": latency_values[p95_idx],
            }
        finally:
            session.close()

    def get_quality_metrics_trend(
        self,
        *,
        user_phone: str,
        days: int = 7,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return daily trend points for quality metrics."""
        session = self.get_session()
        try:
            since = datetime.now(pytz.timezone("Asia/Shanghai")) - timedelta(days=max(days, 1))
            rows = (
                self._metrics_base_query(session, user_phone, session_id)
                .filter(ChatQualityMetric.created_at >= since)
                .order_by(ChatQualityMetric.created_at.asc())
                .all()
            )
            buckets: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                dt = row.created_at
                if dt is None:
                    continue
                key = dt.strftime("%Y-%m-%d")
                bucket = buckets.setdefault(
                    key,
                    {
                        "date": key,
                        "count": 0,
                        "quality_score_sum": 0.0,
                        "context_relevance_sum": 0.0,
                        "faithfulness_sum": 0.0,
                        "coverage_sum": 0.0,
                        "latency_sum": 0,
                        "error_count": 0,
                    },
                )
                bucket["count"] += 1
                bucket["quality_score_sum"] += float(row.quality_score or 0.0)
                bucket["context_relevance_sum"] += float(row.context_relevance or 0.0)
                bucket["faithfulness_sum"] += float(row.answer_faithfulness or 0.0)
                bucket["coverage_sum"] += float(row.answer_coverage or 0.0)
                bucket["latency_sum"] += int(row.total_latency_ms or 0)
                if row.stream_error:
                    bucket["error_count"] += 1

            trend: List[Dict[str, Any]] = []
            for key in sorted(buckets.keys()):
                bucket = buckets[key]
                count = max(bucket["count"], 1)
                trend.append(
                    {
                        "date": key,
                        "count": bucket["count"],
                        "success_rate": round((bucket["count"] - bucket["error_count"]) / count, 4),
                        "avg_quality_score": round(bucket["quality_score_sum"] / count, 4),
                        "avg_context_relevance": round(bucket["context_relevance_sum"] / count, 4),
                        "avg_faithfulness": round(bucket["faithfulness_sum"] / count, 4),
                        "avg_coverage": round(bucket["coverage_sum"] / count, 4),
                        "avg_total_latency_ms": int(bucket["latency_sum"] / count),
                    }
                )
            return trend
        finally:
            session.close()
    
    # ============== 案件去重方法 ==============
    
    def check_case_duplicate(self, file_hash: str) -> Optional[dict]:
        """
        检查案件是否已存在（通过文件哈希）
        
        Args:
            file_hash: 文件SHA256哈希值
        
        Returns:
            dict: 已存在的案件信息，不存在返回None
        """
        session = self.get_session()
        try:
            case = session.query(SRRCase).filter(
                SRRCase.file_hash == file_hash,
                SRRCase.is_active == True
            ).first()
            
            if case:
                return self._case_to_dict(case)
            return None
        finally:
            session.close()

    def precheck_case_upload(
        self,
        *,
        filename: str,
        file_hash: Optional[str],
        user_phone: str,
        role: str = "user",
    ) -> Dict[str, Any]:
        """上传前检查 Case 文件：NOT_FOUND / FOUND_SAME_HASH / FOUND_SAME_NAME_DIFF_HASH。"""
        normalized_name = (filename or "").strip()
        lowered_name = normalized_name.lower()
        session = self.get_session()
        try:
            same_hash_case = None
            if file_hash:
                same_hash_case = (
                    session.query(SRRCase)
                    .filter(
                        SRRCase.file_hash == file_hash,
                        SRRCase.is_active == True,
                    )
                    .first()
                )
            if same_hash_case:
                visible_to_user = (
                    role in ("admin", "manager")
                    or same_hash_case.uploaded_by in (None, user_phone)
                )
                return {
                    "result": "FOUND_SAME_HASH",
                    "visible_to_user": visible_to_user,
                    "existing_case_id": same_hash_case.id,
                    "existing_filename": same_hash_case.original_filename,
                    "existing_case_number": same_hash_case.C_case_number,
                    "uploaded_by": same_hash_case.uploaded_by,
                    "existing_created_at": self._format_beijing_time(same_hash_case.created_at),
                }

            same_name_case = None
            if lowered_name:
                same_name_query = (
                    session.query(SRRCase)
                    .filter(
                        SRRCase.is_active == True,
                        func.lower(SRRCase.original_filename) == lowered_name,
                    )
                    .order_by(
                        func.coalesce(SRRCase.updated_at, SRRCase.created_at).desc(),
                        SRRCase.id.desc(),
                    )
                )
                if file_hash:
                    same_name_query = same_name_query.filter(
                        or_(SRRCase.file_hash.is_(None), SRRCase.file_hash != file_hash)
                    )
                same_name_case = same_name_query.first()

            if same_name_case:
                visible_to_user = (
                    role in ("admin", "manager")
                    or same_name_case.uploaded_by in (None, user_phone)
                )
                return {
                    "result": "FOUND_SAME_NAME_DIFF_HASH",
                    "visible_to_user": visible_to_user,
                    "existing_case_id": same_name_case.id,
                    "existing_filename": same_name_case.original_filename,
                    "existing_case_number": same_name_case.C_case_number,
                    "uploaded_by": same_name_case.uploaded_by,
                    "existing_created_at": self._format_beijing_time(same_name_case.created_at),
                }

            return {
                "result": "NOT_FOUND",
                "visible_to_user": True,
                "existing_case_id": None,
                "existing_filename": None,
                "existing_case_number": None,
                "uploaded_by": None,
                "existing_created_at": None,
            }
        finally:
            session.close()
    
    def save_case_with_dedup(self, case_data: dict, file_hash: str, user_phone: str = None) -> tuple:
        """
        保存案件，如果已存在则返回现有案件
        
        Args:
            case_data: 案件数据字典
            file_hash: 文件哈希值
            user_phone: 上传者电话号码（可选）
        
        Returns:
            tuple: (case_id, is_new) - 案件ID和是否为新案件的标志
        """
        session = self.get_session()
        try:
            # 检查是否已存在
            existing_case = session.query(SRRCase).filter(
                SRRCase.file_hash == file_hash,
                SRRCase.is_active == True
            ).first()
            
            if existing_case:
                print(f"⚠️ 案件已存在，file_hash: {file_hash[:16]}..., ID: {existing_case.id}")
                return (existing_case.id, False)
            
            # 创建新案件
            case_data['file_hash'] = file_hash
            if user_phone:
                case_data['uploaded_by'] = user_phone

            for attempt in range(2):
                try:
                    case = SRRCase(**case_data)
                    session.add(case)
                    session.commit()
                    case_id = case.id
                    print(f"✅ 新案件保存成功，ID: {case_id}")
                    return (case_id, True)
                except IntegrityError as e:
                    session.rollback()
                    msg = str(e).lower()
                    is_pk_conflict = "srr_cases_pkey" in msg or (
                        "duplicate key value violates unique constraint" in msg
                        and "key (id)=" in msg
                    )
                    if attempt == 0 and is_pk_conflict:
                        print("⚠️ 检测到 srr_cases 主键冲突，正在同步序列后重试...")
                        self._sync_postgres_sequence(session, "srr_cases", "id")
                        continue
                    raise

        except Exception as e:
            session.rollback()
            print(f"❌ 案件保存失败: {e}")
            raise e
        finally:
            session.close()

    def update_case_metadata(
        self,
        case_id: int,
        ai_summary: Optional[str] = None,
        similar_historical_cases: Optional[list] = None,
        location_statistics: Optional[dict] = None,
        duplicate_detection: Optional[dict] = None,
    ) -> bool:
        """
        更新案件 AI 摘要、相似歷史案件與地點統計
        
        Args:
            case_id: 案件 ID
            ai_summary: AI 生成摘要（可選）
            similar_historical_cases: 相似歷史案件列表（可選，會轉為 JSON 儲存）
            location_statistics: 地點統計（可選，會轉為 JSON 儲存）
        
        Returns:
            bool: 是否更新成功
        """
        session = self.get_session()
        try:
            case = session.query(SRRCase).filter(SRRCase.id == case_id).first()
            if not case:
                return False
            if ai_summary is not None:
                case.ai_summary = ai_summary
            if similar_historical_cases is not None:
                case.similar_historical_cases = json.dumps(
                    similar_historical_cases, ensure_ascii=False
                )
            if location_statistics is not None:
                case.location_statistics = json.dumps(
                    location_statistics, ensure_ascii=False
                )
            if duplicate_detection is not None:
                case.duplicate_status = duplicate_detection.get("classification")
                case.duplicate_case_number = duplicate_detection.get("prior_case_number")
                linked_id = duplicate_detection.get("prior_case_id")
                if linked_id in (None, "", "None") and case.duplicate_case_number:
                    linked_case = (
                        session.query(SRRCase)
                        .filter(
                            SRRCase.C_case_number == case.duplicate_case_number,
                            SRRCase.is_active == True,
                        )
                        .order_by(SRRCase.id.desc())
                        .first()
                    )
                    linked_id = linked_case.id if linked_case else None
                case.duplicate_case_id = int(linked_id) if linked_id not in (None, "", "None") else None
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            print(f"❌ 更新案件 metadata 失败: {e}")
            return False
        finally:
            session.close()

    # ============== 知识库文件权限方法 ==============

    def check_kb_file_duplicate(
        self,
        file_hash: Optional[str],
        filename: Optional[str] = None,
        file_size: Optional[int] = None,
    ) -> Optional[dict]:
        """检查知识库是否重复。优先按哈希，其次对历史空哈希记录按同名同大小兜底。"""
        if not file_hash and not ((filename or "").strip() and isinstance(file_size, int) and file_size > 0):
            return None
        session = self.get_session()
        try:
            kb = None
            if file_hash:
                kb = (
                    session.query(KnowledgeBaseFile)
                    .filter(
                        KnowledgeBaseFile.file_hash == file_hash,
                        KnowledgeBaseFile.is_active == True,
                    )
                    .first()
                )
            # 兼容历史数据：早期记录未回填 file_hash，按同名+同大小兜底判重。
            if not kb and (filename or "").strip() and isinstance(file_size, int) and file_size > 0:
                lowered_name = filename.strip().lower()
                kb = (
                    session.query(KnowledgeBaseFile)
                    .filter(
                        KnowledgeBaseFile.is_active == True,
                        func.lower(KnowledgeBaseFile.filename) == lowered_name,
                        KnowledgeBaseFile.file_size == file_size,
                    )
                    .order_by(KnowledgeBaseFile.upload_time.desc(), KnowledgeBaseFile.id.desc())
                    .first()
                )
            return self._kb_file_to_dict(kb) if kb else None
        finally:
            session.close()

    def get_kb_files_for_user(self, user_phone: str, role: str = "user") -> List[dict]:
        """按用户/角色获取知识库文件列表。知识库全局共享，所有用户可见。"""
        session = self.get_session()
        try:
            query = session.query(KnowledgeBaseFile).filter(
                KnowledgeBaseFile.is_active == True
            )
            files = query.order_by(KnowledgeBaseFile.upload_time.desc()).all()
            return [self._kb_file_to_dict(f) for f in files]
        finally:
            session.close()

    def get_kb_file_for_user(self, file_id: int, user_phone: str, role: str = "user") -> Optional[dict]:
        """按用户/角色获取单个知识库文件。知识库全局共享，所有用户可见。"""
        session = self.get_session()
        try:
            query = session.query(KnowledgeBaseFile).filter(
                KnowledgeBaseFile.id == file_id,
                KnowledgeBaseFile.is_active == True
            )
            kb_file = query.first()
            return self._kb_file_to_dict(kb_file) if kb_file else None
        finally:
            session.close()

    def precheck_kb_upload(
        self,
        *,
        filename: str,
        file_hash: Optional[str],
        file_size: Optional[int],
        user_phone: str,
        role: str = "user",
    ) -> Dict[str, Any]:
        """上传前检查知识库文件：NOT_FOUND / FOUND_SAME_HASH / FOUND_SAME_NAME_DIFF_HASH。"""
        normalized_name = (filename or "").strip()
        lowered_name = normalized_name.lower()
        session = self.get_session()
        try:
            same_hash_kb = None
            if file_hash:
                same_hash_kb = (
                    session.query(KnowledgeBaseFile)
                    .filter(
                        KnowledgeBaseFile.file_hash == file_hash,
                        KnowledgeBaseFile.is_active == True,
                    )
                    .first()
                )
            if same_hash_kb:
                # 知识库全局共享，所有用户可见已有文件
                visible_to_user = True
                return {
                    "result": "FOUND_SAME_HASH",
                    "visible_to_user": visible_to_user,
                    "existing_file_id": same_hash_kb.id,
                    "existing_filename": same_hash_kb.filename,
                    "existing_category": same_hash_kb.category,
                    "uploaded_by": same_hash_kb.uploaded_by,
                    "existing_upload_time": same_hash_kb.upload_time.isoformat()
                    if same_hash_kb.upload_time
                    else None,
                }

            # 兼容历史空哈希记录：同名+同大小视为已上传。
            same_name_same_size = None
            if lowered_name and isinstance(file_size, int) and file_size > 0:
                same_name_same_size = (
                    session.query(KnowledgeBaseFile)
                    .filter(
                        KnowledgeBaseFile.is_active == True,
                        func.lower(KnowledgeBaseFile.filename) == lowered_name,
                        KnowledgeBaseFile.file_size == file_size,
                    )
                    .order_by(KnowledgeBaseFile.upload_time.desc(), KnowledgeBaseFile.id.desc())
                    .first()
                )
            if same_name_same_size:
                visible_to_user = True
                return {
                    "result": "FOUND_SAME_HASH",
                    "visible_to_user": visible_to_user,
                    "existing_file_id": same_name_same_size.id,
                    "existing_filename": same_name_same_size.filename,
                    "existing_category": same_name_same_size.category,
                    "uploaded_by": same_name_same_size.uploaded_by,
                    "existing_upload_time": same_name_same_size.upload_time.isoformat()
                    if same_name_same_size.upload_time
                    else None,
                }

            same_name_kb = None
            if lowered_name:
                same_name_query = (
                    session.query(KnowledgeBaseFile)
                    .filter(
                        KnowledgeBaseFile.is_active == True,
                        func.lower(KnowledgeBaseFile.filename) == lowered_name,
                    )
                    .order_by(KnowledgeBaseFile.upload_time.desc(), KnowledgeBaseFile.id.desc())
                )
                if file_hash:
                    same_name_query = same_name_query.filter(
                        or_(
                            KnowledgeBaseFile.file_hash.is_(None),
                            KnowledgeBaseFile.file_hash != file_hash,
                        )
                    )
                same_name_kb = same_name_query.first()

            if same_name_kb:
                visible_to_user = True
                return {
                    "result": "FOUND_SAME_NAME_DIFF_HASH",
                    "visible_to_user": visible_to_user,
                    "existing_file_id": same_name_kb.id,
                    "existing_filename": same_name_kb.filename,
                    "existing_category": same_name_kb.category,
                    "uploaded_by": same_name_kb.uploaded_by,
                    "existing_upload_time": same_name_kb.upload_time.isoformat()
                    if same_name_kb.upload_time
                    else None,
                }

            return {
                "result": "NOT_FOUND",
                "visible_to_user": True,
                "existing_file_id": None,
                "existing_filename": None,
                "existing_category": None,
                "uploaded_by": None,
                "existing_upload_time": None,
            }
        finally:
            session.close()

    def deactivate_template_slot(self, reply_type: str) -> int:
        """Deactivate all active template files for the given reply_type slot."""
        session = self.get_session()
        try:
            query = session.query(KnowledgeBaseFile).filter(
                KnowledgeBaseFile.is_active == True,
                KnowledgeBaseFile.category == "template",
            )
            rows = query.all()
            count = 0
            for row in rows:
                meta = row.get_metadata()
                if meta.get("reply_type") == reply_type:
                    row.is_active = False
                    count += 1
            session.commit()
            return count
        except Exception as e:
            session.rollback()
            print(f"❌ deactivate_template_slot 失败: {e}")
            return 0
        finally:
            session.close()

    def get_template_file_by_slot(self, reply_type: str) -> Optional[dict]:
        """Get the active template file for the given reply_type slot."""
        session = self.get_session()
        try:
            query = session.query(KnowledgeBaseFile).filter(
                KnowledgeBaseFile.is_active == True,
                KnowledgeBaseFile.category == "template",
            )
            rows = query.order_by(KnowledgeBaseFile.upload_time.desc()).all()
            for row in rows:
                meta = row.get_metadata()
                if meta.get("reply_type") == reply_type:
                    return self._kb_file_to_dict(row)
            return None
        finally:
            session.close()

    def soft_delete_kb_file_for_user(self, file_id: int, user_phone: str, role: str = "user") -> bool:
        """按用户/角色软删除知识库文件。"""
        session = self.get_session()
        try:
            query = session.query(KnowledgeBaseFile).filter(
                KnowledgeBaseFile.id == file_id,
                KnowledgeBaseFile.is_active == True
            )
            if role not in ("admin", "manager"):
                query = query.filter(KnowledgeBaseFile.uploaded_by == user_phone)
            kb_file = query.first()
            if not kb_file:
                return False
            kb_file.is_active = False
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            print(f"❌ 软删除知识库文件失败: {e}")
            return False
        finally:
            session.close()

    def _kb_file_to_dict(self, kb_file: KnowledgeBaseFile) -> dict:
        """将知识库文件对象转换为字典。"""
        return {
            "id": kb_file.id,
            "filename": kb_file.filename,
            "file_hash": getattr(kb_file, "file_hash", None),
            "file_type": kb_file.file_type,
            "category": getattr(kb_file, "category", "general"),
            "file_path": kb_file.file_path,
            "file_size": kb_file.file_size,
            "mime_type": kb_file.mime_type,
            "uploaded_by": kb_file.uploaded_by,
            "upload_time": kb_file.upload_time.isoformat() if kb_file.upload_time else None,
            "processed": kb_file.processed,
            "chunk_count": kb_file.chunk_count,
            "preview_text": kb_file.preview_text,
            "metadata": kb_file.get_metadata(),
            "processing_error": kb_file.processing_error,
            "vector_ids": kb_file.get_vector_ids(),
        }

# 全局data库managerinstance
_db_manager = None

def get_db_manager():
    """获取data库管理器instance"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
