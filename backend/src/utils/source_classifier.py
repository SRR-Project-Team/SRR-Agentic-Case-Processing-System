#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
来源classify器
根据文件处理类型直接判断B_source字段的值
简化规则：仅支持4个类别 - TMO、ICC、RCC、Others
"""

import logging

logger = logging.getLogger(__name__)


class SourceClassifier:
    """来源classify器"""
    
    def __init__(self):
        """初始化分类器"""
        pass
    
    def classify_source(self, processing_type: str = None, file_path: str = None, 
                       content: str = "", email_content: str = None, 
                       file_type: str = "txt") -> str:
        """
        根据处理类型直接分类来源
        
        规则：
        - processing_type="txt" → "ICC" (1823通过邮件或app发送的TXT文件)
        - processing_type="tmo" → "TMO" (TMO通过邮件发送的PDF文件，ASD开头)
        - processing_type="rcc" → "RCC" (RCC通过传真扫描的PDF文件，RCC开头)
        - 其他情况 → "Others"
        
        Args:
            processing_type (str): 文件处理类型 ('txt', 'tmo', 'rcc', 'unknown')
            file_path (str): file path (保留用于向后兼容)
            content (str): 文件内容 (保留用于向后兼容)
            email_content (str): 邮件内容 (保留用于向后兼容)
            file_type (str): 文件class型 (保留用于向后兼容)
            
        Returns:
            str: 来源名称 ('TMO', 'ICC', 'RCC', 'Others')
        """
        logger.debug(f"🔍 开始来源分类...")
        logger.debug(f"   处理类型: {processing_type}")
        
        # 根据处理类型直接返回对应的源类型
        if processing_type == "txt":
            logger.info("📝 TXT文件，分类为 ICC (1823)")
            return "ICC"
        elif processing_type == "tmo":
            logger.info("🌳 TMO PDF文件，分类为 TMO")
            return "TMO"
        elif processing_type == "rcc":
            logger.info("📋 RCC PDF文件，分类为 RCC")
            return "RCC"
        else:
            logger.warning("❓ 未知处理类型，使用默认值 Others")
            return "Others"


# 全局classify器instance
_source_classifier = None


def get_source_classifier() -> SourceClassifier:
    """获取全局来源classify器instance"""
    global _source_classifier
    if _source_classifier is None:
        _source_classifier = SourceClassifier()
    return _source_classifier


def classify_source_smart(processing_type: str = None, file_path: str = None, 
                         content: str = "", email_content: str = None, 
                         file_type: str = "txt") -> str:
    """
    根据处理类型分类来源的便捷函数
    
    Args:
        processing_type (str): 文件处理类型 ('txt', 'tmo', 'rcc', 'unknown') - 必需参数
        file_path (str): file path (保留用于向后兼容)
        content (str): 文件内容 (保留用于向后兼容)
        email_content (str): 邮件内容 (保留用于向后兼容)
        file_type (str): 文件class型 (保留用于向后兼容)
        
    Returns:
        str: 来源名称 ('TMO', 'ICC', 'RCC', 'Others')
    """
    classifier = get_source_classifier()
    return classifier.classify_source(processing_type, file_path, content, email_content, file_type)


def test_source_classifier():
    """测试来源classify器"""
    print("=== 来源分类器测试 ===\n")
    
    classifier = SourceClassifier()
    
    # test用例 - 根据新的简化规则
    test_cases = [
        {
            'name': 'TXT文件处理类型',
            'processing_type': 'txt',
            'expected': 'ICC'
        },
        {
            'name': 'TMO PDF文件处理类型',
            'processing_type': 'tmo',
            'expected': 'TMO'
        },
        {
            'name': 'RCC PDF文件处理类型',
            'processing_type': 'rcc',
            'expected': 'RCC'
        },
        {
            'name': '未知处理类型',
            'processing_type': 'unknown',
            'expected': 'Others'
        },
        {
            'name': 'None处理类型',
            'processing_type': None,
            'expected': 'Others'
        }
    ]
    
    print("📋 测试案例:")
    success_count = 0
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. {test_case['name']}")
        
        result = classifier.classify_source(
            processing_type=test_case['processing_type']
        )
        
        expected = test_case['expected']
        
        if result == expected:
            print(f"   ✅ 正确: {result}")
            success_count += 1
        else:
            print(f"   ❌ 错误:")
            print(f"      期望: {expected}")
            print(f"      实际: {result}")
    
    accuracy = success_count / len(test_cases)
    print(f"\n📈 分类准确率: {accuracy:.1%} ({success_count}/{len(test_cases)})")
    
    # 显示有效来源选项
    print(f"\n📋 有效来源选项:")
    valid_sources = ['TMO', 'ICC', 'RCC', 'Others']
    for source in valid_sources:
        print(f"   - {source}")


if __name__ == "__main__":
    test_source_classifier()
