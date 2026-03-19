#!/usr/bin/env python3
"""Unified knowledge base management service."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import pandas as pd
from config.settings import MAX_RAG_CHUNKS
from core.embedding import embed_texts
from database import get_db_manager
from database.models import KnowledgeBaseFile
from services.slope_data_parser import SlopeDataParser
from services.tree_inventory_content_service import build_tree_content
from services.text_splitter import split_text
from utils.file_processors import (
    detect_file_type_from_extension,
    get_file_metadata,
    process_file,
)
from utils.file_storage import get_file_preview, get_local_path_for_reading, save_rag_file

VALID_TEMPLATE_SLOTS = ("interim", "final", "wrong_referral")


class KnowledgeBaseService:
    CATEGORY_GENERAL = "general"
    CATEGORY_SLOPE_DATA = "slope_data"
    CATEGORY_TREE_INVENTORY = "tree_inventory"
    CATEGORY_TEMPLATE = "template"

    VALID_CATEGORIES = {
        CATEGORY_GENERAL,
        CATEGORY_SLOPE_DATA,
        CATEGORY_TREE_INVENTORY,
        CATEGORY_TEMPLATE,
    }

    def __init__(self) -> None:
        self.db_manager = get_db_manager()
        self.slope_parser = SlopeDataParser()

    def _create_vector_client(self):
        from core.pg_vector_store import PgVectorStore

        return PgVectorStore()

    def normalize_category(self, category: Optional[str]) -> str:
        value = (category or self.CATEGORY_GENERAL).strip().lower()
        return value if value in self.VALID_CATEGORIES else self.CATEGORY_GENERAL

    def _match_column(self, columns: List[str], candidates: tuple[str, ...]) -> str:
        lowered = {c.lower().strip(): c for c in columns}
        for cand in candidates:
            for lower_col, original in lowered.items():
                if cand in lower_col:
                    return original
        return ""

    def _parse_float(self, val: Any) -> Optional[float]:
        """Parse value to float; return None for empty/invalid."""
        if val is None or val == "":
            return None
        if isinstance(val, (int, float)):
            if isinstance(val, float) and pd.isna(val):
                return None
            return float(val)
        try:
            return float(str(val).strip())
        except (ValueError, TypeError):
            return None

    def _build_tree_inventory_records(self, file_path: str) -> List[Dict[str, Any]]:
        """Parse tabular tree inventory files into structured vector records.
        Uses same content format as init_vector_store via build_tree_content."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext in (".xlsx", ".xls"):
            frames = pd.read_excel(file_path, sheet_name=None)
            df = pd.concat(frames.values(), ignore_index=True) if frames else pd.DataFrame()
        elif ext == ".csv":
            df = pd.read_csv(file_path)
        elif ext == ".json":
            df = pd.read_json(file_path)
        else:
            return []

        if df.empty:
            return []
        df = df.fillna("")
        columns = [str(c) for c in df.columns]

        slope_no_col = self._match_column(
            columns,
            ("slope no", "slope_no", "slopeno", "slope"),
        )
        slope_id_col = self._match_column(
            columns,
            ("slope id", "slope_id"),
        )
        tree_no_col = self._match_column(
            columns,
            ("tree no", "tree_id", "tree number", "tree no.", "tree"),
        )
        scientific_name_col = self._match_column(
            columns,
            ("scientific name", "species", "species_en", "tree species", "species name"),
        )
        chinese_name_col = self._match_column(
            columns,
            ("chinese name", "chinese_name", "species_cn"),
        )
        height_col = self._match_column(
            columns,
            ("height (m)", "height_m", "height"),
        )
        dbh_col = self._match_column(
            columns,
            ("dbh (mm)", "dbh_mm", "dbh"),
        )
        health_col = self._match_column(
            columns,
            ("health (good/fair/poor)", "health", "health status"),
        )
        classification_col = self._match_column(
            columns,
            ("classification", "classification (type a", "type a type b"),
        )

        records: List[Dict[str, Any]] = []
        for idx, row in df.iterrows():
            slope_no_raw = str(row.get(slope_no_col, "")).strip() if slope_no_col else ""
            slope_no = self.slope_parser.normalize_slope_no(slope_no_raw) if slope_no_raw else ""
            slope_id = str(row.get(slope_id_col, "")).strip() if slope_id_col else ""
            tree_no_raw = row.get(tree_no_col)
            tree_no = str(tree_no_raw).strip() if tree_no_raw not in (None, "") else ""
            scientific_name = str(row.get(scientific_name_col, "")).strip() if scientific_name_col else ""
            chinese_name = str(row.get(chinese_name_col, "")).strip() if chinese_name_col else ""
            height_m = self._parse_float(row.get(height_col)) if height_col else None
            dbh_mm = self._parse_float(row.get(dbh_col)) if dbh_col else None
            health = str(row.get(health_col, "")).strip() if health_col else ""
            classification = str(row.get(classification_col, "")).strip() if classification_col else ""

            if not (tree_no or slope_no or scientific_name or chinese_name):
                continue

            row_dict = {
                "slope_no": slope_no,
                "slope_id": slope_id,
                "tree_no": tree_no or None,
                "scientific_name": scientific_name,
                "chinese_name": chinese_name,
                "height_m": height_m,
                "dbh_mm": dbh_mm,
                "health": health,
                "classification": classification,
            }
            content = build_tree_content(row_dict)
            tree_id_full = f"{slope_no} {tree_no}".strip() if tree_no else slope_no
            records.append(
                {
                    "tree_id": tree_id_full,
                    "tree_no": tree_no or None,
                    "slope_no": slope_no,
                    "slope_id": slope_id,
                    "species": scientific_name,
                    "location": "",
                    "source_row_index": int(idx),
                    "content": content,
                }
            )
        return records

    async def upload_file(
        self,
        *,
        file: Any,
        uploaded_by: str,
        category: Optional[str],
        background_tasks: Any,
    ) -> Dict[str, Any]:
        file_type = detect_file_type_from_extension(file.filename)
        if file_type == "unknown":
            raise ValueError(f"Unsupported file type: {file.filename}")

        category = self.normalize_category(category)
        content = await file.read()
        file_size = len(content)
        from utils.hash_utils import calculate_file_hash

        file_hash = calculate_file_hash(content)
        existing = self.db_manager.check_kb_file_duplicate(
            file_hash,
            filename=file.filename,
            file_size=file_size,
        )
        if existing:
            raise ValueError(f"文件已存在，请勿重复上传 (已有: {existing.get('filename', '')})")

        full_path, relative_path = save_rag_file(content, file.filename)

        session = self.db_manager.get_session()
        try:
            kb_file = KnowledgeBaseFile(
                filename=file.filename,
                file_type=file_type,
                file_hash=file_hash,
                file_path=relative_path,
                file_size=file_size,
                mime_type=file.content_type or "application/octet-stream",
                uploaded_by=uploaded_by,
                category=category,
                processed=False,
            )
            session.add(kb_file)
            session.commit()
            file_id = kb_file.id
            response_data = {
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
            self.process_file_background,
            file_id=file_id,
            full_path=full_path,
            relative_path=relative_path,
            file_type=file_type,
            filename=file.filename,
            mime_type=file.content_type or "application/octet-stream",
            file_size=file_size,
            category=category,
        )
        return response_data

    async def upload_template_file(
        self,
        *,
        file: Any,
        reply_type: str,
        uploaded_by: str,
        background_tasks: Any,
    ) -> Dict[str, Any]:
        """Upload a template file to a fixed slot; overwrites existing template for that slot."""
        if reply_type not in VALID_TEMPLATE_SLOTS:
            raise ValueError(
                f"Invalid reply_type. Must be one of: {', '.join(VALID_TEMPLATE_SLOTS)}"
            )
        file_type = detect_file_type_from_extension(file.filename)
        if file_type != "word":
            raise ValueError("Template must be a .docx file")

        self.db_manager.deactivate_template_slot(reply_type)

        content = await file.read()
        file_size = len(content)
        from utils.hash_utils import calculate_file_hash

        file_hash = calculate_file_hash(content)
        existing = self.db_manager.check_kb_file_duplicate(
            file_hash,
            filename=file.filename,
            file_size=file_size,
        )
        if existing:
            raise ValueError(f"文件已存在，请勿重复上传 (已有: {existing.get('filename', '')})")

        full_path, relative_path = save_rag_file(content, file.filename)

        session = self.db_manager.get_session()
        try:
            kb_file = KnowledgeBaseFile(
                filename=file.filename,
                file_type=file_type,
                file_hash=file_hash,
                file_path=relative_path,
                file_size=file_size,
                mime_type=file.content_type or "application/octet-stream",
                uploaded_by=uploaded_by,
                category=self.CATEGORY_TEMPLATE,
                processed=False,
            )
            kb_file.set_metadata({"reply_type": reply_type})
            session.add(kb_file)
            session.commit()
            file_id = kb_file.id
            response_data = {
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
            self.process_file_background,
            file_id=file_id,
            full_path=full_path,
            relative_path=relative_path,
            file_type=file_type,
            filename=file.filename,
            mime_type=file.content_type or "application/octet-stream",
            file_size=file_size,
            category=self.CATEGORY_TEMPLATE,
            reply_type=reply_type,
        )
        return response_data

    def get_template_by_slot(self, reply_type: str) -> Optional[Dict[str, Any]]:
        """Get the active template file for the given reply_type slot."""
        return self.db_manager.get_template_file_by_slot(reply_type)

    def get_template_content_by_slot(self, reply_type: str) -> Optional[str]:
        """Read template file from KB and extract full text content."""
        kb_file = self.get_template_by_slot(reply_type)
        if not kb_file:
            return None
        relative_path = kb_file.get("file_path")
        file_type = kb_file.get("file_type", "word")
        if not relative_path:
            return None
        local_path = get_local_path_for_reading(relative_path)
        if not local_path:
            return None
        try:
            return process_file(local_path, file_type)
        except Exception as e:
            print(f"❌ 加载模板文件失败: {e}")
            return None

    def get_template_slots_status(self) -> Dict[str, Optional[Dict[str, Any]]]:
        """Get status of all 3 template slots: { interim: {...} | null, final: {...}, wrong_referral: {...} }."""
        result: Dict[str, Optional[Dict[str, Any]]] = {}
        for slot in VALID_TEMPLATE_SLOTS:
            kb_file = self.get_template_by_slot(slot)
            if kb_file:
                result[slot] = {
                    "filename": kb_file.get("filename"),
                    "upload_time": kb_file.get("upload_time"),
                    "file_id": kb_file.get("id"),
                }
            else:
                result[slot] = None
        return result

    async def process_file_background(
        self,
        *,
        file_id: int,
        full_path: str,
        relative_path: str,
        file_type: str,
        filename: str,
        mime_type: str,
        file_size: int,
        category: str,
        reply_type: Optional[str] = None,
    ) -> None:
        try:
            local_path = get_local_path_for_reading(relative_path)
            if not local_path:
                raise FileNotFoundError(f"Cannot resolve file for processing: {relative_path}")

            text = process_file(local_path, file_type)
            metadata = get_file_metadata(local_path, file_type)
            preview = get_file_preview(relative_path, file_type, max_length=500) or ""

            if category == self.CATEGORY_SLOPE_DATA:
                parsed = self.slope_parser.parse_file(local_path)
                metadata["slope_mapping_records"] = parsed.get("records", 0)
                metadata["slope_mapping_columns"] = parsed.get("columns", [])

            if reply_type and reply_type in VALID_TEMPLATE_SLOTS:
                metadata["reply_type"] = reply_type

            chunks = split_text(text, chunk_size=1000, chunk_overlap=150) if text else []
            if len(chunks) > MAX_RAG_CHUNKS:
                ratio = max(2, len(chunks) // MAX_RAG_CHUNKS)
                adaptive_chunk_size = min(4000, 1000 * ratio)
                chunks = split_text(text, chunk_size=adaptive_chunk_size, chunk_overlap=200)

            embeddings = embed_texts(chunks) if chunks else []
            vector_ids = []
            vector_store = self._create_vector_client()
            if chunks and embeddings:
                vector_ids = await vector_store.add_vectors_with_file_id_sync(
                    f"rag_file_{file_id}", chunks, embeddings
                )

            if category == self.CATEGORY_TREE_INVENTORY:
                tree_records = self._build_tree_inventory_records(full_path)
                metadata["tree_inventory_records"] = len(tree_records)
                if tree_records:
                    tree_contents = [r["content"] for r in tree_records]
                    tree_embeddings = embed_texts(tree_contents)
                    tree_payload = []
                    for record, embedding in zip(tree_records, tree_embeddings):
                        rec = {**record, "vector": embedding}
                        entity_id = record.get("tree_id") or record.get("slope_no") or ""
                        rec["metadata"] = {"knowledge_type": "entity", "entity_id": entity_id}
                        tree_payload.append(rec)
                    if tree_payload:
                        await vector_store.add_batch_to_collection(
                            vector_store.COLLECTION_TREE_INVENTORY, tree_payload
                        )

            session = self.db_manager.get_session()
            try:
                kb_file = session.query(KnowledgeBaseFile).get(file_id)
                if not kb_file:
                    return
                kb_file.file_type = file_type
                kb_file.file_path = relative_path
                kb_file.file_size = file_size
                kb_file.mime_type = mime_type
                kb_file.processed = True
                kb_file.chunk_count = len(chunks)
                kb_file.preview_text = preview
                kb_file.processing_error = None
                kb_file.category = self.normalize_category(category)
                kb_file.set_metadata(metadata)
                kb_file.set_vector_ids(vector_ids)
                session.commit()
            finally:
                session.close()
        except Exception as exc:
            session = self.db_manager.get_session()
            try:
                kb_file = session.query(KnowledgeBaseFile).get(file_id)
                if kb_file:
                    kb_file.processing_error = str(exc)
                    kb_file.processed = False
                    session.commit()
            finally:
                session.close()

    def get_stats(self, user_phone: str, role: str) -> Dict[str, Any]:
        session = self.db_manager.get_session()
        try:
            query = session.query(KnowledgeBaseFile).filter(KnowledgeBaseFile.is_active.is_(True))
            rows = query.all()
            by_category: Dict[str, int] = {}
            processed = 0
            pending = 0
            for row in rows:
                category = getattr(row, "category", self.CATEGORY_GENERAL) or self.CATEGORY_GENERAL
                by_category[category] = by_category.get(category, 0) + 1
                if row.processed:
                    processed += 1
                else:
                    pending += 1
            return {
                "total_files": len(rows),
                "processed_files": processed,
                "pending_files": pending,
                "categories": by_category,
            }
        finally:
            session.close()

    def refresh(
        self,
        *,
        background_tasks: Any,
        user_phone: str,
        role: str,
        category: Optional[str] = None,
        file_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        from utils.file_storage import file_exists

        session = self.db_manager.get_session()
        try:
            query = session.query(KnowledgeBaseFile).filter(KnowledgeBaseFile.is_active.is_(True))
            if file_id is not None:
                query = query.filter(KnowledgeBaseFile.id == file_id)
            if category:
                query = query.filter(KnowledgeBaseFile.category == self.normalize_category(category))
            targets = query.all()

            queued = 0
            for row in targets:
                if not file_exists(row.file_path):
                    continue
                row.processed = False
                row.processing_error = None
                row_category = getattr(row, "category", self.CATEGORY_GENERAL)
                reply_type_arg = (
                    row.get_metadata().get("reply_type")
                    if row_category == self.CATEGORY_TEMPLATE
                    else None
                )
                background_tasks.add_task(
                    self.process_file_background,
                    file_id=row.id,
                    full_path=row.file_path,
                    relative_path=row.file_path,
                    file_type=row.file_type,
                    filename=row.filename,
                    mime_type=row.mime_type,
                    file_size=row.file_size,
                    category=row_category,
                    reply_type=reply_type_arg,
                )
                queued += 1
            session.commit()
            return {"queued": queued, "total_candidates": len(targets)}
        finally:
            session.close()

    def precheck_upload(
        self,
        *,
        filename: str,
        file_hash: Optional[str],
        file_size: Optional[int],
        user_phone: str,
        role: str,
    ) -> Dict[str, Any]:
        """Upload precheck for KB files with 3-result status."""
        result = self.db_manager.precheck_kb_upload(
            filename=filename,
            file_hash=file_hash,
            file_size=file_size,
            user_phone=user_phone,
            role=role,
        )
        status = result.get("result", "NOT_FOUND")
        if status == "FOUND_SAME_HASH":
            result["message"] = "文件内容已存在于知识库中。"
        elif status == "FOUND_SAME_NAME_DIFF_HASH":
            result["message"] = "检测到同名文件，但内容已变化，可作为新版本上传。"
        else:
            result["message"] = "未发现重复文件，可上传。"
        return result
