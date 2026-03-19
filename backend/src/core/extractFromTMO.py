"""
TMO (Tree Management Office) PDFdataextractmodule

本module负责从TMO的PDFfile中extractSRR案件data，mainprocessASD开头的PDFfile。
基于extractFromTxt.py的process逻辑，针对TMO PDFfile的特殊结构进行适配。

TMO PDFfile结构特点：
- Date of Referral 对应 A_date_received
- From field对应 B_source
- TMO Ref. 对应案件编号
- 包含check员information和联系方式
- 有具体的check项目和评论

AI增强function：
- CNN图像预process
- 多引擎OCR融合
- 智能文本cleanup和error纠正
- 自适应格式识别

作者: Project3 Team
版本: 2.0 (AI增强版)
"""
import re
import pdfplumber
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
import os
import PyPDF2
import sys
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.file_utils import extract_text_from_pdf_fast

from ai.ai_request_summarizer import generate_ai_request_summary
from utils.case_number_parser import parse_case_number
from utils.slope_location_mapper import get_location_from_slope_no
from utils.source_classifier import classify_source_smart
from utils.case_type_fallback import infer_d_type_from_content

logger = logging.getLogger(__name__)




def parse_date(date_str: str) -> Optional[datetime]:
    """
    解析日期字符串为datetimeobject（用于计算），failedreturnNone
    
    Args:
        date_str (str): 日期字符串，支持多种格式
        
    Returns:
        Optional[datetime]: 解析successreturndatetimeobject，failedreturnNone
    """
    if not date_str:
        return None
    
    # 尝试多种日期格式（包括Vision API可能返回的格式）
    date_formats = [
        "%d-%b-%Y",      # "15-Jan-2024" (Vision API常用格式)
        "%d-%B-%Y",      # "15-January-2024"
        "%d %b %Y",      # "15 Jan 2024"
        "%d %B %Y",      # "21 January 2025"
        "%Y-%m-%d",      # "2025-01-21"
        "%d/%m/%Y",      # "21/01/2025"
        "%d-%m-%Y",      # "21-01-2025"
        "%m/%d/%Y",      # "01/21/2025" (US format)
    ]
    
    for fmt in date_formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    
    return None


def format_date(dt: Optional[datetime]) -> str:
    """
    将datetimeobject格式化为dd-MMM-yyyy格式，Nonereturn空
    
    Args:
        dt (Optional[datetime]): 要格式化的datetimeobject
        
    Returns:
        str: dd-MMM-yyyy格式的日期字符串，如 "15-Jan-2024"
    """
    return dt.strftime("%d-%b-%Y") if dt else ""


def calculate_due_date(base_date: Optional[datetime], days: int) -> str:
    """
    计算基准日期加days天后的日期，returnISO字符串
    
    Args:
        base_date (Optional[datetime]): 基准日期
        days (int): 要添加的天数
        
    Returns:
        str: 计算后的日期ISO字符串
    """
    if not base_date:
        return ""
    return format_date(base_date + timedelta(days=days))


def extract_tmo_reference(content: str) -> str:
    """
    extractTMO参考编号
    
    Args:
        content (str): PDFtext content
        
    Returns:
        str: TMO参考编号
    """
    # match "TMO Ref. ASD-WC-20250089-PP" 格式
    match = re.search(r'TMO Ref\.\s*([A-Z0-9\-]+)', content)
    return match.group(1).strip() if match else ""


def extract_referral_date(content: str) -> str:
    """
    extract转介日期 (Date of Referral)
    
    Args:
        content (str): PDFtext content
        
    Returns:
        str: 转介日期
    """
    # match "Date of Referral 21 January 2025" 格式
    # 使用更精确的正则table达式，只match日期部分
    match = re.search(r'Date of Referral\s+(\d{1,2}\s+\w+\s+\d{4})', content)
    if match:
        date_str = match.group(1).strip()
        parsed_date = parse_date(date_str)
        return format_date(parsed_date)
    return ""


def extract_source_from(content: str) -> str:
    """
    extract来源information (Fromfield)
    
    Args:
        content (str): PDFtext content
        
    Returns:
        str: 来源information
    """
    # match "From Tree Management Office (TMO)" 格式
    match = re.search(r'From\s+([^\n]+)', content)
    if match:
        source = match.group(1).strip()
        # 简化来源information
        if "Tree Management Office" in source or "TMO" in source:
            return "TMO"
        return source
    return ""


def extract_inspection_officers(content: str) -> Tuple[str, str]:
    """
    extractcheck员information
    
    Args:
        content (str): PDFtext content
        
    Returns:
        Tuple[str, str]: (check员姓名, 联系方式)
    """
    # matchcheck员information - 修复正则table达式以match实际格式
    # 实际格式: "Inspection Ms. Jennifer CHEUNG, FdO(TM)9"
    officer_match = re.search(r'Inspection\s+([^\n]+?)(?=\s+Officer|\s+Attn\.|$)', content, re.DOTALL)
    contact_match = re.search(r'Contact\s+([^\n]+)', content)
    
    officers = ""
    contact = ""
    
    if officer_match:
        officers = officer_match.group(1).strip()
        # cleanup格式，extract姓名
        officers = re.sub(r'\s+', ' ', officers)
        # 只保留姓名部分，去掉职位information
        officers = re.sub(r'\s*FdO\(TM\)\d+.*', '', officers).strip()
        # 进一步cleanup，只保留姓名
        officers = re.sub(r'\s*Ms\.\s*', 'Ms. ', officers)
        officers = re.sub(r'\s*Mr\.\s*', 'Mr. ', officers)
    
    if contact_match:
        contact = contact_match.group(1).strip()
        # 提取純電話號碼：格式如 "3509 7662 Post Sr Forestry Offr/TMG" -> "3509 7662"
        phone_match = re.search(r'(\d{3,4}\s*\d{4})', contact)
        if phone_match:
            contact = re.sub(r'\s+', ' ', phone_match.group(1).strip())
    
    return officers, contact


def extract_district(content: str) -> str:
    """
    extract地区information
    
    Args:
        content (str): PDFtext content
        
    Returns:
        str: 地区information
    """
    # match "District Wan Chai" 格式
    match = re.search(r'District\s+([^\n]+)', content)
    return match.group(1).strip() if match else ""


def extract_form_reference(content: str) -> str:
    """
    extractForm 2参考编号
    
    Args:
        content (str): PDFtext content
        
    Returns:
        str: Form 2参考编号
    """
    # match "Form 2 ref. no. form2-11SWB/F199-20241028-002" 格式
    match = re.search(r'Form 2 ref\.\s+no\.\s+([^\n]+)', content)
    return match.group(1).strip() if match else ""


def extract_slope_no_from_form_ref(content: str) -> str:
    """
    从TMO内容中extract斜坡编号，支持多种模式
    
    支持的extract模式：
    1. slope.no 后面的内容
    2. Form 2 ref. no 后面的内容中extract
    3. 斜坡编号 后面的内容
    
    Args:
        content (str): PDFtext content
        
    Returns:
        str: extract并清理后的斜坡编号
    """
    logger.debug("🔍 TMO开始extract斜坡编号...")
    
    # 模式1: 11SW-B/F199(0) 和 11SW-B/F199 多个结果用 & 连接
    slope_patterns = [
        r'\b(\d+[A-Z]+-[A-Z]+/[A-Z]+\d+(?:\(\d+\))?)(?![\(\w])'# 11SW-B/F199(0) 11SW-B/F199匹配带不带括号的版本
    ]

    all_slope_numbers = []

    for pattern in slope_patterns:
        # 使用findall查找所有匹配
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            for match in matches:
                slope_no = clean_slope_number_tmo(match)
                if slope_no:
                    # 去重，避免重复添加相同的编号
                    if slope_no not in all_slope_numbers:
                        all_slope_numbers.append(slope_no)

    if len(all_slope_numbers) == 1:
        print(f"✅ 从slope.noextract斜坡编号: {all_slope_numbers[0]}")
        return all_slope_numbers[0]
    elif len(all_slope_numbers) > 1:
        result = " & ".join(all_slope_numbers)
        print(f"✅ 从slope.noextract斜坡编号: {result}")
        return result
    
    # 模式2: slope.no 后面的内容
    slope_patterns = [
        r'slope\.?\s*no\.?\s*[:\s]+([A-Z0-9\-/#\s]+)',  # slope.no: 11SW-B/F199
        r'slope\s+no\.?\s*[:\s]+([A-Z0-9\-/#\s]+)',     # slope no: 11SW-B/F199
        r'slope\s*[:\s]+([A-Z0-9\-/#\s]+)',             # slope: 11SW-B/F199
    ]
    
    for pattern in slope_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            slope_no = clean_slope_number_tmo(match.group(1))
            if slope_no:
                logger.info(f"✅ 从slope.noextract斜坡编号: {slope_no}")
                return slope_no
    
    # 模式3: Form 2 ref. no 后面的内容中extract
    form_ref = extract_form_reference(content)
    if form_ref:
        # 从form2-11SWB/F199-20241028-002中extract11SWB/F199部分
        slope_match = re.search(r'form2-([A-Z0-9/#\s]+)', form_ref, re.IGNORECASE)
        if slope_match:
            slope_part = slope_match.group(1).upper()
            slope_no = format_slope_number_tmo(slope_part)
            if slope_no:
                logger.info(f"✅ 从Form 2 ref. noextract斜坡编号: {slope_no}")
                return slope_no
    
    # 模式4: 斜坡编号 后面的内容
    chinese_patterns = [
        r'斜坡编号[:\s]+([A-Z0-9\-/#\s]+)',
        r'斜坡編號[:\s]+([A-Z0-9\-/#\s]+)',
        r'斜坡[:\s]+([A-Z0-9\-/#\s]+)',
    ]
    
    for pattern in chinese_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            slope_no = clean_slope_number_tmo(match.group(1))
            if slope_no:
                logger.info(f"✅ 从斜坡编号extract: {slope_no}")
                return slope_no
    
    logger.warning("⚠️ TMO未找到斜坡编号")
    return ""


def detect_tmo_form_type(content: str) -> str:
    """Detect TMO form type: form1 / form2 / hazardous / unknown."""
    lower = (content or "").lower()
    if any(k in lower for k in ("hazardous tree", "dangerous tree", "tree risk", "危險樹木", "危险树木")):
        return "hazardous"
    if re.search(r"\bform\s*2\b", lower) or "form2-" in lower or "form 2 ref" in lower:
        return "form2"
    if re.search(r"\bform\s*1\b", lower) or "inspection form" in lower:
        return "form1"
    return "unknown"


def collect_tmo_form_conflicts(content: str, form_type: str, slope_no: str) -> list[str]:
    conflicts: list[str] = []
    lower = (content or "").lower()
    has_form1 = bool(re.search(r"\bform\s*1\b", lower))
    has_form2 = bool(re.search(r"\bform\s*2\b", lower) or "form2-" in lower)
    if has_form1 and has_form2:
        conflicts.append("TMO document indicates both Form 1 and Form 2 markers")
    if form_type == "form2" and not extract_form_reference(content):
        conflicts.append("Form 2 detected but missing form reference number")
    if form_type in {"form1", "form2", "hazardous"} and not (slope_no or "").strip():
        conflicts.append(f"{form_type} detected but slope number is missing")
    if form_type == "hazardous" and "hazardous tree" not in lower and "危險樹木" not in lower and "危险树木" not in lower:
        conflicts.append("Hazardous form classification lacks explicit hazardous-tree phrase")
    return conflicts


def clean_slope_number_tmo(slope_text: str) -> str:
    """
    清理TMO斜坡编号，去除干扰information
    
    Args:
        slope_text (str): 原始斜坡编号文本
        
    Returns:
        str: 清理后的斜坡编号
    """
    if not slope_text:
        return ""
    
    # 去除#号、空格和其他干扰字符
    cleaned = re.sub(r'[#\s]+', '', slope_text.strip())
    
    # 只保留字母、数字、连字符和斜杠
    cleaned = re.sub(r'[^A-Z0-9\-/()]', '', cleaned.upper())
    
    # 修正OCRerror
    if cleaned.startswith('LSW') or cleaned.startswith('ISW') or cleaned.startswith('JSW'):
        cleaned = '11SW' + cleaned[3:]
    elif cleaned.startswith('lSW') or cleaned.startswith('iSW') or cleaned.startswith('jSW'):
        cleaned = '11SW' + cleaned[3:]
    elif cleaned.startswith('1SW') and len(cleaned) > 3:
        # process 1SW-D/CR995 -> 11SW-D/CR995
        cleaned = '11SW' + cleaned[3:]
    
    # format斜坡编号
    return format_slope_number_tmo(cleaned)


def format_slope_number_tmo(slope_no: str) -> str:
    """
    格式化TMO斜坡编号，转换为标准格式
    
    Args:
        slope_no (str): 原始斜坡编号
        
    Returns:
        str: 格式化后的斜坡编号
    """
    if not slope_no:
        return ""
    
    # 转换格式：11SWB/F199 -> 11SW-B/F199
    if 'SWB' in slope_no and 'SW-B' not in slope_no:
        slope_no = slope_no.replace('SWB', 'SW-B')
    elif 'SWD' in slope_no and 'SW-D' not in slope_no:
        slope_no = slope_no.replace('SWD', 'SW-D')
    elif 'SWC' in slope_no and 'SW-C' not in slope_no:
        slope_no = slope_no.replace('SWC', 'SW-C')
    elif 'SWA' in slope_no and 'SW-A' not in slope_no:
        slope_no = slope_no.replace('SWA', 'SW-A')
    
    return slope_no


def extract_comments(content: str) -> str:
    """
    extractTMO评论information
    
    Args:
        content (str): PDFtext content
        
    Returns:
        str: 评论information
    """
    # findCOMMENTS FROM TMO部分
    comments_section = re.search(r'COMMENTS FROM TMO(.*?)(?=Tree Management Office|$)', content, re.DOTALL)
    if comments_section:
        comments = comments_section.group(1).strip()
        # cleanup格式
        comments = re.sub(r'\s+', ' ', comments)
        return comments[:200] + "..." if len(comments) > 200 else comments
    return ""


def extract_follow_up_actions(content: str) -> str:
    """
    extract后续行动information
    
    Args:
        content (str): PDFtext content
        
    Returns:
        str: 后续行动information
    """
    # findFOLLOW-UP ACTIONS部分
    actions_section = re.search(r'FOLLOW-UP ACTIONS(.*?)(?=Tree Management Office|$)', content, re.DOTALL)
    if actions_section:
        actions = actions_section.group(1).strip()
        # cleanup格式
        actions = re.sub(r'\s+', ' ', actions)
        return actions[:200] + "..." if len(actions) > 200 else actions
    return ""


# 注意：get_location_from_slope_no function现在从 slope_location_mapper moduleimport







def extract_case_data_from_pdf(pdf_path: str) -> Dict[str, Any]:
    """
    从TMO PDF文件中extract所有案件data，return字典格式
    
    这是主要的TMOdataextract函数，使用通用的PDF提取函数（合并了RCC和TMO的共同逻辑）
    使用pdf2image将PDF转为图片，然后使用OpenAI Vision API提取A-Q字段
    
    Args:
        pdf_path (str): PDFfile path
        
    Returns:
        Dict[str, Any]: 包含所有A-Qfield的字典
    """
    # 使用通用的PDF提取函数（合并了RCC和TMO的共同逻辑）
    from utils.file_utils import extract_case_data_from_pdf_with_llm
    
    result = extract_case_data_from_pdf_with_llm(
        pdf_path=pdf_path,
        file_type="TMO",
        parse_date_func=parse_date,
        format_date_func=format_date,
        calculate_due_date_func=calculate_due_date,
        format_date_only_func=lambda dt: dt.strftime("%Y-%m-%d") if dt else "",
        get_location_from_slope_no_func=get_location_from_slope_no
    )
    
    print("📄 使用传统OCR方法提取PDF内容...")
    content = extract_text_from_pdf_fast(pdf_path)
    form_type = detect_tmo_form_type(content or "")
    if content and result:
        # G: 斜坡编号
        result['G_slope_no'] = extract_slope_no_from_form_ref(content)
        result['tmo_form_type'] = form_type
        result['tmo_form_conflicts'] = collect_tmo_form_conflicts(
            content,
            form_type,
            result.get('G_slope_no', ''),
        )
        if form_type == "hazardous" and "hazardous" not in str(result.get("J_subject_matter") or "").lower():
            result["J_subject_matter"] = "Hazardous Tree"
        # F: 用 OCR 提取的 Contact 電話覆寫 LLM 結果（LLM 可能誤用 TMO (DEVB)）
        _, ocr_contact = extract_inspection_officers(content)
        if ocr_contact:
            result['F_contact_no'] = ocr_contact
        return result
    elif result:
        result['tmo_form_type'] = form_type
        result['tmo_form_conflicts'] = []
        if form_type == "hazardous" and "hazardous" not in str(result.get("J_subject_matter") or "").lower():
            result["J_subject_matter"] = "Hazardous Tree"
        # 如果result不为空，content为空时，返回result
        return result
    elif not content and not result:
        logger.warning("⚠️ 无法extractPDFtext content")
        print("⚠️ 无法extractPDFtext content")
        return _get_empty_result()
    #
    #如果result为空，content不为空时，继续进行其他字段的提取
    # 初始化结果字典
    result = {}

    # A: 案件接收日期 (Date of Referral)
    result['A_date_received'] = extract_referral_date(content)
    # 需要从原始内容中extract日期string进行parse
    import re
    date_match = re.search(r'Date of Referral\s+(\d{1,2}\s+\w+\s+\d{4})', content)
    A_date = parse_date(date_match.group(1).strip()) if date_match else None
    
    # B: 来源（根据处理类型直接分类）
    result['B_source'] = classify_source_smart(
        processing_type='tmo',
        file_path=pdf_path, 
        content=content, 
        email_content=None, 
        file_type='pdf'
    )
    
    # C: 案件编号 (TMO Ref. format e.g. ASD-WC-20250089-PP)
    result['C_case_number'], _ = parse_case_number(content, source_hint="TMO")
    
    # D: 案件class型（传统规则备用）
    result['D_type'] = infer_d_type_from_content(content)
    
    # E: 来电人姓名；F: 联系电话 (check员information)
    result['E_caller_name'], result['F_contact_no'] = extract_inspection_officers(content)
    
    # G: 斜坡编号 (从Form 2 ref. no.中extract并转换格式)
    # 从Form 2 ref. no.中extract斜坡编号
    # 例如：11SWB/F199 -> 11SW-B/F199
    result['G_slope_no'] = extract_slope_no_from_form_ref(content)
    result['tmo_form_type'] = form_type
    result['tmo_form_conflicts'] = collect_tmo_form_conflicts(content, form_type, result['G_slope_no'])
    
    # H: 位置 (从Exceldataget)
    result['H_location'] = get_location_from_slope_no(result['G_slope_no'])
    
    # I: request性质摘要 (使用AI从PDF内容生成具体request摘要)
    try:
        logger.info("🤖 TMO使用AI生成请求摘要...")
        ai_summary = generate_ai_request_summary(content, None, 'pdf')
        result['I_nature_of_request'] = ai_summary
        logger.info(f"✅ TMO AI请求摘要生成success: {ai_summary}")
    except Exception as e:
        logger.warning(f"⚠️ TMO AI摘要生成failed，使用备用method: {e}")
        # 备用method：使用原有的评论extract
        result['I_nature_of_request'] = extract_comments(content)
    
    result['J_subject_matter'] = "Hazardous Tree" if form_type == "hazardous" else "Tree Trimming/ Pruning"
    
    # K: 10天规则截止日期 (A+10天)
    result['K_10day_rule_due_date'] = calculate_due_date(A_date, 10)
    
    # L: ICC临时回复截止日期 (A+10个日历日)
    result['L_icc_interim_due'] = calculate_due_date(A_date, 10)
    
    # M: ICC最终回复截止日期 (A+21个日历日)
    result['M_icc_final_due'] = calculate_due_date(A_date, 21)
    
    # N: 工程完成截止日期 (取决于D)
    days_map = {"Emergency": 1, "Urgent": 3, "General": 12}
    result['N_works_completion_due'] = calculate_due_date(A_date, days_map.get(result['D_type'], 0))
    
    # O1: 发给承包商的传真日期 (仅日期部分，通常同A)
    result['O1_fax_to_contractor'] = A_date.strftime("%Y-%m-%d") if A_date else ""
    
    # O2: 邮件发送时间 (TMO不适用)
    result['O2_email_send_time'] = ""
    
    # P: 传真页数 (PDF页数)
    try:
        with pdfplumber.open(pdf_path) as pdf:
            result['P_fax_pages'] = str(len(pdf.pages))
    except:
        result['P_fax_pages'] = ""
    
    # Q: 案件详情 (后续行动)
    result['Q_case_details'] = extract_follow_up_actions(content)
    
    return result


def _get_empty_result() -> Dict[str, Any]:
    """
    返回空的A-Q字段结果字典
    
    Returns:
        Dict[str, Any]: 包含所有A-Q字段的空字典
    """
    return {
        'A_date_received': "",
        'B_source': "",
        'C_case_number': "",
        'D_type': "General",
        'E_caller_name': "",
        'F_contact_no': "",
        'G_slope_no': "",
        'H_location': "",
        'I_nature_of_request': "",
        'J_subject_matter': "Tree Trimming/ Pruning",
        'K_10day_rule_due_date': "",
        'L_icc_interim_due': "",
        'M_icc_final_due': "",
        'N_works_completion_due': "",
        'O1_fax_to_contractor': "",
        'O2_email_send_time': "",
        'P_fax_pages': "",
        'Q_case_details': ""
    }
