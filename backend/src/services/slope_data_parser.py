#!/usr/bin/env python3
"""Parsers for slope mapping structured files."""

from __future__ import annotations

import os
import re
from typing import Dict, List

import pandas as pd


class SlopeDataParser:
    """Parse slope mapping files (xlsx/xls/csv/json)."""

    _SLOPE_COL_CANDIDATES = (
        "slope no",
        "slope_no",
        "slope",
        "slope id",
        "slope_id",
        "slopeno",
        "斜坡编号",
        "斜坡編號",
    )
    _LOCATION_COL_CANDIDATES = (
        "location",
        "venue",
        "address",
        "location en",
        "english",
        "位置",
        "地点",
        "地點",
    )
    _LOCATION_CN_COL_CANDIDATES = (
        "location cn",
        "chinese",
        "location chinese",
        "位置(中文)",
        "位置中文",
    )

    def normalize_slope_no(self, value: str) -> str:
        if not value:
            return ""
        slope = re.sub(r"\s+", "", str(value).upper())
        slope = slope.replace("／", "/")
        slope = re.sub(r"[^A-Z0-9\-/()]", "", slope)
        return slope

    def _match_column(self, columns: List[str], candidates: tuple[str, ...]) -> str:
        lowered = {c.lower().strip(): c for c in columns}
        for cand in candidates:
            for lower_col, original in lowered.items():
                if cand in lower_col:
                    return original
        return ""

    def parse_file(self, file_path: str) -> Dict[str, object]:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in (".xlsx", ".xls"):
            frames = pd.read_excel(file_path, sheet_name=None)
            df = pd.concat(frames.values(), ignore_index=True) if frames else pd.DataFrame()
        elif ext == ".csv":
            df = pd.read_csv(file_path)
        elif ext == ".json":
            df = pd.read_json(file_path)
        else:
            raise ValueError(f"Unsupported slope mapping file: {file_path}")

        if df.empty:
            return {"mapping_en": {}, "mapping_cn": {}, "records": 0}

        df = df.fillna("")
        columns = [str(c) for c in df.columns]
        slope_col = self._match_column(columns, self._SLOPE_COL_CANDIDATES)
        location_col = self._match_column(columns, self._LOCATION_COL_CANDIDATES)
        location_cn_col = self._match_column(columns, self._LOCATION_CN_COL_CANDIDATES)

        # Fallback to first two columns if source headers are unknown.
        if not slope_col and len(columns) >= 1:
            slope_col = columns[0]
        if not location_col and len(columns) >= 2:
            location_col = columns[1]

        mapping_en: Dict[str, str] = {}
        mapping_cn: Dict[str, str] = {}

        for _, row in df.iterrows():
            slope_no = self.normalize_slope_no(str(row.get(slope_col, "")))
            if not slope_no:
                continue
            loc_en = str(row.get(location_col, "")).strip() if location_col else ""
            loc_cn = str(row.get(location_cn_col, "")).strip() if location_cn_col else ""
            if loc_en:
                mapping_en[slope_no] = loc_en
            if loc_cn:
                mapping_cn[slope_no] = loc_cn

        return {
            "mapping_en": mapping_en,
            "mapping_cn": mapping_cn,
            "records": len(mapping_en),
            "columns": columns,
        }
