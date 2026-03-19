"""Convert Office files (xlsx, docx, pptx) to PDF via LibreOffice headless."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from typing import Optional


_CACHE_DIR: Optional[str] = None


def _get_cache_dir() -> str:
    global _CACHE_DIR
    if _CACHE_DIR is None:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        _CACHE_DIR = os.path.join(base, "data", "pdf_cache")
        os.makedirs(_CACHE_DIR, exist_ok=True)
    return _CACHE_DIR


def _find_libreoffice() -> Optional[str]:
    """Return the path to the libreoffice binary, or None."""
    for candidate in ("libreoffice", "soffice", "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        path = shutil.which(candidate)
        if path:
            return path
    if os.path.isfile("/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        return "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    return None


def _cache_key(source_path: str) -> str:
    stat = os.stat(source_path)
    raw = f"{os.path.abspath(source_path)}:{stat.st_size}:{stat.st_mtime_ns}"
    return hashlib.sha256(raw.encode()).hexdigest()


def convert_to_pdf(source_path: str) -> Optional[str]:
    """Convert an Office file to PDF. Returns the PDF path or None on failure.

    Converted PDFs are cached by (path, size, mtime) so repeated previews
    are instant.
    """
    lo = _find_libreoffice()
    if lo is None:
        return None

    cache_dir = _get_cache_dir()
    key = _cache_key(source_path)
    cached = os.path.join(cache_dir, f"{key}.pdf")
    if os.path.isfile(cached):
        return cached

    with tempfile.TemporaryDirectory(prefix="lo_conv_") as tmpdir:
        try:
            subprocess.run(
                [lo, "--headless", "--norestore", "--convert-to", "pdf", "--outdir", tmpdir, source_path],
                timeout=60,
                check=True,
                capture_output=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
            print(f"LibreOffice conversion failed: {exc}")
            return None

        base = os.path.splitext(os.path.basename(source_path))[0]
        pdf_path = os.path.join(tmpdir, f"{base}.pdf")
        if not os.path.isfile(pdf_path):
            return None

        shutil.move(pdf_path, cached)

    return cached


def is_office_type(file_type: str) -> bool:
    return file_type in ("excel", "word", "powerpoint")


def libreoffice_available() -> bool:
    return _find_libreoffice() is not None
