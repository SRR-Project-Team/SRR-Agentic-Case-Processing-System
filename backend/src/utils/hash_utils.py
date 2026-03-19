#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件哈希计算工具模块

本模块提供文件内容哈希计算功能，用于：
1. 文件去重检测
2. 内容完整性验证

使用SHA256算法确保哈希唯一性

作者: Project3 Team
版本: 1.0
"""

import hashlib


def calculate_file_hash(file_content: bytes) -> str:
    """
    计算文件内容的SHA256哈希值
    
    Args:
        file_content: 文件的二进制内容
        
    Returns:
        str: 64位十六进制哈希字符串
        
    Example:
        >>> with open('file.txt', 'rb') as f:
        ...     content = f.read()
        >>> hash_value = calculate_file_hash(content)
        >>> print(hash_value)
        'a1b2c3d4...'
    """
    return hashlib.sha256(file_content).hexdigest()


def calculate_string_hash(text: str) -> str:
    """
    计算字符串的SHA256哈希值
    
    Args:
        text: 文本字符串
        
    Returns:
        str: 64位十六进制哈希字符串
    """
    return hashlib.sha256(text.encode('utf-8')).hexdigest()
