from __future__ import annotations

import io
import mimetypes
import os
import zipfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from fastapi import UploadFile

SourceType = Literal["ICC", "TMO", "RCC", "OTHER"]
FileCategory = Literal[
    "icc_mail",
    "tmo_rcc_form",
    "location_plan",
    "site_photo",
    "zip",
    "unknown",
]
TmoFormType = Literal["Form1", "Form2", "HazardousReferral"]


@dataclass
class AttachmentItem:
    """Single attachment with optional extracted metadata."""

    file: str
    extracted: Optional[Dict[str, Any]] = None


@dataclass
class FileManifest:
    """Summary of file processing."""

    total_files: int = 0
    processed: int = 0
    skipped: int = 0
    from_zip: List[str] = field(default_factory=list)


@dataclass
class ParsedDocument:
    filename: str
    content_type: str
    file_bytes: bytes
    source: str = "upload"
    # Enhanced fields for SRR architecture
    source_type: Optional[SourceType] = None
    case_id: Optional[str] = None
    tmo_form_type: Optional[TmoFormType] = None
    raw_text: str = ""
    parsed_fields: Dict[str, Any] = field(default_factory=dict)
    attachments: Dict[str, Any] = field(default_factory=lambda: {
        "core_document": "",
        "referral_forms": [],
        "location_plans": [],
        "site_photos": [],
        "skipped": [],
    })
    file_manifest: Optional[FileManifest] = None
    file_category: Optional[FileCategory] = None


def _guess_content_type(filename: str, fallback: str = "application/octet-stream") -> str:
    guessed, _ = mimetypes.guess_type(filename or "")
    return guessed or fallback


def _normalize_zip_path(path: str) -> str:
    safe = (path or "").replace("\\", "/").strip().lstrip("/")
    safe = safe.replace("../", "").replace("..", "")
    return safe


def _expand_zip_bytes(data: bytes, *, parent: str = "") -> List[ParsedDocument]:
    parsed: List[ParsedDocument] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for entry in zf.infolist():
            if entry.is_dir():
                continue
            name = _normalize_zip_path(entry.filename)
            if not name or name.startswith("__MACOSX/"):
                continue
            rel_name = f"{parent}/{name}" if parent else name
            with zf.open(entry, "r") as f:
                raw = f.read()
            if name.lower().endswith(".zip"):
                parsed.extend(_expand_zip_bytes(raw, parent=rel_name[:-4]))
                continue
            parsed.append(
                ParsedDocument(
                    filename=rel_name,
                    content_type=_guess_content_type(rel_name),
                    file_bytes=raw,
                    source="zip",
                )
            )
    return parsed


async def parse_uploaded_documents(files: List[UploadFile]) -> List[ParsedDocument]:
    documents: List[ParsedDocument] = []
    for upload in files or []:
        raw = await upload.read()
        filename = upload.filename or "uploaded-file"
        content_type = upload.content_type or _guess_content_type(filename)
        is_zip = filename.lower().endswith(".zip") or content_type in {
            "application/zip",
            "application/x-zip-compressed",
        }
        if is_zip:
            try:
                documents.extend(_expand_zip_bytes(raw, parent=os.path.splitext(filename)[0]))
                continue
            except Exception:
                # Keep fallback behavior: if unzip fails, process raw upload as a normal file.
                pass
        documents.append(
            ParsedDocument(
                filename=filename,
                content_type=content_type,
                file_bytes=raw,
                source="upload",
            )
        )
    return documents

