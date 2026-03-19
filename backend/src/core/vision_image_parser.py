#!/usr/bin/env python3
"""Vision image parser for SRR case files.

Extracts structured data from:
- location_plan: slope number, area, road name
- site_photo: tree/slope condition description
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

ImageCategory = Literal["location_plan", "site_photo"]


def _encode_image(file_path: str) -> Optional[tuple[str, str]]:
    """Read image file and return (base64_data, mime_type)."""
    if not file_path or not os.path.isfile(file_path):
        return None
    ext = os.path.splitext(file_path)[1].lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    try:
        with open(file_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        return (data, mime)
    except Exception as e:
        logger.warning("Failed to read image %s: %s", file_path, e)
        return None


def _encode_image_bytes(file_bytes: bytes, filename: str) -> tuple[str, str]:
    """Encode bytes to base64. Return (base64_data, mime_type)."""
    ext = os.path.splitext(filename or "")[1].lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    data = base64.b64encode(file_bytes).decode("utf-8")
    return (data, mime)


def parse_location_plan(
    image_path: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
    filename: str = "",
) -> Dict[str, Any]:
    """
    Extract slope number, area, road from a location plan image.

    Returns:
        {"slope_no": str, "area": str, "road": str} or empty dict on failure.
    """
    if image_path:
        encoded = _encode_image(image_path)
    elif image_bytes:
        encoded = _encode_image_bytes(image_bytes, filename)
    else:
        return {}

    if not encoded:
        return {}

    data, mime = encoded
    try:
        from services.llm_service import get_llm_service

        llm = get_llm_service()
        if not llm.client:
            logger.warning("Vision API not available, LLM client not initialized")
            return {}
    except Exception as e:
        logger.warning("Cannot get LLM service for Vision: %s", e)
        return {}

    prompt = """Extract the following from this location plan / map image. Return JSON only.
{
  "slope_no": "slope number if visible (e.g. 11SW-C/ND31, 15NE-AF91)",
  "area": "district or area name (e.g. 北角, North Point)",
  "road": "road or street name if visible"
}
Use empty string "" for any field not found. Return valid JSON only, no other text."""

    try:
        response = llm.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{data}"},
                        },
                    ],
                }
            ],
            max_tokens=300,
            temperature=0,
        )
        if not response or not response.choices:
            return {}
        content = (response.choices[0].message.content or "").strip()
        if not content:
            return {}
        content = content.replace("```json", "").replace("```", "").strip()
        result = json.loads(content)
        return {
            "slope_no": str(result.get("slope_no", "") or "").strip(),
            "area": str(result.get("area", "") or "").strip(),
            "road": str(result.get("road", "") or "").strip(),
        }
    except json.JSONDecodeError as e:
        logger.warning("Vision location_plan JSON parse error: %s", e)
        return {}
    except Exception as e:
        logger.warning("Vision location_plan API error: %s", e)
        return {}


def parse_site_photo(
    image_path: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
    filename: str = "",
) -> Dict[str, Any]:
    """
    Generate tree/slope condition description from a site photo.

    Returns:
        {"description": str, "objects_detected": ["tree", "slope", ...]} or empty dict.
    """
    if image_path:
        encoded = _encode_image(image_path)
    elif image_bytes:
        encoded = _encode_image_bytes(image_bytes, filename)
    else:
        return {}

    if not encoded:
        return {}

    data, mime = encoded
    try:
        from services.llm_service import get_llm_service

        llm = get_llm_service()
        if not llm.client:
            logger.warning("Vision API not available, LLM client not initialized")
            return {}
    except Exception as e:
        logger.warning("Cannot get LLM service for Vision: %s", e)
        return {}

    prompt = """Describe the tree/slope condition visible in this site photo. Return JSON only.
{
  "description": "Brief Chinese or English description (e.g. 榕树根部隆起、枝条悬挂路面)",
  "objects_detected": ["tree", "slope", "drainage", "crack", "vegetation", etc.]
}
Keep description under 80 characters. Return valid JSON only."""

    try:
        response = llm.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{data}"},
                        },
                    ],
                }
            ],
            max_tokens=200,
            temperature=0,
        )
        if not response or not response.choices:
            return {}
        content = (response.choices[0].message.content or "").strip()
        if not content:
            return {}
        content = content.replace("```json", "").replace("```", "").strip()
        result = json.loads(content)
        desc = str(result.get("description", "") or "").strip()
        objs = result.get("objects_detected")
        if isinstance(objs, list):
            objs = [str(x) for x in objs if x]
        else:
            objs = []
        return {"description": desc, "objects_detected": objs}
    except json.JSONDecodeError as e:
        logger.warning("Vision site_photo JSON parse error: %s", e)
        return {}
    except Exception as e:
        logger.warning("Vision site_photo API error: %s", e)
        return {}


def parse_image(
    category: ImageCategory,
    image_path: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
    filename: str = "",
) -> Dict[str, Any]:
    """
    Parse image by category. Dispatches to parse_location_plan or parse_site_photo.
    """
    if category == "location_plan":
        return parse_location_plan(
            image_path=image_path,
            image_bytes=image_bytes,
            filename=filename,
        )
    if category == "site_photo":
        return parse_site_photo(
            image_path=image_path,
            image_bytes=image_bytes,
            filename=filename,
        )
    return {}
