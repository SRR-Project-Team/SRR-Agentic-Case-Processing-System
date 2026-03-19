#!/usr/bin/env python3
"""File sorter for SRR case folders.

Recursively traverses case folders, extracts ZIPs, and classifies files
into 6 categories: ICC mail, TMO/RCC form, location plan, site photo, ZIP, unknown.
"""

from __future__ import annotations

import io
import mimetypes
import os
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.input_adapter import (
    FileCategory,
    FileManifest,
    ParsedDocument,
    SourceType,
    TmoFormType,
)


_SLOPE_PATTERN = re.compile(
    r"\b\d{1,2}[A-Z]{2,3}[-/][A-Z0-9/()\-]+\b",
    re.IGNORECASE,
)
_ICC_BLOCK_MARKERS = ("Complaint Details", "1823", "Specific Q&A", "Assignment History")
_LOCATION_KEYWORDS = ("location", "plan", "map", "位置", "平面图", "地圖")
_TMO_PREFIX = ("ASD", "TMO")
_RCC_PREFIX = ("RCC",)


def _guess_content_type(filename: str, fallback: str = "application/octet-stream") -> str:
    guessed, _ = mimetypes.guess_type(filename or "")
    return guessed or fallback


def _normalize_zip_path(path: str) -> str:
    safe = (path or "").replace("\\", "/").strip().lstrip("/")
    safe = safe.replace("../", "").replace("..", "")
    return safe


def _read_file_bytes(path: str) -> Optional[bytes]:
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None


def _classify_file(filename: str, content_type: str, content_preview: Optional[str] = None) -> FileCategory:
    """Classify a file into one of 6 categories based on extension and content."""
    name_lower = (filename or "").lower()
    ext = os.path.splitext(filename or "")[1].lower()
    preview = (content_preview or "")[:2000].lower()

    if ext == ".zip":
        return "zip"

    if ext == ".txt":
        if any(m in preview for m in _ICC_BLOCK_MARKERS):
            return "icc_mail"
        return "unknown"

    if ext in (".pdf", ".docx"):
        base = os.path.basename(name_lower)
        if any(base.upper().startswith(p) for p in _TMO_PREFIX):
            return "tmo_rcc_form"
        if any(base.upper().startswith(p) for p in _RCC_PREFIX):
            return "tmo_rcc_form"
        return "tmo_rcc_form" if "form" in name_lower or "referral" in name_lower else "unknown"

    if ext in (".jpg", ".jpeg", ".png"):
        if any(kw in name_lower for kw in _LOCATION_KEYWORDS):
            return "location_plan"
        if _SLOPE_PATTERN.search(filename or ""):
            return "location_plan"
        return "site_photo"

    return "unknown"


def _infer_source_type(filename: str, file_category: FileCategory) -> Optional[SourceType]:
    """Infer source type from filename and category."""
    name_upper = (filename or "").upper()
    if file_category == "icc_mail":
        return "ICC"
    if file_category == "tmo_rcc_form":
        if any(name_upper.startswith(p) for p in _RCC_PREFIX):
            return "RCC"
        if any(name_upper.startswith(p) for p in _TMO_PREFIX):
            return "TMO"
    return None


def _expand_zip_bytes(
    raw: bytes,
    parent: str = "",
    manifest: Optional[FileManifest] = None,
    from_zip: Optional[List[str]] = None,
    skip_unknown: bool = True,
) -> List[ParsedDocument]:
    """Recursively expand ZIP bytes into ParsedDocument list."""
    docs: List[ParsedDocument] = []
    fz = from_zip or []
    mf = manifest or FileManifest()

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            for entry in zf.infolist():
                if entry.is_dir():
                    continue
                name = _normalize_zip_path(entry.filename)
                if not name or name.startswith("__MACOSX/"):
                    continue
                rel_name = f"{parent}/{name}" if parent else name
                with zf.open(entry, "r") as f:
                    file_bytes = f.read()
                if name.lower().endswith(".zip"):
                    sub_docs = _expand_zip_bytes(
                        file_bytes,
                        parent=rel_name[:-4],
                        manifest=mf,
                        from_zip=fz,
                        skip_unknown=skip_unknown,
                    )
                    docs.extend(sub_docs)
                    fz.append(f"{rel_name} -> {len(sub_docs)} files")
                    continue
                content_type = _guess_content_type(rel_name)
                preview = None
                if "text" in (content_type or ""):
                    try:
                        preview = file_bytes.decode("utf-8", errors="ignore")
                    except Exception:
                        pass
                category = _classify_file(rel_name, content_type or "", preview)
                mf.total_files += 1
                if skip_unknown and category == "unknown":
                    mf.skipped += 1
                    fz.append(rel_name)
                    continue
                doc = ParsedDocument(
                    filename=rel_name,
                    content_type=content_type or "application/octet-stream",
                    file_bytes=file_bytes,
                    source="zip",
                    file_category=category,
                    source_type=_infer_source_type(rel_name, category),
                )
                docs.append(doc)
                mf.processed += 1
                fz.append(rel_name)
    except Exception:
        pass
    return docs


def sort_and_parse_folder(
    folder_path: str,
    *,
    skip_unknown: bool = True,
) -> Tuple[List[ParsedDocument], FileManifest]:
    """
    Recursively traverse folder, expand ZIPs, classify files, and return
    ParsedDocument list with file manifest.

    Args:
        folder_path: Path to case folder
        skip_unknown: If True, skip files classified as unknown (still counted in manifest)

    Returns:
        (list of ParsedDocument, FileManifest)
    """
    manifest = FileManifest()
    all_docs: List[ParsedDocument] = []
    from_zip_entries: List[str] = []

    if not folder_path or not os.path.isdir(folder_path):
        return all_docs, manifest

    for root, _dirs, files in os.walk(folder_path):
        for fname in files:
            if fname.startswith("."):
                continue
            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, folder_path)
            manifest.total_files += 1

            if fname.lower().endswith(".zip"):
                raw = _read_file_bytes(full_path)
                if raw:
                    parent = os.path.splitext(fname)[0]
                    sub_docs = _expand_zip_bytes(
                        raw,
                        parent=parent,
                        manifest=manifest,
                        from_zip=from_zip_entries,
                        skip_unknown=skip_unknown,
                    )
                    all_docs.extend(sub_docs)
                continue

            raw = _read_file_bytes(full_path)
            if not raw:
                manifest.skipped += 1
                continue
            content_type = _guess_content_type(rel_path)
            preview = None
            if "text" in content_type:
                try:
                    preview = raw.decode("utf-8", errors="ignore")
                except Exception:
                    pass
            category = _classify_file(rel_path, content_type, preview)
            if skip_unknown and category == "unknown":
                manifest.skipped += 1
                continue
            doc = ParsedDocument(
                filename=rel_path,
                content_type=content_type,
                file_bytes=raw,
                source="upload",
                file_category=category,
                source_type=_infer_source_type(rel_path, category),
            )
            all_docs.append(doc)
            manifest.processed += 1

    manifest.from_zip = from_zip_entries
    manifest.skipped = manifest.total_files - manifest.processed
    return all_docs, manifest


def sort_uploaded_files(
    files: List[Tuple[str, bytes]],
    *,
    skip_unknown: bool = True,
) -> Tuple[List[ParsedDocument], FileManifest]:
    """
    Classify a list of (filename, bytes) uploads. Handles ZIP expansion.

    Returns:
        (list of ParsedDocument, FileManifest)
    """
    manifest = FileManifest()
    all_docs: List[ParsedDocument] = []
    from_zip_entries: List[str] = []

    for filename, raw in files or []:
        manifest.total_files += 1
        content_type = _guess_content_type(filename or "")
        is_zip = (filename or "").lower().endswith(".zip") or "zip" in (content_type or "")

        if is_zip:
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                    for entry in zf.infolist():
                        if entry.is_dir():
                            continue
                        name = _normalize_zip_path(entry.filename)
                        if not name or name.startswith("__MACOSX/"):
                            continue
                        with zf.open(entry, "r") as f:
                            file_bytes = f.read()
                        if name.lower().endswith(".zip"):
                            manifest.skipped += 1
                            continue
                        parent = os.path.splitext(filename or "archive")[0]
                        rel_name = f"{parent}/{name}"
                        ct = _guess_content_type(rel_name)
                        preview = None
                        if "text" in ct:
                            try:
                                preview = file_bytes.decode("utf-8", errors="ignore")
                            except Exception:
                                pass
                        category = _classify_file(rel_name, ct, preview)
                        if skip_unknown and category == "unknown":
                            manifest.skipped += 1
                            from_zip_entries.append(rel_name)
                            continue
                        doc = ParsedDocument(
                            filename=rel_name,
                            content_type=ct,
                            file_bytes=file_bytes,
                            source="zip",
                            file_category=category,
                            source_type=_infer_source_type(rel_name, category),
                        )
                        all_docs.append(doc)
                        manifest.processed += 1
                        from_zip_entries.append(rel_name)
            except Exception:
                manifest.skipped += 1
            continue

        preview = None
        if "text" in content_type:
            try:
                preview = raw.decode("utf-8", errors="ignore")
            except Exception:
                pass
        category = _classify_file(filename or "", content_type, preview)
        if skip_unknown and category == "unknown":
            manifest.skipped += 1
            continue
        doc = ParsedDocument(
            filename=filename or "uploaded-file",
            content_type=content_type,
            file_bytes=raw,
            source="upload",
            file_category=category,
            source_type=_infer_source_type(filename or "", category),
        )
        all_docs.append(doc)
        manifest.processed += 1

    manifest.from_zip = from_zip_entries
    manifest.skipped = manifest.total_files - manifest.processed
    return all_docs, manifest
