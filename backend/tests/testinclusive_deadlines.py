import os
import sys

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC_DIR = os.path.join(_BACKEND_DIR, "src")
for _p in (_BACKEND_DIR, _SRC_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.extractFromRCC import calculate_k_due_date as calculate_rcc_k_due_date
from core.extractFromRCC import parse_date as parse_rcc_date
from core.extractFromTMO import calculate_k_due_date as calculate_tmo_k_due_date
from core.extractFromTMO import parse_date as parse_tmo_date
from core.extractFromTxt import (
    calculate_k_due_date as calculate_txt_k_due_date,
    extract_case_data,
    parse_date as parse_txt_date,
)
from utils.deadline_rules import add_inclusive_calendar_days, inclusive_calendar_day_offset


def test_inclusive_calendar_day_offset_counts_start_day() -> None:
    assert inclusive_calendar_day_offset(10) == 9
    assert inclusive_calendar_day_offset(1) == 0


def test_add_inclusive_calendar_days_returns_expected_date() -> None:
    dt = parse_txt_date("2026-04-15 16:36:16")
    shifted = add_inclusive_calendar_days(dt, 10)

    assert shifted is not None
    assert shifted.strftime("%d-%b-%Y") == "24-Apr-2026"


def test_k_due_date_is_inclusive_for_txt_tmo_and_rcc() -> None:
    assert calculate_txt_k_due_date(parse_txt_date("2026-04-15 16:36:16")) == "24-Apr-2026"
    assert calculate_tmo_k_due_date(parse_tmo_date("15-Apr-2026")) == "24-Apr-2026"
    assert calculate_rcc_k_due_date(parse_rcc_date("15-Apr-2026")) == "24-Apr-2026"


def test_extract_case_data_sets_inclusive_k_and_icc_interim_l() -> None:
    content = """1823 CASE: 3-9400481748
Case Creation Date : 2026-04-15 16:36:16

I. DUE DATE:
Interim Reply : 2026-04-24 16:38:56
Final Reply : 2026-05-06 16:38:56

IV. CASE DETAILS:
Subject Matter : 樹木 - ASD
Description :
測試

VI. CONTACT INFORMATION:
Last Name :  謝
Mobile : 96560321

VII. WRITTEN CONTACT INBOUND DETAILS:
Transaction Time:    2026-04-14 14:23:10
"""

    result = extract_case_data(content, content)

    assert result["K_10day_rule_due_date"] == "24-Apr-2026"
    assert result["L_icc_interim_due"] == "24-Apr-2026"
