#!/usr/bin/env python3
"""External public data source service (LandsD/CEDD/HKO)."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from config.settings import (
    CEDD_WFS_URL,
    EXTERNAL_API_ENABLED,
    EXTERNAL_API_TIMEOUT,
    GEOINFO_API_URL,
    HKO_API_URL,
    LANDSD_WFS_URL,
)

logger = logging.getLogger(__name__)


def _normalize_slope_no(slope_no: str) -> str:
    raw = str(slope_no or "").strip().upper()
    raw = raw.replace("／", "/")
    return re.sub(r"\s+", "", raw)


def _pick_first(props: Dict[str, Any], keys: List[str]) -> Optional[Any]:
    if not props:
        return None
    lowered = {str(k).lower(): v for k, v in props.items()}
    for key in keys:
        if key.lower() in lowered and lowered[key.lower()] not in (None, ""):
            return lowered[key.lower()]
    return None


class ExternalDataService:
    """Read slope/weather data from official public APIs."""

    def __init__(
        self,
        *,
        landsd_wfs_url: Optional[str] = None,
        cedd_wfs_url: Optional[str] = None,
        hko_api_url: Optional[str] = None,
        geoinfo_api_url: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> None:
        self.enabled = EXTERNAL_API_ENABLED
        self.landsd_wfs_url = landsd_wfs_url or LANDSD_WFS_URL
        self.cedd_wfs_url = cedd_wfs_url or CEDD_WFS_URL
        self.hko_api_url = hko_api_url or HKO_API_URL
        self.geoinfo_api_url = geoinfo_api_url or GEOINFO_API_URL
        self.timeout_seconds = int(timeout_seconds or EXTERNAL_API_TIMEOUT)
        # Note: actual layer names can vary by environment, keep configurable.
        self.landsd_type_name = "Slope_Maintenance_Responsibility_Boundaries"
        self.cedd_type_name = "Registered_Man_Made_Slopes"

    async def _wfs_get_feature(
        self,
        *,
        base_url: str,
        type_name: str,
        slope_no: str,
        count: int = 10,
    ) -> Dict[str, Any]:
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": type_name,
            "outputFormat": "GeoJSON",
            "count": str(count),
            "CQL_FILTER": f"SLOPE_NO='{_normalize_slope_no(slope_no)}'",
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds, trust_env=False) as client:
            response = await client.get(base_url, params=params)
            response.raise_for_status()
            return response.json()

    async def query_slope_responsibility(self, slope_no: str) -> Optional[Dict[str, Any]]:
        """Query LandsD slope maintenance responsibility by slope number."""
        if not self.enabled or not slope_no:
            return None
        try:
            data = await self._wfs_get_feature(
                base_url=self.landsd_wfs_url,
                type_name=self.landsd_type_name,
                slope_no=slope_no,
            )
            features = data.get("features") or []
            if not features:
                return None
            props = (features[0] or {}).get("properties") or {}
            found_slope_no = _pick_first(props, ["slope_no", "slope number", "slopeno"])
            subdivision = _pick_first(props, ["sub_division", "subdivision", "sub-division no"])
            maint = _pick_first(
                props,
                [
                    "maintenance_responsibility",
                    "maintenance_responsible",
                    "maint_responsibility",
                    "responsible_party",
                ],
            )
            return {
                "slope_no": str(found_slope_no or _normalize_slope_no(slope_no)),
                "subdivision": str(subdivision or ""),
                "maintenance_responsible": str(maint or ""),
                "source": "api",
                "raw": props,
            }
        except Exception as exc:
            logger.warning("LandsD WFS query failed: %s", exc)
            return None

    async def query_slope_engineering(self, slope_no: str) -> Optional[Dict[str, Any]]:
        """Query CEDD slope engineering metadata by slope number."""
        if not self.enabled or not slope_no:
            return None
        try:
            data = await self._wfs_get_feature(
                base_url=self.cedd_wfs_url,
                type_name=self.cedd_type_name,
                slope_no=slope_no,
            )
            features = data.get("features") or []
            if not features:
                return None
            props = (features[0] or {}).get("properties") or {}
            return {
                "slope_no": str(_pick_first(props, ["slope_no", "slopeno"]) or _normalize_slope_no(slope_no)),
                "slope_type": _pick_first(props, ["slope_type", "type", "slopeclass"]) or "",
                "district": _pick_first(props, ["district", "dist"]) or "",
                "location": _pick_first(props, ["location", "loc"]) or "",
                "source": "api",
                "raw": props,
            }
        except Exception as exc:
            logger.warning("CEDD WFS query failed: %s", exc)
            return None

    async def query_weather_warnings(self) -> List[Dict[str, Any]]:
        """Query HKO weather warning summary."""
        if not self.enabled:
            return []
        try:
            params = {"dataType": "warnsum", "lang": "en"}
            async with httpx.AsyncClient(timeout=self.timeout_seconds, trust_env=False) as client:
                response = await client.get(self.hko_api_url, params=params)
                response.raise_for_status()
                payload = response.json()
            if not isinstance(payload, dict):
                return []
            warnings: List[Dict[str, Any]] = []
            for code, item in payload.items():
                if not isinstance(item, dict):
                    continue
                warnings.append(
                    {
                        "code": code,
                        "name": item.get("name_en") or item.get("name") or "",
                        "action_code": item.get("actionCode") or "",
                        "issue_time": item.get("issueTime") or "",
                        "expire_time": item.get("expireTime") or "",
                    }
                )
            return warnings
        except Exception as exc:
            logger.warning("HKO warnsum query failed: %s", exc)
            return []

    async def query_geoinfo(self, location: str) -> Optional[Dict[str, Any]]:
        """Query GeoInfo Map for address standardization. Returns None on failure."""
        if not self.enabled or not (location or "").strip():
            return None
        try:
            params = {"q": (location or "").strip()[:200], "limit": "5"}
            async with httpx.AsyncClient(timeout=self.timeout_seconds, trust_env=False) as client:
                response = await client.get(self.geoinfo_api_url, params=params)
                response.raise_for_status()
                data = response.json()
            if not isinstance(data, dict):
                return None
            results = data.get("results") or data.get("features") or []
            if not results:
                return {"location": location, "standardized": None, "source": "geoinfo"}
            first = results[0] if isinstance(results[0], dict) else {}
            addr = first.get("address") or first.get("name") or first.get("label") or location
            return {
                "location": location,
                "standardized": addr,
                "source": "geoinfo",
                "raw": first,
            }
        except Exception as exc:
            logger.warning("GeoInfo query failed: %s", exc)
            return None

    async def query_all(self, slope_no: Optional[str] = None) -> Dict[str, Any]:
        """Run external lookups in parallel."""
        if not self.enabled:
            return {"enabled": False, "smris": None, "cedd": None, "weather": []}

        smris_task = self.query_slope_responsibility(slope_no or "")
        cedd_task = self.query_slope_engineering(slope_no or "")
        weather_task = self.query_weather_warnings()
        smris, cedd, weather = await asyncio.gather(smris_task, cedd_task, weather_task, return_exceptions=True)

        return {
            "enabled": True,
            "smris": None if isinstance(smris, Exception) else smris,
            "cedd": None if isinstance(cedd, Exception) else cedd,
            "weather": [] if isinstance(weather, Exception) else weather,
        }
