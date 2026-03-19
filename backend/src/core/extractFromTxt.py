"""
dataextractmodule - 从TXTfile中extract和parseSRR案件data

本module负责从SRR案件的TXTfile中extract结构化data，包括：
- 案件基本information（日期、来源、class型等）
- 联系人information（姓名、电话）
- 斜坡相关information（编号、位置）
- 时间节点（截止日期、回复时间等）
- 案件详情和附件information

mainfunction：
1. parse各种日期格式
2. extract案件来源和class型
3. get联系人和斜坡information
4. calculate各种截止日期
5. 生成案件摘要和详情
6. AI增强文本process和OCR能力

作者: Project3 Team
版本: 2.0 (AI增强版)
"""
import re
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Tuple
import os
import sys
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

from utils.email_info_extractor import get_email_contact_info
from utils.case_number_parser import parse_case_number
from ai.ai_request_summarizer import generate_ai_request_summary
from utils.file_utils import detect_file_encoding, read_file_with_encoding
from utils.slope_location_mapper import get_location_from_slope_no
from utils.source_classifier import classify_source_smart
from utils.case_type_fallback import infer_d_type_from_content


def parse_date(date_str: str) -> Optional[datetime]:
    """
    解析日期字符串为datetimeobject（用于计算），failedreturnNone
    
    支持多种日期格式，包括：
    - "YYYY-MM-DD HH:MM:SS"
    - "dd-MMM-yyyy" (e.g., "15-Jan-2024")
    - "YYYY-MM-DD"
    - 其他常见格式
    
    Args:
        date_str (str): 日期字符串
        
    Returns:
        Optional[datetime]: 解析successreturndatetimeobject，failedreturnNone
        
    Example:
        >>> parse_date("2024-01-15 10:30:00")
        datetime(2024, 1, 15, 10, 30, 0)
        >>> parse_date("15-Jan-2024")
        datetime(2024, 1, 15, 0, 0, 0)
        >>> parse_date("")
        None
    """
    if not date_str:
        return None
    
    # 尝试多种日期格式
    date_formats = [
        "%Y-%m-%d %H:%M:%S",  # "2024-01-15 10:30:00"
        "%d-%b-%Y",           # "15-Jan-2024"
        "%d-%B-%Y",           # "15-January-2024"
        "%d %b %Y",           # "15 Jan 2024"
        "%d %B %Y",           # "21 January 2025"
        "%Y-%m-%d",           # "2025-01-21"
        "%Y/%m/%d",           # "2025/03/18"
        "%d/%m/%Y",           # "21/01/2025"
        "%d-%m-%Y",           # "21-01-2025"
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
        
    Example:
        >>> format_date(datetime(2024, 1, 15, 10, 30, 0))
        "15-Jan-2024"
        >>> format_date(None)
        ""
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
        
    Example:
        >>> base = datetime(2024, 1, 15, 10, 30, 0)
        >>> calculate_due_date(base, 10)
        "2024-01-25T10:30:00"
    """
    if not base_date:
        return ""
    return format_date(base_date + timedelta(days=days))


def extract_1823_case_no(content: str) -> str:
    """
    extract1823案件编号
    
    从TXT内容中搜索"1823 case:"后面的内容作为案件编号
    
    Args:
        content (str): TXT文件内容
        
    Returns:
        str: extract的案件编号，未找到return空字符串
        
    Example:
        >>> content = "1823 CASE: 3-8641924612"
        >>> extract_1823_case_no(content)
        "3-8641924612"
    """
    # search"1823 case:"后面的内容（不区分大小写）
    match = re.search(r'1823\s+case:\s*([\w\-:]+)', content, re.IGNORECASE)
    if match:
        case_number = match.group(1).strip()
        logger.info(f"✅ extract到1823案件编号: {case_number}")
        return case_number
    
    logger.warning("⚠️ 未找到1823案件编号")
    return ""




def get_caller_info_by_source(content: str, source: str) -> Tuple[str, str]:
    """
    根据来源Bextract联系人姓名(E)和电话(F)
    
    从CONTACT INFORMATION部分extract联系人的姓名和电话号码，
    支持RCC、ICC、1823等来源格式
    
    Args:
        content (str): TXT文件内容
        source (str): 案件来源（RCC/ICC/1823等）
        
    Returns:
        Tuple[str, str]: (姓名, 电话号码)
        
    Example:
        >>> content = "Last Name : 张\nFirst Name : 三\nDaytime No. : 12345678"
        >>> get_caller_info_by_source(content, "1823")
        ("张 三", "12345678")
    """
    # 不同来源的extract规则
    if source in ["RCC", "ICC", "1823"]:
        # 从VI. CONTACT INFORMATIONextract
        last_name = re.search(r'Last Name :\s*(.*?)\n', content)
        first_name = re.search(r'First Name :\s*(.*?)\n', content)
        phone = re.search(r'Daytime No. :\s*(.*?)\n', content) or re.search(r'Mobile :\s*(.*?)\n', content)
        
        full_name = f"{last_name.group(1).strip() if last_name else ''} {first_name.group(1).strip() if first_name else ''}".strip()
        contact_no = phone.group(1).strip() if phone else ""
        return (full_name, contact_no)
    # 其他来源的规则可扩展
    return ("", "")


def parse_specific_qa_block(content: str) -> dict:
    """
    Extract Q&A pairs from ICC "V. SPECIFIC Q&A" / "Specific Q&A" block.

    Returns dict mapping question keys to answer values (normalized to lowercase).
    """
    if not content:
        return {}
    # Locate block between "Specific Q&A" / "V. SPECIFIC Q&A" and next section
    start_markers = [
        r"V\.\s*SPECIFIC\s+Q\s*&\s*A\s*:?\s*\n",
        r"SPECIFIC\s+Q\s*&\s*A\s*:?\s*\n",
        r"Specific Q&A\s*:?\s*\n",
        r"V\.\s*SPECIFIC\s+Q&A\s*:?\s*\n",
    ]
    end_markers = [
        r"\n\s*VI\.\s+CONTACT\s+INFORMATION",
        r"\n\s*Assignment\s+History",
        r"\n\s*II\.\s+ASSIGNMENT",
        r"\n\s*VI\.\s+CONTACT",
    ]
    block = ""
    for start in start_markers:
        m = re.search(start, content, re.IGNORECASE)
        if m:
            rest = content[m.end() :]
            for end in end_markers:
                em = re.search(end, rest, re.IGNORECASE)
                if em:
                    block = rest[: em.start()].strip()
                    break
            if not block:
                block = rest[:2000].strip()
            break
    if not block:
        return {}
    # Extract Q&A pairs: "Q1: ..." / "A1: ..." or "Question: ..." / "Answer: ..."
    qa = {}
    for q_match in re.finditer(r"(?:Q\d*|Question)\s*[：:]\s*(.+?)(?=\n|$)", block, re.IGNORECASE | re.DOTALL):
        q_text = q_match.group(1).strip()[:200]
        q_key = re.sub(r"\s+", " ", q_text).lower()
        # Find next A: answer
        after = block[q_match.end() : q_match.end() + 500]
        a_match = re.search(r"(?:A\d*|Answer)\s*[：:]\s*(.+?)(?=\n|$)", after, re.IGNORECASE | re.DOTALL)
        if a_match:
            a_text = a_match.group(1).strip()[:200].lower()
            qa[q_key] = a_text
    return qa


def infer_d_type_from_specific_qa(qa: dict) -> str:
    """
    Map Specific Q&A answers to D_type: Emergency/Urgent/General
    """
    if not qa:
        return "General"
    text = " ".join(qa.values()).lower()
    for q, a in qa.items():
        if any(kw in q for kw in ("immediate danger", "即时危险", "即時危險")):
            if any(kw in a for kw in ("yes", "是", "有")):
                return "Emergency"
        if any(kw in q for kw in ("urgent", "加急", "紧急")):
            if any(kw in a for kw in ("yes", "是", "有")):
                return "Urgent"
    return "General"


def classify_case_type_traditional(content: str) -> str:
    """传统的案件class型classifymethod（备用）- 优先 Specific Q&A，否则 Description 段落"""
    qa = parse_specific_qa_block(content)
    if qa:
        d = infer_d_type_from_specific_qa(qa)
        if d != "General":
            return d
    desc = re.search(r'Description :\s*(.*?)\n', content, re.DOTALL)
    if not desc:
        return "General"
    return infer_d_type_from_content(desc.group(1))


def generate_nature_summary(content: str) -> str:
    """
    生成请求性质摘要I - 使用NLP增强技术
    
    Args:
        content (str): TXT文件内容（已AI增强process）
        
    Returns:
        str: 请求性质摘要
    """
    # 直接使用NLP增强技术进行智能summarize
    try:
        from ai.nlp_enhanced_processor import get_nlp_enhanced_nature_of_request
        
        # check是否有对应的邮件file
        email_content = None
        # 尝试推断邮件file path
        # 这里可以根据当前process的file名来推断
        # 例如: 3-3YXXSJV.txt -> emailcontent_3-3YXXSJV.txt
        
        # 使用NLP技术summarize诉求内容
        nlp_summary = get_nlp_enhanced_nature_of_request(content, email_content)
        if nlp_summary:
            logger.info(f"✅ NLP增强摘要success: {nlp_summary}")
            return nlp_summary
            
    except ImportError:
        logger.warning("⚠️ NLP增强process器不可用，使用传统method")
    except Exception as e:
        logger.warning(f"⚠️ NLPprocessfailed: {e}，使用传统method")
    
    # 传统method作为备选
    if len(content) > 100:
        return content[:100] + "..."
    else:
        return content


def generate_nature_summary_from_original(original_content: str) -> str:
    """
    从原始文件内容生成简洁的NLPsummarize
    
    Args:
        original_content (str): 原始TXT文件内容
        
    Returns:
        str: 简洁的请求性质摘要
    """
    try:
        from ai.nlp_enhanced_processor import get_nlp_enhanced_nature_of_request
        
        # check是否有对应的邮件file
        email_content = None
        
        # 使用原始内容进行NLPsummarize，生成简洁result
        nlp_summary = get_nlp_enhanced_nature_of_request(original_content, email_content)
        if nlp_summary:
            logger.info(f"✅ 原始内容NLP摘要success: {nlp_summary}")
            return nlp_summary
            
    except ImportError:
        logger.warning("⚠️ NLP增强process器不可用，使用传统method")
    except Exception as e:
        logger.warning(f"⚠️ NLPprocessfailed: {e}，使用传统method")
    
    # 传统method作为备选
    if len(original_content) > 100:
        return original_content[:100] + "..."
    else:
        return original_content


def get_slope_no(content: str) -> str:
    """extract斜坡编号G（从补充information或描述中）"""
    # match"斜坡编号为XXX"或"[请提供斜坡牌...](XXX)"
    slope_match = re.search(r'斜坡編號為([\w\-/]+)', content) or re.search(r'\((11sw-c/nd31)\)', content, re.IGNORECASE)
    return slope_match.group(1).strip().upper() if slope_match else ""


# 注意：get_location_from_slope_no function现在从 slope_location_mapper moduleimport


def get_last_interim_reply_time(content: str) -> str:
    """extract最后一个实质process的Interim Reply时间"""
    # find所有DUE DATE部分
    due_date_sections = re.findall(r'DUE DATE:.*?(?=\d+st DUE DATE:|$)', content, re.DOTALL)
    
    if not due_date_sections:
        return ""
    
    # 遍历所有DUE DATE部分，找到最后一个有Interim Reply时间的
    last_interim_reply = ""
    for section in due_date_sections:
        interim_match = re.search(r'Interim Reply\s*:\s*([^\n]+)', section)
        if interim_match and interim_match.group(1).strip():
            last_interim_reply = interim_match.group(1).strip()
    
    return last_interim_reply


def get_last_final_reply_time(content: str) -> str:
    """extract最后一个实质process的Final Reply时间"""
    # find所有DUE DATE部分
    due_date_sections = re.findall(r'DUE DATE:.*?(?=\d+st DUE DATE:|$)', content, re.DOTALL)
    
    if not due_date_sections:
        return ""
    
    # 遍历所有DUE DATE部分，找到最后一个有Final Reply时间的
    last_final_reply = ""
    for section in due_date_sections:
        final_match = re.search(r'Final Reply\s*:\s*([^\n]+)', section)
        if final_match and final_match.group(1).strip():
            last_final_reply = final_match.group(1).strip()
    
    return last_final_reply


def format_date_only(dt: Optional[datetime]) -> str:
    """将datetimeobject格式化为仅日期字符串（YYYY-MM-DD），Nonereturn空"""
    return dt.strftime("%Y-%m-%d") if dt else ""


def format_time_only(dt: Optional[datetime]) -> str:
    """将datetimeobject格式化为仅时间字符串（HH:MM:SS），Nonereturn空"""
    return dt.strftime("%H:%M:%S") if dt else ""


# deleteAI增强processfunction，直接使用原始file内容


def extract_case_data_from_txt(
    txt_path: str,
    correction_hints: list = None,
    few_shot_cases: list = None,
) -> dict:
    """
    从TXT文件中extract所有案件data，return字典格式
    
    这是主要的dataextract函数，使用OpenAI大模型提取A-Q字段
    
    Args:
        txt_path (str): TXTfile path
        
    Returns:
        dict: 包含所有A-Qfield的字典
    """
    result = {}
    
    # 使用智能encoding检测read原始file内容
    try:
        content = read_file_with_encoding(txt_path)
    except Exception as e:
        logger.error(f"⚠️ 无法读取TXT文件: {e}")
        return _get_empty_result()
    
    # check是否有对应的邮件file
    email_content = None
    try:
        # 根据TXTfile名推断邮件file path
        # 例如: exampleInput/txt/3-3YXXSJV.txt -> exampleInput/txt/emailcontent_3-3YXXSJV.txt
        dir_path = os.path.dirname(txt_path)
        base_name = os.path.splitext(os.path.basename(txt_path))[0]
        email_path = os.path.join(dir_path, f"emailcontent_{base_name}.txt")
        
        if os.path.exists(email_path):
            logger.info(f"📧 发现邮件文件: {email_path}")
            try:
                email_content = read_file_with_encoding(email_path)
            except Exception as e:
                logger.warning(f"⚠️ 邮件文件读取failed: {e}")
                email_content = None
        else:
            logger.debug(f"ℹ️ 未找到邮件文件: {email_path}")
            
    except Exception as e:
        logger.warning(f"⚠️ 邮件文件processfailed: {e}")
    
    # 使用OpenAI大模型提取A-Q字段
    try:
        from services.llm_service import get_llm_service
        
        logger.info("🤖 使用OpenAI大模型提取TXT文档A-Q字段...")
        llm_service = get_llm_service()
        extracted_data = llm_service.extract_fields_from_text(
            content,
            email_content,
            correction_hints=correction_hints or [],
            few_shot_examples=few_shot_cases or [],
        )
        
        if extracted_data:
            result = extracted_data
            logger.info(f"✅ 成功从TXT文档提取 {len(result)} 个字段")
            
            # 计算日期相关字段（如果A_date_received存在）
            if result.get('A_date_received'):
                A_date = parse_date(result['A_date_received'])
                
                if A_date:
                    # 重新格式化日期
                    result['A_date_received'] = format_date(A_date)
                    # 计算截止日期
                    result['K_10day_rule_due_date'] = calculate_due_date(A_date, 10)
                    
                    # N: 工程完成截止日期 (取决于D)
                    days_map = {"Emergency": 1, "Urgent": 3, "General": 12}
                    result['N_works_completion_due'] = calculate_due_date(A_date, days_map.get(result.get('D_type', 'General'), 12))
                    
                    # O1: 发给承包商的传真日期
                    result['O1_fax_to_contractor'] = format_date_only(A_date)
            
            # H: 位置 (只要slope number存在，优先地址本地检索)
            if result.get('G_slope_no'):
                if get_location_from_slope_no(result['G_slope_no']):
                    result['H_location'] = get_location_from_slope_no(result['G_slope_no'])
            
            return result
        else:
            logger.warning("⚠️ OpenAI大模型未能提取字段，使用备用方法...")
    except Exception as e:
        logger.warning(f"⚠️ OpenAI大模型提取失败: {e}")
        import traceback
        logger.debug(traceback.format_exc())
    
    # 备用方法：使用传统提取逻辑
    logger.info("📄 使用传统方法提取TXT内容...")
    return extract_case_data_with_email(content, email_content, content, txt_path)


def extract_case_data_with_email(content: str, email_content: str = None, original_content: str = None, txt_path: str = None) -> dict:
    """
    从TXT内容中extract所有案件data，支持邮件内容用于NLPprocess和联系informationextract
    
    Args:
        content (str): TXT文件内容
        email_content (str): 邮件内容（可选）
        original_content (str): 原始内容（用于NLPprocess）
        
    Returns:
        dict: 包含所有A-Qfield的字典
    """
    # 调用原有的extract逻辑，传递file path
    result = extract_case_data(content, original_content, email_content, txt_path)
    
    # 如果有邮件内容，进行增强process
    if email_content:
        # 1. 使用AI生成具体的request摘要（优先使用邮件内容）
        try:
            logger.info("🤖 使用AI从邮件内容生成请求摘要...")
            ai_summary = generate_ai_request_summary(content, email_content, 'txt')
            if ai_summary and ai_summary != "无法extract具体请求内容":
                result['I_nature_of_request'] = ai_summary
                logger.info(f"✅ AI邮件请求摘要生成success: {ai_summary}")
            
        except Exception as e:
            logger.warning(f"⚠️ AI邮件摘要生成failed: {e}，使用原有摘要")
        
        # 2. 从邮件内容extract联系information（E_caller_name和F_contact_no）
        try:
            email_contact_info = get_email_contact_info(email_content, content)
            
            # 如果邮件中有联系information，优先使用邮件information
            if email_contact_info.get('E_caller_name'):
                result['E_caller_name'] = email_contact_info['E_caller_name']
                logger.info(f"✅ 从邮件extract联系人姓名: {email_contact_info['E_caller_name']}")
            
            if email_contact_info.get('F_contact_no'):
                result['F_contact_no'] = email_contact_info['F_contact_no']
                logger.info(f"✅ 从邮件extract联系电话: {email_contact_info['F_contact_no']}")
                
        except Exception as e:
            logger.warning(f"⚠️ 邮件联系informationextractfailed: {e}，使用原有information")
    
    return result


# deleteAI增强process相关function，直接使用原始file内容


def extract_case_data(content: str, original_content: str = None, email_content: str = None, file_path: str = None) -> dict:
    """
    从TXT内容中extract所有案件data，return字典格式
    
    这是主要的dataextract函数，整合了所有extract逻辑，按照A-Qfield规则extract：
    - A: 案件接收日期
    - B: 来源
    - C: 1823案件号（仅RCC/ICC）
    - D: 案件class型
    - E: 来电人姓名
    - F: 联系电话
    - G: 斜坡编号
    - H: 位置（从Exceldata获取）
    - I: 请求性质摘要
    - J: 事项主题
    - K: 10天规则截止日期
    - L: ICC临时回复截止日期
    - M: ICC最终回复截止日期
    - N: 工程完成截止日期
    - O1: 发给承包商的传真日期
    - O2: 邮件发送时间
    - P: 传真页数
    - Q: 案件详情
    
    Args:
        content (str): TXT文件内容
        
    Returns:
        dict: 包含所有A-Qfield的字典
        
    Example:
        >>> content = "Case Creation Date : 2024-01-15 10:30:00\\nChannel : Web..."
        >>> data = extract_case_data(content)
        >>> data['A_date_received']
        "2024-01-15T10:30:00"
    """
    result = {}
    
    # A: 案件接收日期（AIMS生成，对应Case Creation Date）
    creation_date_match = re.search(r'Case Creation Date :\s*(.*?)\n', content)
    A_date = parse_date(creation_date_match.group(1)) if creation_date_match else None
    result['A_date_received'] = format_date(A_date)
    
    # B: 来源（根据处理类型直接分类）
    result['B_source'] = classify_source_smart(
        processing_type='txt',
        file_path=file_path, 
        content=content, 
        email_content=email_content, 
        file_type='txt'
    )
    
    # C: 案件编号 (unified parser, ICC format)
    result['C_case_number'], _ = parse_case_number(content, source_hint="ICC", file_path=file_path)
    
    # E: 来电人姓名；F: 联系电话（取决于B）
    result['E_caller_name'], result['F_contact_no'] = get_caller_info_by_source(content, result['B_source'])
    
    # G: 斜坡编号
    result['G_slope_no'] = get_slope_no(content)
    
    # H: 位置（从slope data.xlsxget）
    result['H_location'] = get_location_from_slope_no(result['G_slope_no'])
    
    # I: request性质摘要 - 使用AI从邮件或内容中生成具体request摘要
    try:
        logger.info("🤖 TXT使用AI生成请求摘要...")
        source_content = original_content if original_content else content
        ai_summary = generate_ai_request_summary(source_content, email_content, 'txt')
        result['I_nature_of_request'] = ai_summary
        logger.info(f"✅ TXT AI请求摘要生成success: {ai_summary}")
    except Exception as e:
        logger.warning(f"⚠️ TXT AI摘要生成failed，使用备用method: {e}")
        # 备用method：使用原有的NLPprocess
        if original_content:
            result['I_nature_of_request'] = generate_nature_summary_from_original(original_content)
        else:
            result['I_nature_of_request'] = generate_nature_summary(content)
    
    # J: 事项主题（根据历史record和规则，示例逻辑）
    subject_match = re.search(r'Subject Matter :\s*(.*?)\n', content)
    extracted_subject = subject_match.group(1).strip() if subject_match else ""
    
    result['J_subject_matter'] = extracted_subject or "Others"
    
    # D: 案件class型（传统规则备用）
    result['D_type'] = classify_case_type_traditional(content)
    
    # K: 10天规则截止日期（A+10天）
    result['K_10day_rule_due_date'] = calculate_due_date(A_date, 10)
    
    # L: ICC临时回复截止日期（A+10个日历日）
    result['L_icc_interim_due'] = calculate_due_date(A_date, 10)
    
    # M: ICC最终回复截止日期（A+21个日历日）
    result['M_icc_final_due'] = calculate_due_date(A_date, 21)
    
    # N: 工程完成截止日期（取决于D）
    days_map = {"Emergency": 1, "Urgent": 3, "General": 12}
    result['N_works_completion_due'] = calculate_due_date(A_date, days_map.get(result['D_type'], 0))
    
    # O1: 发给承包商的传真日期（仅日期部分，通常同A）
    result['O1_fax_to_contractor'] = format_date_only(A_date)
    
    # O2: 邮件发送时间（从书面联系详情extract时间部分，如果没有Transaction Time则使用Case Creation Date的时间）
    email_time_match = re.search(r'Transaction Time:\s*(.*?)\n', content)
    if email_time_match:
        email_dt = parse_date(email_time_match.group(1))
        result['O2_email_send_time'] = format_time_only(email_dt)
    else:
        # 如果没有Transaction Time，使用Case Creation Date的时间部分
        result['O2_email_send_time'] = format_time_only(A_date)
    
    # P: 传真页数（从附件informationextract）
    file_upload_match = re.search(r'File upload:\s*(\d+)\s*file', content)
    result['P_fax_pages'] = f"1 + {file_upload_match.group(1)}" if file_upload_match else ""
    
    # Q: 案件详情（带建议截止日期）
    # 整合描述和建议截止日期
    # 重用I列的result，避免duplicateNLPprocess
    detail_text = result['I_nature_of_request']
    if result['N_works_completion_due']:
        detail_text += f"\n建议工程完成截止日期: {result['N_works_completion_due']}"
    result['Q_case_details'] = detail_text
    
    return result


def _get_empty_result() -> dict:
    """
    返回空的A-Q字段结果字典
    
    Returns:
        dict: 包含所有A-Q字段的空字典
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
        'J_subject_matter': "Others",
        'K_10day_rule_due_date': "",
        'L_icc_interim_due': "",
        'M_icc_final_due': "",
        'N_works_completion_due': "",
        'O1_fax_to_contractor': "",
        'O2_email_send_time': "",
        'P_fax_pages': "",
        'Q_case_details': ""
    }
