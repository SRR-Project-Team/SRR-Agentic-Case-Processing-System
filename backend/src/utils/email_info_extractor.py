#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮件informationextractmodule
从邮件内容中extractE_caller_name（落款）和F_contact_no（电话号码）
"""

import re
from typing import Dict, Optional, Tuple


def extract_email_contact_info(email_content: str) -> Dict[str, str]:
    """
    从邮件内容中extract联系人information
    
    Args:
        email_content: 邮件内容文本
        
    Returns:
        dict: 包含E_caller_name和F_contact_no的dictionary
    """
    result = {
        'E_caller_name': '',
        'F_contact_no': ''
    }
    
    # extract落款（signature）
    caller_name = extract_caller_name(email_content)
    if caller_name:
        result['E_caller_name'] = caller_name
    
    # extract电话号码
    contact_no = extract_contact_number(email_content)
    if contact_no:
        result['F_contact_no'] = contact_no
    
    return result


def extract_caller_name(email_content: str) -> str:
    """
    extract邮件落款/signature中的姓名
    
    优先级：
    1. 1823 Duty Manager（标准格式）
    2. 其他可能的signature格式
    3. 发件人information
    """
    
    # 1. 标准1823格式
    duty_manager_pattern = r'1823\s+Duty\s+Manager'
    if re.search(duty_manager_pattern, email_content, re.IGNORECASE):
        return "1823 Duty Manager"
    
    # 2. find其他可能的signature格式
    # 通常在邮件末尾，在联系information之前
    signature_patterns = [
        # 常见signature格式
        r'(?:Best\s+regards?|Regards?|Sincerely|Thank\s+you)[,\s]*\n\s*([A-Za-z\s]+)\s*\n',
        r'(?:谢谢|此致|敬礼)[，\s]*\n\s*([A-Za-z\u4e00-\u9fff\s]+)\s*\n',
        
        # 职位+姓名格式
        r'([A-Za-z\s]+(?:Manager|Officer|Coordinator|Assistant))\s*\n',
        r'([A-Za-z\u4e00-\u9fff\s]+(?:经理|主任|助理|专员))\s*\n',
        
        # 部门+职位格式
        r'([A-Za-z\s]+)\s*\n(?:Tel:|Email:|Fax:)',
    ]
    
    for pattern in signature_patterns:
        match = re.search(pattern, email_content, re.MULTILINE | re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            # 只取第一行作为姓名
            first_line = name.split('\n')[0].strip()
            if first_line and len(first_line) > 1 and not re.match(r'^\d+$', first_line):
                return first_line
    
    # 3. 从Distribution Listextract发件人
    dist_pattern = r'Distribution\s+List\s*-\s*To\s*:\s*([^\n]+)'
    dist_match = re.search(dist_pattern, email_content, re.IGNORECASE)
    if dist_match:
        email_addr = dist_match.group(1).strip()
        # 从邮箱地址extract部门information
        if '@' in email_addr:
            local_part = email_addr.split('@')[0]
            # 转换为可读的部门名称
            dept_name = format_department_name(local_part)
            if dept_name:
                return dept_name
    
    # 4. 默认return空string
    return ""


def extract_contact_number(email_content: str) -> str:
    """
    extract邮件中的联系电话号码
    
    优先级：
    1. Tel: 后面的号码
    2. 电话: 后面的号码  
    3. 其他电话格式
    """
    
    # 1. 标准Tel:格式
    tel_patterns = [
        r'Tel:\s*([0-9\s\-\+\(\)]+)',
        r'电话:\s*([0-9\s\-\+\(\)]+)',
        r'Tel\s+No\.?:\s*([0-9\s\-\+\(\)]+)',
        r'电话号码:\s*([0-9\s\-\+\(\)]+)',
    ]
    
    for pattern in tel_patterns:
        match = re.search(pattern, email_content, re.IGNORECASE)
        if match:
            phone = match.group(1).strip()
            # cleanup和format电话号码
            formatted_phone = format_phone_number(phone)
            if formatted_phone:
                return formatted_phone
    
    # 2. 从body内容中extractTel No.
    tel_no_pattern = r'Tel\s+No\.?\s*:\s*([0-9\s\-\+\(\)]+)'
    tel_match = re.search(tel_no_pattern, email_content, re.IGNORECASE)
    if tel_match:
        phone = tel_match.group(1).strip()
        formatted_phone = format_phone_number(phone)
        if formatted_phone:
            return formatted_phone
    
    # 3. find其他可能的电话格式
    general_phone_patterns = [
        r'(?:联系电话|手机|电话)[：:]\s*([0-9\s\-\+\(\)]+)',
        r'(?:Contact|Phone|Mobile)[：:]\s*([0-9\s\-\+\(\)]+)',
        r'\b([0-9]{4}\s*[0-9]{4})\b',  # 8位数字格式
        r'\b([0-9]{8})\b',  # 连续8位数字
    ]
    
    for pattern in general_phone_patterns:
        match = re.search(pattern, email_content, re.IGNORECASE)
        if match:
            phone = match.group(1).strip()
            formatted_phone = format_phone_number(phone)
            if formatted_phone and len(formatted_phone.replace(' ', '').replace('-', '')) >= 8:
                return formatted_phone
    
    return ""


def format_phone_number(phone: str) -> str:
    """
    format电话号码
    
    Args:
        phone: 原始电话号码string
        
    Returns:
        str: format后的电话号码
    """
    if not phone:
        return ""
    
    # 移除多余的空格和特殊字符
    cleaned = re.sub(r'[^\d\+\-\(\)\s]', '', phone.strip())
    
    # 移除多余的空格
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    # 如果是纯数字且长度合适，添加空格分隔
    digits_only = re.sub(r'[^\d]', '', cleaned)
    if len(digits_only) == 8 and digits_only.isdigit():
        # 香港电话号码格式：XXXX XXXX
        return f"{digits_only[:4]} {digits_only[4:]}"
    elif len(digits_only) >= 8:
        return cleaned
    
    return cleaned if len(cleaned) >= 4 else ""


def format_department_name(local_part: str) -> str:
    """
    将邮箱地址的本地部分转换为可读的部门名称
    
    Args:
        local_part: 邮箱地址@前面的部分
        
    Returns:
        str: format的部门名称
    """
    if not local_part:
        return ""
    
    # 常见部门缩写map
    dept_mapping = {
        'archsd_psb_enquiry': 'Architectural Services Department - Property Services Branch',
        'archsd': 'Architectural Services Department',
        'psb': 'Property Services Branch',
        '1823_general': '1823 General Enquiry',
        'cedd': 'Civil Engineering and Development Department',
        'ld': 'Lands Department',
        'hyd': 'Highways Department',
    }
    
    # 直接match
    if local_part.lower() in dept_mapping:
        return dept_mapping[local_part.lower()]
    
    # 部分match
    for key, value in dept_mapping.items():
        if key in local_part.lower():
            return value
    
    # 如果没有match，returnformat的原始string
    formatted = local_part.replace('_', ' ').title()
    return formatted if len(formatted) > 2 else ""


def extract_citizen_contact_from_body(body_content: str) -> Dict[str, str]:
    """
    从bodyfile中extract市民的联系information（如果可用）
    
    Args:
        body_content: bodyfile内容
        
    Returns:
        dict: 包含市民联系information的dictionary
    """
    result = {
        'citizen_name': '',
        'citizen_tel': '',
        'citizen_email': ''
    }
    
    if not body_content:
        return result
    
    # extract姓名（通常在Name:field，但可能被隐藏）
    name_patterns = [
        r'Name:\s*([^\n\r]+)',
        r'姓名:\s*([^\n\r]+)',
        r'联系人:\s*([^\n\r]+)',
        r'Contact\s+Person:\s*([^\n\r]+)',
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, body_content, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            # filter掉无效的姓名
            if (name and 
                name not in ['', '***HIDDEN***', 'N/A'] and
                not name.startswith('Email:') and
                not name.startswith('Tel:') and
                len(name) > 1 and
                not re.match(r'^[:\s]*$', name)):
                result['citizen_name'] = name
                break
    
    # extract电话号码
    tel_patterns = [
        r'Tel\s+No\.?\s*:\s*([0-9\s\-\+\(\)]+)',
        r'电话:\s*([0-9\s\-\+\(\)]+)',
        r'联系电话:\s*([0-9\s\-\+\(\)]+)',
    ]
    
    for pattern in tel_patterns:
        match = re.search(pattern, body_content, re.IGNORECASE)
        if match:
            tel = match.group(1).strip()
            if tel and tel not in ['', '***HIDDEN***', 'N/A']:
                formatted_tel = format_phone_number(tel)
                if formatted_tel:
                    result['citizen_tel'] = formatted_tel
                    break
    
    # extract邮箱
    email_patterns = [
        r'Email:\s*([^\s\n\r]+@[^\s\n\r]+)',
        r'邮箱:\s*([^\s\n\r]+@[^\s\n\r]+)',
        r'电子邮件:\s*([^\s\n\r]+@[^\s\n\r]+)',
    ]
    
    for pattern in email_patterns:
        match = re.search(pattern, body_content, re.IGNORECASE)
        if match:
            email = match.group(1).strip()
            if email and email not in ['', '***HIDDEN***', 'N/A'] and '@' in email:
                result['citizen_email'] = email
                break
    
    return result


def get_email_contact_info(email_content: str, body_content: str = "") -> Dict[str, str]:
    """
    综合extract邮件联系information的主function
    
    Args:
        email_content: 邮件内容
        body_content: bodyfile内容（optional）
        
    Returns:
        dict: 包含E_caller_name和F_contact_no的dictionary
    """
    # 从邮件内容extract
    email_info = extract_email_contact_info(email_content)
    
    # 从body内容extract市民information（作为备选）
    citizen_info = extract_citizen_contact_from_body(body_content) if body_content else {}
    
    # 决定最终使用的information
    result = {
        'E_caller_name': '',
        'F_contact_no': ''
    }
    
    # E_caller_name优先级：邮件落款 > 市民姓名 > 空
    if email_info.get('E_caller_name'):
        result['E_caller_name'] = email_info['E_caller_name']
    elif citizen_info.get('citizen_name'):
        result['E_caller_name'] = citizen_info['citizen_name']
    
    # F_contact_no优先级：邮件电话 > 市民电话 > 空
    if email_info.get('F_contact_no'):
        result['F_contact_no'] = email_info['F_contact_no']
    elif citizen_info.get('citizen_tel'):
        result['F_contact_no'] = citizen_info['citizen_tel']
    
    return result


if __name__ == "__main__":
    # testfunction
    print("=== 邮件informationextracttest ===")
    
    # test样例1
    sample_email = """
To: - Property Services Branch,

We have received the enclosed enquiry that requires a response from your department.

Thank you for your assistance.

1823 Duty Manager 

Tel: 3142 2013 
Fax: 3142 2602
Email: 1823_general@1823.gov.hk

Distribution List - To : archsd_psb_enquiry@archsd.gov.hk
"""
    
    result = extract_email_contact_info(sample_email)
    print(f"测试样例1result:")
    print(f"E_caller_name: '{result['E_caller_name']}'")
    print(f"F_contact_no: '{result['F_contact_no']}'")
    print()
    
    # test样例2 - body内容
    sample_body = """
Case Type:		Complaint
Name:			张三
Email:			zhangsan@example.com
Tel No.:	    9876 5432
Details:	    投诉内容...
"""
    
    citizen_result = extract_citizen_contact_from_body(sample_body)
    print(f"Body内容extractresult:")
    print(f"citizen_name: '{citizen_result['citizen_name']}'")
    print(f"citizen_tel: '{citizen_result['citizen_tel']}'")
    print(f"citizen_email: '{citizen_result['citizen_email']}'")
    print()
    
    # 综合test
    combined_result = get_email_contact_info(sample_email, sample_body)
    print(f"综合extractresult:")
    print(f"E_caller_name: '{combined_result['E_caller_name']}'")
    print(f"F_contact_no: '{combined_result['F_contact_no']}'")
