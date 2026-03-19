#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
斜坡位置mapmodule
根据斜坡编号从models/mapping_rules/slope_location_mapping.jsonfind对应的venuevalue
"""

import json
import os
import re
from typing import Optional

# 获取当前文件所在目录的父目录（即backend目录）
CURRENT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load_slope_mapping(language : str = "English"):
    """加载斜坡位置映射data"""
    if language == "English":
        mapping_file = os.path.join(CURRENT_DIR, 'models/mapping_rules/slope_location_mapping.json')
    elif language == "Chinese":
        mapping_file = os.path.join(CURRENT_DIR, 'models/mapping_rules/slope_location_mapping_cn.json')
    if os.path.exists(mapping_file):
        with open(mapping_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        print(f"⚠️ 斜坡映射文件不存在: {mapping_file}")
        return {}

def get_location_from_slope_no(slope_no: str, language: str = "English") -> str:
    """
    根据斜坡编号获取位置information
    
    Args:
        slope_no: 斜坡编号，如 "11SW-D/805"
    
    Returns:
        str: 位置information，如果找不到则return空字符串
    """
    if not slope_no or not isinstance(slope_no, str):
        return ""
    
    # loadmapdata
    slope_mapping_en = load_slope_mapping("English")
    slope_mapping_cn = load_slope_mapping("Chinese")
    
    if not slope_mapping_en or not slope_mapping_cn:
        print("⚠️ 斜坡映射data未加载")
        return ""
    
    # 直接find
    if slope_no in slope_mapping_en:
        if slope_no in slope_mapping_cn:
            return slope_mapping_en[slope_no] + "/" + slope_mapping_cn[slope_no]
        return slope_mapping_en[slope_no]
    
    # 尝试多种match方式
    cleaned_slope = clean_slope_number(slope_no)
    if slope_no in slope_mapping_en:
        if slope_no in slope_mapping_cn:
            return slope_mapping_en[cleaned_slope] + "/" + slope_mapping_cn[cleaned_slope]
        return slope_mapping_en[cleaned_slope]
    
    # 模糊match两表中的地址
    for mapped_slope, venue in slope_mapping_en.items():
        if is_slope_match(slope_no, mapped_slope):
            return venue
    
    return ""

def clean_slope_number(slope_no: str) -> str:
    """
    清理斜坡编号，去除干扰information
    
    Args:
        slope_no: 原始斜坡编号
    
    Returns:
        str: 清理后的斜坡编号
    """
    if not slope_no:
        return ""
    
    # 去除前后空格
    cleaned = slope_no.strip()
    
    # 去除#号等干扰字符
    cleaned = re.sub(r'[#\s]+', '', cleaned)
    
    # 确保以数字开头
    if not re.match(r'^\d', cleaned):
        # 如果开头不是数字，尝试extract数字部分
        match = re.search(r'\d+[A-Za-z]+[-/][A-Za-z0-9]+', cleaned)
        if match:
            cleaned = match.group()
    
    return cleaned

def is_slope_match(slope1: str, slope2: str) -> bool:
    """
    判断两个斜坡编号是否匹配
    
    Args:
        slope1: 斜坡编号1
        slope2: 斜坡编号2
    
    Returns:
        bool: 是否匹配
    """
    if not slope1 or not slope2:
        return False
    
    # cleanup两个编号
    clean1 = clean_slope_number(slope1)
    clean2 = clean_slope_number(slope2)
    
    # 直接match
    if clean1 == clean2:
        return True
    
    # extract核心部分进行match
    core1 = extract_slope_core(clean1)
    core2 = extract_slope_core(clean2)
    
    return core1 == core2 and core1 != ""

def normalize_slope_core(slope_no: str) -> str:
    """
    规范化斜坡编号核心形式，用于聊天检索匹配。
    只去掉末尾的 (数字) 后缀，使 11SW-A/FR24(3) 与 11SW-A/FR24 视为同一棵树。
    不改变 11SW-A/FR241（无括号），与 11SW-A/FR24 区分开。

    Args:
        slope_no: 原始斜坡编号

    Returns:
        str: 规范化后的核心形式
    """
    if not slope_no:
        return ""
    s = str(slope_no).strip()
    return re.sub(r"\s*\(\d+\)\s*$", "", s)


def extract_slope_from_query(query: str) -> Optional[str]:
    """
    从自由文本查询中提取斜坡编号（方案 A）。
    支持 11SW-A/FR24、11SW-A/FR24(3) 等格式，与 TMO extract 逻辑一致。

    Args:
        query: 用户查询文本

    Returns:
        提取到的斜坡编号，若无则返回 None
    """
    if not query or not isinstance(query, str):
        return None
    # 与 extractFromTMO 类似的模式：支持带/不带括号；不用 \b 以兼容中文前后文
    pattern = r"(\d+[A-Z]+-[A-Z]+/[A-Za-z0-9]+(?:\(\d+\))?)"
    match = re.search(pattern, query, re.IGNORECASE)
    if match:
        raw = match.group(1).strip()
        cleaned = clean_slope_number(raw)
        return cleaned if cleaned else None
    return None


def extract_slope_core(slope_no: str) -> str:
    """
    extract斜坡编号的核心部分
    
    Args:
        slope_no: 斜坡编号
    
    Returns:
        str: 核心部分
    """
    if not slope_no:
        return ""
    
    # match模式：数字+字母+斜杠+字母数字
    match = re.search(r'(\d+[A-Za-z]+[-/][A-Za-z0-9]+)', slope_no)
    if match:
        return match.group(1)
    
    return ""

def get_all_slope_locations() -> dict:
    """
    获取所有斜坡位置映射
    
    Returns:
        dict: 斜坡编号到位置的映射字典
    """
    return load_slope_mapping()

def search_slope_by_location(location_keyword: str) -> list:
    """
    根据位置关键词搜索斜坡编号
    
    Args:
        location_keyword: 位置关键词
    
    Returns:
        list: 匹配的斜坡编号列table
    """
    slope_mapping = load_slope_mapping()
    matches = []
    
    if not slope_mapping:
        return matches
    
    location_keyword = location_keyword.lower()
    
    for slope_no, venue in slope_mapping.items():
        if location_keyword in venue.lower():
            matches.append(slope_no)
    
    return matches

# testfunction
def test_slope_mapping():
    """测试斜坡映射function"""
    print("🧪 测试斜坡映射function...")
    
    test_slopes = ["11SW-D/805", "11SW-B/F199", "11SW-D/CR995"]
    
    for slope in test_slopes:
        location = get_location_from_slope_no(slope)
        print(f"斜坡 {slope}: {location}")
    
    # testsearchfunction
    search_results = search_slope_by_location("Aberdeen")
    print(f"包含'Aberdeen'的斜坡: {search_results[:3]}")

if __name__ == "__main__":
    test_slope_mapping()
