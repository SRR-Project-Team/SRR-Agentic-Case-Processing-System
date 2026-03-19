#!/usr/bin/env python3
"""PostgreSQL/pgvector vector store for RAG and similar-case retrieval."""

from __future__ import annotations

import json
import math
import hashlib
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, inspect, text

from config.settings import DATABASE_URL


class PgVectorStore:
    COLLECTION_HISTORICAL_CASES = "historical_cases_vectors"
    COLLECTION_KNOWLEDGE_DOCS = "knowledge_docs_vectors"
    COLLECTION_TREE_INVENTORY = "tree_inventory_vectors"
    EMBEDDING_MODEL = "bge-m3"  # default fallback label
    ASIA_TZ = ZoneInfo("Asia/Shanghai")

    def _active_embedding_model(self) -> str:
        """Return the currently active embedding model name from context (or fallback)."""
        try:
            from src.core.embedding import _get_provider, _get_model
            return _get_model(_get_provider())
        except Exception:
            return self.EMBEDDING_MODEL

    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or DATABASE_URL
        connect_args = {}
        if "postgresql" in str(self.database_url):
            # 方案B：数据库会话时区固定为东8区，避免 NOW()/默认值产生 UTC 偏差
            connect_args = {"options": "-c timezone=Asia/Shanghai"}
        self.engine = create_engine(
            self.database_url,
            echo=False,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self._ensure_tables()

    def _now_cn_iso(self) -> str:
        """Return Asia/Shanghai wall-clock time (ISO string) for DB inserts."""
        return datetime.now(self.ASIA_TZ).replace(tzinfo=None).isoformat()

    def _content_hash(self, content: str) -> str:
        return hashlib.sha256((content or "").encode("utf-8")).hexdigest()

    def _ensure_tables(self) -> None:
        ddl = [
            "CREATE EXTENSION IF NOT EXISTS vector",
            """
            CREATE TABLE IF NOT EXISTS vector_chunks (
                id BIGSERIAL PRIMARY KEY,
                file_id VARCHAR(128) NOT NULL,
                chunk_index INTEGER NOT NULL,
                embedding_model VARCHAR(64) NOT NULL DEFAULT 'bge-m3',
                embedding_dim INTEGER NOT NULL DEFAULT 1024,
                content_hash VARCHAR(64),
                content TEXT NOT NULL,
                vector_json TEXT NOT NULL,
                create_time TIMESTAMP DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_cases_vectors (
                id BIGSERIAL PRIMARY KEY,
                case_id VARCHAR(64),
                case_number VARCHAR(64),
                location TEXT,
                slope_no VARCHAR(128),
                tree_id VARCHAR(64),
                source VARCHAR(64),
                embedding_model VARCHAR(64) NOT NULL DEFAULT 'bge-m3',
                embedding_dim INTEGER NOT NULL DEFAULT 1024,
                content_hash VARCHAR(64),
                content TEXT NOT NULL,
                vector_json TEXT NOT NULL,
                create_time TIMESTAMP DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS tree_inventory_vectors (
                id BIGSERIAL PRIMARY KEY,
                tree_id VARCHAR(64),
                tree_no VARCHAR(16),
                slope_no VARCHAR(128),
                slope_id VARCHAR(16),
                species TEXT,
                location TEXT,
                source_row_index INTEGER,
                embedding_model VARCHAR(64) NOT NULL DEFAULT 'bge-m3',
                embedding_dim INTEGER NOT NULL DEFAULT 1024,
                content_hash VARCHAR(64),
                content TEXT NOT NULL,
                vector_json TEXT NOT NULL,
                create_time TIMESTAMP DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS knowledge_docs_vectors (
                id BIGSERIAL PRIMARY KEY,
                doc_type VARCHAR(64),
                filename TEXT,
                approved BOOLEAN DEFAULT TRUE,
                embedding_model VARCHAR(64) NOT NULL DEFAULT 'bge-m3',
                embedding_dim INTEGER NOT NULL DEFAULT 1024,
                content_hash VARCHAR(64),
                content TEXT NOT NULL,
                vector_json TEXT NOT NULL,
                create_time TIMESTAMP DEFAULT NOW()
            )
            """,
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_vector_chunks_model_file_chunk ON vector_chunks(embedding_model, file_id, chunk_index)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_hist_case_model ON historical_cases_vectors(embedding_model, case_id)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_tree_vec_model_slope_tree_row ON tree_inventory_vectors(embedding_model, slope_no, COALESCE(tree_no, '_NULL_'), source_row_index)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_kdoc_model_type_file ON knowledge_docs_vectors(embedding_model, doc_type, filename)",
        ]
        with self.engine.begin() as conn:
            for sql in ddl:
                try:
                    conn.execute(text(sql))
                except Exception:
                    # SQLite fallback path does not support CREATE EXTENSION.
                    if "EXTENSION" in sql:
                        continue
                    # SQLite BIGSERIAL fallback table definitions.
                    conn.execute(
                        text(
                            sql.replace("BIGSERIAL", "INTEGER").replace("DEFAULT NOW()", "")
                        )
                    )

    def _cosine_similarity(self, v1: Iterable[float], v2: Iterable[float]) -> float:
        a = list(v1 or [])
        b = list(v2 or [])
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _load_vector(self, raw: Any) -> List[float]:
        if raw is None:
            return []
        if isinstance(raw, list):
            return [float(x) for x in raw]
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [float(x) for x in parsed]
        except Exception:
            return []
        return []

    async def add_vectors_with_file_id_sync(
        self, file_id: str, text_chunks: List[str], embeddings: List[List[float]]
    ) -> List[str]:
        ids: List[str] = []
        now = self._now_cn_iso()
        is_pg = "postgresql" in str(self.engine.url)
        active_model = self._active_embedding_model()
        with self.engine.begin() as conn:
            for idx, (chunk, vec) in enumerate(zip(text_chunks, embeddings)):
                emb_dim = len(vec or [])
                content_hash = self._content_hash(chunk)
                if is_pg:
                    result = conn.execute(
                        text(
                            """
                            INSERT INTO vector_chunks (
                                file_id, chunk_index, embedding_model, embedding_dim, content_hash, content, vector_json, create_time
                            )
                            VALUES (
                                :file_id, :chunk_index, :embedding_model, :embedding_dim, :content_hash, :content, :vector_json, :create_time
                            )
                            ON CONFLICT (embedding_model, file_id, chunk_index)
                            DO UPDATE SET
                                embedding_dim = EXCLUDED.embedding_dim,
                                content_hash = EXCLUDED.content_hash,
                                content = EXCLUDED.content,
                                vector_json = EXCLUDED.vector_json,
                                create_time = EXCLUDED.create_time
                            RETURNING id
                            """
                        ),
                        {
                            "file_id": file_id,
                            "chunk_index": idx,
                            "embedding_model": active_model,
                            "embedding_dim": emb_dim,
                            "content_hash": content_hash,
                            "content": chunk,
                            "vector_json": json.dumps(vec, ensure_ascii=False),
                            "create_time": now,
                        },
                    )
                    row = result.fetchone()
                    rid = row[0] if row else None
                else:
                    result = conn.execute(
                        text(
                            """
                            INSERT OR REPLACE INTO vector_chunks (
                                file_id, chunk_index, embedding_model, embedding_dim, content_hash, content, vector_json, create_time
                            )
                            VALUES (
                                :file_id, :chunk_index, :embedding_model, :embedding_dim, :content_hash, :content, :vector_json, :create_time
                            )
                            """
                        ),
                        {
                            "file_id": file_id,
                            "chunk_index": idx,
                            "embedding_model": active_model,
                            "embedding_dim": emb_dim,
                            "content_hash": content_hash,
                            "content": chunk,
                            "vector_json": json.dumps(vec, ensure_ascii=False),
                            "create_time": now,
                        },
                    )
                    rid = getattr(result, "lastrowid", None)
                ids.append(str(rid or f"{file_id}:{idx}"))
        return ids

    async def delete_vectors_by_file_id_sync(self, file_id: str) -> int:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM vector_chunks WHERE file_id = :file_id"), {"file_id": file_id}
            )
            return int(result.rowcount or 0)

    async def get_chunk_count_by_file_id_sync(self, file_id: str) -> int:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT COUNT(*) AS c FROM vector_chunks WHERE file_id = :file_id"),
                {"file_id": file_id},
            ).mappings().first()
            return int((row or {}).get("c", 0))

    async def retrieve_similar_sync(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        from src.services.embedding_service import generate_embedding

        query_vector = generate_embedding([query])[0]
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT content, vector_json FROM vector_chunks ORDER BY id DESC LIMIT 5000")
            ).mappings().all()
        scored: List[Dict[str, Any]] = []
        for row in rows:
            score = self._cosine_similarity(query_vector, self._load_vector(row.get("vector_json")))
            scored.append({"content": row.get("content", ""), "similarity": round(float(score), 3)})
        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:top_k]

    async def add_to_collection(self, collection: str, data: Dict[str, Any]):
        payload = dict(data or {})
        vector = payload.pop("vector", [])
        emb_dim = len(vector or [])
        payload["vector_json"] = json.dumps(vector, ensure_ascii=False)
        payload["create_time"] = payload.get("create_time") or self._now_cn_iso()
        payload["embedding_model"] = self._active_embedding_model()
        payload["embedding_dim"] = emb_dim
        payload["content_hash"] = self._content_hash(payload.get("content", ""))

        is_pg = "postgresql" in str(self.engine.url)
        returning = " RETURNING id" if is_pg else ""

        if collection == self.COLLECTION_HISTORICAL_CASES:
            payload.setdefault("tree_id", None)
            meta = payload.pop("metadata", None)
            meta_json = json.dumps(meta, ensure_ascii=False) if isinstance(meta, dict) else None
            inspector = inspect(self.engine)
            has_meta = False
            if inspector.has_table("historical_cases_vectors"):
                col_names = {c["name"] for c in inspector.get_columns("historical_cases_vectors")}
                has_meta = "metadata" in col_names
            cols = "case_id, case_number, location, slope_no, tree_id, source, embedding_model, embedding_dim, content_hash, content, vector_json, create_time"
            vals = ":case_id, :case_number, :location, :slope_no, :tree_id, :source, :embedding_model, :embedding_dim, :content_hash, :content, :vector_json, :create_time"
            if has_meta and meta_json:
                cols += ", metadata"
                vals += ", :metadata_json::jsonb" if is_pg else ", :metadata_json"
                payload["metadata_json"] = meta_json
            update_meta = ", metadata = EXCLUDED.metadata" if has_meta and meta_json else ""
            sql = text(
                f"""
                INSERT INTO historical_cases_vectors ({cols})
                VALUES ({vals})
                ON CONFLICT (embedding_model, case_id)
                DO UPDATE SET
                    case_number = EXCLUDED.case_number,
                    location = EXCLUDED.location,
                    slope_no = EXCLUDED.slope_no,
                    tree_id = EXCLUDED.tree_id,
                    source = EXCLUDED.source,
                    embedding_dim = EXCLUDED.embedding_dim,
                    content_hash = EXCLUDED.content_hash,
                    content = EXCLUDED.content,
                    vector_json = EXCLUDED.vector_json,
                    create_time = EXCLUDED.create_time{update_meta}
                """
                + returning
            )
        elif collection == self.COLLECTION_TREE_INVENTORY:
            payload.setdefault("tree_no", None)
            payload.setdefault("slope_id", None)
            payload.setdefault("source_row_index", 0)
            meta = payload.pop("metadata", None)
            meta_json = json.dumps(meta, ensure_ascii=False) if isinstance(meta, dict) else None
            inspector = inspect(self.engine)
            has_meta = False
            if inspector.has_table("tree_inventory_vectors"):
                cols_set = {c["name"] for c in inspector.get_columns("tree_inventory_vectors")}
                has_meta = "metadata" in cols_set
            cols = "tree_id, tree_no, slope_no, slope_id, species, location, source_row_index, embedding_model, embedding_dim, content_hash, content, vector_json, create_time"
            vals = ":tree_id, :tree_no, :slope_no, :slope_id, :species, :location, :source_row_index, :embedding_model, :embedding_dim, :content_hash, :content, :vector_json, :create_time"
            if has_meta and meta_json:
                cols += ", metadata"
                vals += ", :metadata_json::jsonb" if is_pg else ", :metadata_json"
                payload["metadata_json"] = meta_json
            update_meta = ", metadata = EXCLUDED.metadata" if has_meta and meta_json else ""
            sql = text(
                f"""
                INSERT INTO tree_inventory_vectors ({cols})
                VALUES ({vals})
                ON CONFLICT (embedding_model, slope_no, COALESCE(tree_no, '_NULL_'), source_row_index)
                DO UPDATE SET
                    tree_id = EXCLUDED.tree_id,
                    slope_id = EXCLUDED.slope_id,
                    species = EXCLUDED.species,
                    location = EXCLUDED.location,
                    embedding_dim = EXCLUDED.embedding_dim,
                    content_hash = EXCLUDED.content_hash,
                    content = EXCLUDED.content,
                    vector_json = EXCLUDED.vector_json,
                    create_time = EXCLUDED.create_time{update_meta}
                """
                + returning
            )
        elif collection == self.COLLECTION_KNOWLEDGE_DOCS:
            approved = payload.get("approved", True)
            payload.setdefault("approved", approved)
            meta = payload.get("metadata")
            if isinstance(meta, dict):
                payload["metadata_json"] = json.dumps(meta, ensure_ascii=False)
            else:
                payload["metadata_json"] = None
            cols = "doc_type, filename, approved, embedding_model, embedding_dim, content_hash, content, vector_json, create_time"
            vals = ":doc_type, :filename, :approved, :embedding_model, :embedding_dim, :content_hash, :content, :vector_json, :create_time"
            is_pg = "postgresql" in str(self.engine.url)
            inspector = inspect(self.engine)
            has_meta = False
            if inspector.has_table("knowledge_docs_vectors"):
                col_names = [c["name"] for c in inspector.get_columns("knowledge_docs_vectors")]
                has_meta = "metadata" in col_names
            if has_meta and payload.get("metadata_json") is not None:
                cols += ", metadata"
                vals += ", :metadata_json::jsonb" if is_pg else ", :metadata_json"
            update_meta = ", metadata = EXCLUDED.metadata" if has_meta and payload.get("metadata_json") is not None else ""
            sql = text(
                f"""
                INSERT INTO knowledge_docs_vectors ({cols})
                VALUES ({vals})
                ON CONFLICT (embedding_model, doc_type, filename)
                DO UPDATE SET
                    approved = EXCLUDED.approved,
                    embedding_dim = EXCLUDED.embedding_dim,
                    content_hash = EXCLUDED.content_hash,
                    content = EXCLUDED.content,
                    vector_json = EXCLUDED.vector_json,
                    create_time = EXCLUDED.create_time{update_meta}
                """
                + returning
            )
        else:
            raise ValueError(f"Unknown collection: {collection}")

        with self.engine.begin() as conn:
            result = conn.execute(sql, payload)
            if is_pg:
                row = result.fetchone()
                rid = row[0] if row else None
            else:
                rid = getattr(result, "lastrowid", None)
            return str(rid) if rid is not None else None

    async def add_batch_to_collection(self, collection: str, records: List[Dict[str, Any]]) -> List[str]:
        inserted: List[str] = []
        for record in records:
            rid = await self.add_to_collection(collection, record)
            if rid:
                inserted.append(rid)
        return inserted

    async def retrieve_from_collection(
        self,
        collection: str,
        query: str,
        top_k: int,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        from src.services.embedding_service import generate_embedding

        active_model = self._active_embedding_model()
        query_vector = generate_embedding([query])[0]
        filters = {k: v for k, v in (filters or {}).items() if v not in (None, "", [])}
        metadata_filters = {k: filters.pop(k) for k in ("knowledge_type", "entity_id") if k in filters}

        if collection == self.COLLECTION_HISTORICAL_CASES:
            table = "historical_cases_vectors"
            filter_fields = ("location", "slope_no", "case_number", "source", "tree_id")
        elif collection == self.COLLECTION_TREE_INVENTORY:
            table = "tree_inventory_vectors"
            filter_fields = ("location", "slope_no", "tree_id", "tree_no", "species")
        elif collection == self.COLLECTION_KNOWLEDGE_DOCS:
            table = "knowledge_docs_vectors"
            filter_fields = ("doc_type", "filename", "knowledge_type", "entity_id")
        else:
            raise ValueError(f"Unknown collection: {collection}")

        where_parts = ["embedding_model = :_active_model"]
        params: Dict[str, Any] = {**dict(filters), "_active_model": active_model}
        is_pg = "postgresql" in str(self.engine.url)
        inspector = inspect(self.engine)
        has_metadata = False
        if table in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns(table)}
            has_metadata = "metadata" in cols
        for field in filter_fields:
            if field in filters:
                if field == "slope_no" and is_pg:
                    # 规范化匹配：DB 中 11SW-A/FR24(3) 与 11SW-A/FR24 视为同一棵树
                    where_parts.append(
                        "regexp_replace(trim(COALESCE(slope_no, '')), '\\s*\\(\\d+\\)\\s*$', '') = :slope_no"
                    )
                else:
                    where_parts.append(f"{field} = :{field}")
        for field, val in metadata_filters.items():
            if has_metadata and val:
                if is_pg:
                    where_parts.append(f"(metadata->>'{field}') = :meta_{field}")
                else:
                    where_parts.append(f"json_extract(metadata, '$.{field}') = :meta_{field}")
                params[f"meta_{field}"] = str(val)
        base_where = " AND ".join(where_parts)
        if collection == self.COLLECTION_KNOWLEDGE_DOCS:
            base_where += " AND (COALESCE(approved, TRUE) = TRUE)"
        where_clause = "WHERE " + base_where
        sql = text(f"SELECT * FROM {table} {where_clause} ORDER BY id DESC LIMIT 5000")

        with self.engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()

        scored: List[Dict[str, Any]] = []
        for row in rows:
            score = self._cosine_similarity(query_vector, self._load_vector(row.get("vector_json")))
            payload = dict(row)
            payload.pop("vector_json", None)
            payload["similarity"] = round(float(score), 3)
            scored.append(payload)
        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:top_k]

    def approve_knowledge_doc(self, doc_type: str, filename: str) -> int:
        """Set approved=TRUE for a knowledge doc. Returns row count updated."""
        with self.engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE knowledge_docs_vectors
                    SET approved = TRUE
                    WHERE doc_type = :doc_type AND filename = :filename
                    """
                ),
                {"doc_type": doc_type, "filename": filename},
            )
            return int(result.rowcount or 0)

    def list_pending_knowledge_docs(self) -> List[Dict[str, Any]]:
        """List knowledge docs with approved=FALSE (or NULL)."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, doc_type, filename, content, create_time
                    FROM knowledge_docs_vectors
                    WHERE COALESCE(approved, FALSE) = FALSE
                    ORDER BY create_time DESC
                    """
                )
            ).mappings().all()
        return [dict(r) for r in rows]
