"""
Unified case number parser for 1823/TMO/RCC (R15).

Centralizes parsing of three case number formats:
- 1823 (ICC): 3-XXXXXXXXXX (10 digits)
- TMO: ASD-HKE-2026001-CYC or "TMO Ref. ASD-WC-20250089-PP"
- RCC: 8-digit or "RCC#84878800"
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# 1823: 3- followed by 10 digits
_PATTERN_1823 = re.compile(r"1823\s+case:\s*([\w\-:]+)", re.IGNORECASE)
_PATTERN_1823_DIRECT = re.compile(r"\b(3-\d{10})\b")

# TMO: ASD-XXX-YYYYYY-ZZ format or "TMO Ref. ..."
_PATTERN_TMO_REF = re.compile(r"TMO\s+Ref\.\s*([A-Z0-9\-]+)", re.IGNORECASE)
_PATTERN_TMO_DIRECT = re.compile(r"\b(ASD-[A-Z]+-\d+-[A-Z]+)\b", re.IGNORECASE)

# RCC: 8-digit or patterns in content
_PATTERN_RCC_FILENAME = re.compile(r"RCC[#\s]*(\d+)", re.IGNORECASE)
_PATTERN_RCC_CONTENT = [
    re.compile(r"Call\s+Reference\s+No[:\s]+(\d+)", re.IGNORECASE),
    re.compile(r"RCC[#\s]*(\d+)", re.IGNORECASE),
    re.compile(r"案件編號[：:]\s*([A-Z0-9\-]+)", re.IGNORECASE),
    re.compile(r"Case\s+No\.?\s*([A-Z0-9\-]+)", re.IGNORECASE),
    re.compile(r"編號[：:]\s*([A-Z0-9\-]+)", re.IGNORECASE),
    re.compile(r"\b(\d{8})\b"),  # 8-digit standalone
]

SourceType = Optional[str]  # "ICC" | "TMO" | "RCC"


def parse_case_number(
    content: str,
    source_hint: Optional[str] = None,
    file_path: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    """
    Parse case number from content, optionally with source hint or file path.

    Args:
        content: Raw text content (TXT body, PDF text, etc.)
        source_hint: "ICC" | "TMO" | "RCC" to try that format first
        file_path: Optional file path (used for RCC filename extraction)

    Returns:
        (case_number, inferred_source). Empty string and None if not found.
    """
    content = content or ""
    file_path = file_path or ""

    # Try source-specific extraction first when hint is given
    if source_hint:
        hint_upper = source_hint.upper()
        if hint_upper in ("ICC", "1823"):
            num = _try_1823(content)
            if num:
                return (num, "ICC")
        elif hint_upper == "TMO":
            num = _try_tmo(content)
            if num:
                return (num, "TMO")
        elif hint_upper == "RCC":
            num = _try_rcc(content, file_path)
            if num:
                return (num, "RCC")

    # No hint or not found: try all formats and infer from first match
    num, src = _try_1823(content)
    if num:
        return (num, src or "ICC")

    num, src = _try_tmo(content)
    if num:
        return (num, src or "TMO")

    num, src = _try_rcc(content, file_path)
    if num:
        return (num, src or "RCC")

    return ("", None)


def _try_1823(content: str) -> Tuple[str, Optional[str]]:
    match = _PATTERN_1823.search(content)
    if match:
        num = match.group(1).strip()
        if re.match(r"3-\d{10}", num):
            logger.info("Parsed 1823 case number: %s", num)
            return (num, "ICC")
    match = _PATTERN_1823_DIRECT.search(content)
    if match:
        num = match.group(1).strip()
        logger.info("Parsed 1823 case number (direct): %s", num)
        return (num, "ICC")
    return ("", None)


def _try_tmo(content: str) -> Tuple[str, Optional[str]]:
    match = _PATTERN_TMO_REF.search(content)
    if match:
        num = match.group(1).strip()
        logger.info("Parsed TMO reference: %s", num)
        return (num, "TMO")
    match = _PATTERN_TMO_DIRECT.search(content)
    if match:
        num = match.group(1).strip()
        logger.info("Parsed TMO reference (direct): %s", num)
        return (num, "TMO")
    return ("", None)


def _try_rcc(content: str, file_path: str) -> Tuple[str, Optional[str]]:
    if file_path:
        filename = os.path.basename(file_path)
        match = _PATTERN_RCC_FILENAME.search(filename)
        if match:
            num = match.group(1).strip()
            logger.info("Parsed RCC case number from filename: %s", num)
            return (num, "RCC")

    for pattern in _PATTERN_RCC_CONTENT:
        match = pattern.search(content)
        if match:
            num = match.group(1).strip()
            # Prefer 8-digit for RCC when it looks like RCC format
            if len(num) == 8 and num.isdigit():
                logger.info("Parsed RCC case number from content: %s", num)
                return (num, "RCC")
            # Other patterns may return alphanumeric
            logger.info("Parsed RCC-like case number from content: %s", num)
            return (num, "RCC")

    return ("", None)


def normalize_case_number(case_number: str, source: str) -> str:
    """
    Normalize case number format for validation/correction.

    Args:
        case_number: Raw parsed case number
        source: "ICC" | "TMO" | "RCC"

    Returns:
        Normalized case number string.
    """
    if not case_number or not source:
        return case_number or ""

    raw = str(case_number).strip().upper()
    src = str(source).upper()

    if src in ("ICC", "1823"):
        # 3-XXXXXXXXXX: ensure hyphen and 10 digits
        m = re.match(r"3-?(\d{10})", raw)
        if m:
            return f"3-{m.group(1)}"
        if re.match(r"3-\d{10}", raw):
            return raw

    elif src == "TMO":
        # ASD-XXX-YYYYYY-ZZ: ensure consistent hyphenation
        return raw.replace(" ", "")

    elif src == "RCC":
        # 8-digit: strip non-digits, take first 8
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 8:
            return digits[:8]

    return raw
