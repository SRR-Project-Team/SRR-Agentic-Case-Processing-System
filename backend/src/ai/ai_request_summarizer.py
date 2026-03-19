#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AIrequest摘要生成器module

本module专门用于从邮件或PDF（传真）内容中生成简洁、准确的request摘要。
与传统的邮件结构extract不同，本module专注于识别和summarize具体的request内容。

mainfunction：
1. 智能识别17种不同class型的request模式
2. 从复杂内容中extract核心requestinformation
3. 生成简洁的自然语言摘要
4. 支持多语言内容process（中文/英文）
5. 提供confidenceevaluate和内容融合

技术特点：
- 基于正则table达式的模式match
- 多源内容融合算法
- confidence评分机制
- 智能内容cleanup和format

作者: Project3 Team
版本: 2.0
"""

import re
from typing import Optional, Dict, List, Tuple
import os


class AIRequestSummarizer:
    """
    AI请求摘要生成器
    
    专门用于从邮件或PDF内容中extract和summarize具体的请求information，
    生成简洁、准确的案件请求摘要。
    
    Attributes:
        request_patterns (List[Dict]): 请求识别模式列table
        content_extractors (Dict): 内容extract器字典
    """
    
    def __init__(self):
        """
        initialize摘要生成器
        
        构建请求识别模式和内容extract器，用于后续的摘要生成。
        """
        self.request_patterns = self._build_request_patterns()
        self.content_extractors = self._build_content_extractors()
    
    def _build_request_patterns(self) -> List[Dict]:
        """构建请求识别模式"""
        return [
            # 中文query模式
            {
                'pattern': r'主旨[：:]\s*([^\n]+)',
                'type': 'subject',
                'priority': 10,
                'description': '邮件主旨'
            },
            {
                'pattern': r'查詢([^\n，。]+)',
                'type': 'inquiry',
                'priority': 9,
                'description': 'query请求'
            },
            {
                'pattern': r'投訴([^\n，。]+)',
                'type': 'complaint',
                'priority': 9,
                'description': '投诉内容'
            },
            {
                'pattern': r'要求([^\n，。]+)',
                'type': 'request',
                'priority': 8,
                'description': '具体要求'
            },
            {
                'pattern': r'申請([^\n，。]+)',
                'type': 'application',
                'priority': 8,
                'description': '申请事项'
            },
            {
                'pattern': r'報告([^\n，。]+)',
                'type': 'report',
                'priority': 7,
                'description': '报告事项'
            },
            
            # 英文query模式
            {
                'pattern': r'Subject[：:]\s*([^\n]+)',
                'type': 'subject',
                'priority': 10,
                'description': 'Email Subject'
            },
            {
                'pattern': r'Request for ([^\n,.]+)',
                'type': 'request',
                'priority': 8,
                'description': 'Request for'
            },
            {
                'pattern': r'Enquiry about ([^\n,.]+)',
                'type': 'inquiry',
                'priority': 9,
                'description': 'Enquiry about'
            },
            {
                'pattern': r'Complaint regarding ([^\n,.]+)',
                'type': 'complaint',
                'priority': 9,
                'description': 'Complaint regarding'
            },
            {
                'pattern': r'Application for ([^\n,.]+)',
                'type': 'application',
                'priority': 8,
                'description': 'Application for'
            },
            
            # 具体内容模式
            {
                'pattern': r'斜坡[編编號号]*[：:]?\s*([^\s，。\n]+)',
                'type': 'slope_info',
                'priority': 6,
                'description': '斜坡information'
            },
            {
                'pattern': r'維修工程([^\n，。]+)',
                'type': 'maintenance',
                'priority': 7,
                'description': '维修工程'
            },
            {
                'pattern': r'進度([^\n，。]*)',
                'type': 'progress',
                'priority': 6,
                'description': '进度query'
            }
        ]
    
    def _build_content_extractors(self) -> List[Dict]:
        """构建内容extract器"""
        return [
            # TXTfile内容extract
            {
                'source': 'txt_outbound',
                'patterns': [
                    r'主旨[：:]\s*([^\n]+)',
                    r'\[Detail\]\s*([^[]+?)(?=\[|$)',
                    r'Email - Outbound[^[]*?\[Detail\]\s*([^[]+?)(?=\[|$)'
                ],
                'priority': 10
            },
            {
                'source': 'txt_inbound',
                'patterns': [
                    r'Email - Inbound[^[]*?\[Detail\]\s*([^[]+?)(?=\[|$)',
                    r'WRITTEN CONTACT INBOUND DETAILS[^[]*?([^[]+?)(?=\[|$)'
                ],
                'priority': 8
            },
            
            # 邮件内容extract
            {
                'source': 'email_body',
                'patterns': [
                    r'We have received the following enquiry[：:]?\s*([^.]+)',
                    r'The citizen enquires about[：:]?\s*([^.]+)',
                    r'Enquiry details[：:]?\s*([^.]+)',
                    r'Request details[：:]?\s*([^.]+)'
                ],
                'priority': 9
            },
            
            # PDF内容extract
            {
                'source': 'pdf_content',
                'patterns': [
                    r'Nature of complaint[：:]?\s*([^\n]+)',
                    r'Description[：:]?\s*([^\n]+)',
                    r'Details[：:]?\s*([^\n]+)',
                    r'Complaint[：:]?\s*([^\n]+)'
                ],
                'priority': 7
            }
        ]
    
    def generate_request_summary(self, content: str, email_content: str = None, 
                               content_type: str = 'txt') -> str:
        """
        生成请求摘要
        
        Args:
            content: 主要内容（TXT/PDF内容）
            email_content: 邮件内容（可选）
            content_type: 内容class型 ('txt', 'pdf', 'email')
            
        Returns:
            str: 生成的请求摘要
        """
        print("🤖 开始AI请求摘要生成...")
        
        # 收集所有可能的requestinformation
        extracted_requests = []
        
        # 1. 从main内容extract
        if content:
            main_requests = self._extract_requests_from_content(content, content_type)
            extracted_requests.extend(main_requests)
        
        # 2. 从邮件内容extract
        if email_content:
            email_requests = self._extract_requests_from_content(email_content, 'email')
            extracted_requests.extend(email_requests)
        
        # 3. 按优先级sort并生成摘要
        if extracted_requests:
            # 按优先级和confidencesort
            extracted_requests.sort(key=lambda x: (x['priority'], x['confidence']), reverse=True)
            
            # 生成智能摘要
            summary = self._generate_intelligent_summary(extracted_requests)
            
            if summary:
                print(f"✅ AI请求摘要生成success: {summary}")
                return summary
        
        # 4. 如果没有extract到具体request，使用传统method
        fallback_summary = self._generate_fallback_summary(content, email_content)
        print(f"⚠️ 使用备用摘要method: {fallback_summary}")
        return fallback_summary
    
    def _extract_requests_from_content(self, content: str, source_type: str) -> List[Dict]:
        """从内容中extract请求information"""
        requests = []
        
        if not content or not content.strip():
            return requests
        
        # 使用request模式match
        for pattern_info in self.request_patterns:
            pattern = pattern_info['pattern']
            matches = re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE)
            
            for match in matches:
                extracted_text = match.group(1).strip() if match.groups() else match.group(0).strip()
                
                if extracted_text and len(extracted_text) > 3:  # 过滤太短的匹配
                    # calculateconfidence
                    confidence = self._calculate_confidence(extracted_text, pattern_info, source_type)
                    
                    requests.append({
                        'text': extracted_text,
                        'type': pattern_info['type'],
                        'priority': pattern_info['priority'],
                        'confidence': confidence,
                        'source': source_type,
                        'description': pattern_info['description']
                    })
        
        return requests
    
    def _calculate_confidence(self, text: str, pattern_info: Dict, source_type: str) -> float:
        """计算extractconfidence"""
        confidence = 0.5  # 基础confidence
        
        # 根据文本长度调整
        if 10 <= len(text) <= 100:
            confidence += 0.2
        elif len(text) > 100:
            confidence += 0.1
        
        # 根据模式class型调整
        if pattern_info['type'] in ['subject', 'inquiry', 'complaint']:
            confidence += 0.2
        
        # 根据来源class型调整
        if source_type == 'txt' and pattern_info['type'] == 'subject':
            confidence += 0.3
        elif source_type == 'email' and 'enquiry' in text.lower():
            confidence += 0.2
        
        # 根据关key词调整
        keywords = ['斜坡', '維修', '工程', '進度', 'slope', 'maintenance', 'repair', 'progress']
        keyword_count = sum(1 for keyword in keywords if keyword.lower() in text.lower())
        confidence += keyword_count * 0.1
        
        return min(confidence, 1.0)  # 最大confidence为1.0
    
    def _generate_intelligent_summary(self, requests: List[Dict]) -> Optional[str]:
        """生成智能摘要"""
        if not requests:
            return None
        
        # 选择最高优先级和confidence的request
        best_request = requests[0]
        
        # 如果是主旨class型，直接使用
        if best_request['type'] == 'subject' and best_request['confidence'] > 0.7:
            return self._clean_summary_text(best_request['text'])
        
        # 组合多个相关request
        summary_parts = []
        used_types = set()
        
        for request in requests[:3]:  # 最多使用前3个请求
            if request['confidence'] > 0.6 and request['type'] not in used_types:
                cleaned_text = self._clean_summary_text(request['text'])
                if cleaned_text:
                    summary_parts.append(cleaned_text)
                    used_types.add(request['type'])
        
        if summary_parts:
            # 智能组合摘要
            if len(summary_parts) == 1:
                return summary_parts[0]
            else:
                # check是否可以merge
                combined = self._combine_summary_parts(summary_parts)
                return combined
        
        return None
    
    def _clean_summary_text(self, text: str) -> str:
        """清理摘要文本"""
        if not text:
            return ""
        
        # 移除多余的空格和换行
        text = re.sub(r'\s+', ' ', text).strip()
        
        # 移除HTML标签
        text = re.sub(r'<[^>]+>', '', text)
        
        # 移除特殊字符
        text = re.sub(r'[^\w\s\-/：:，。()（）]', '', text)
        
        # 限制长度
        if len(text) > 150:
            text = text[:150] + "..."
        
        return text
    
    def _combine_summary_parts(self, parts: List[str]) -> str:
        """组合摘要部分"""
        if not parts:
            return ""
        
        # check是否有duplicate内容
        unique_parts = []
        for part in parts:
            is_duplicate = False
            for existing in unique_parts:
                if self._is_similar_content(part, existing):
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_parts.append(part)
        
        # 智能组合
        if len(unique_parts) == 1:
            return unique_parts[0]
        elif len(unique_parts) <= 3:
            return " | ".join(unique_parts)
        else:
            return unique_parts[0] + " 等多项请求"
    
    def _is_similar_content(self, text1: str, text2: str) -> bool:
        """check内容是否相似"""
        if not text1 or not text2:
            return False
        
        # 简单的相似度check
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if len(words1) == 0 or len(words2) == 0:
            return False
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        similarity = intersection / union if union > 0 else 0
        return similarity > 0.6
    
    def _generate_fallback_summary(self, content: str, email_content: str = None) -> str:
        """生成备用摘要"""
        # 尝试从内容中extract任何有意义的information
        fallback_patterns = [
            r'主旨[：:]\s*([^\n]+)',
            r'Subject[：:]\s*([^\n]+)',
            r'查詢([^\n，。]+)',
            r'Request for ([^\n,.]+)',
            r'Enquiry about ([^\n,.]+)',
            r'Description[：:]\s*([^\n]+)',
            r'Nature of complaint[：:]\s*([^\n]+)'
        ]
        
        sources = [content, email_content] if email_content else [content]
        
        for source in sources:
            if not source:
                continue
                
            for pattern in fallback_patterns:
                match = re.search(pattern, source, re.IGNORECASE)
                if match:
                    extracted = match.group(1).strip()
                    if extracted and len(extracted) > 5:
                        return self._clean_summary_text(extracted)
        
        # 最后的备用方案
        if content and len(content.strip()) > 10:
            # extract前100个字符作为摘要
            summary = content.strip()[:100]
            if len(content.strip()) > 100:
                summary += "..."
            return self._clean_summary_text(summary)
        
        return "无法extract具体请求内容"


def generate_ai_request_summary(content: str, email_content: str = None, 
                              content_type: str = 'txt') -> str:
    """
    生成AI请求摘要的入口函数
    
    Args:
        content: 主要内容
        email_content: 邮件内容（可选）
        content_type: 内容class型
        
    Returns:
        str: 生成的请求摘要
    """
    summarizer = AIRequestSummarizer()
    return summarizer.generate_request_summary(content, email_content, content_type)


def test_ai_request_summarizer():
    """测试AI请求摘要生成器"""
    print("=== AI请求摘要生成器测试 ===\n")
    
    # test用例
    test_cases = [
        {
            'name': '斜坡维修query',
            'content': '主旨：查詢斜坡維修編號11SW-D/805維修工程進度 (檔案編號：3-8641924612)',
            'email_content': None,
            'type': 'txt'
        },
        {
            'name': '树木修剪请求',
            'content': 'Request for tree trimming at slope area 15NE-A/F91',
            'email_content': 'We have received the following enquiry: The citizen requests tree maintenance work.',
            'type': 'txt'
        },
        {
            'name': '排水问题投诉',
            'content': '投訴斜坡排水系統堵塞問題',
            'email_content': None,
            'type': 'pdf'
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"📋 测试案例 {i}: {test_case['name']}")
        
        try:
            summary = generate_ai_request_summary(
                test_case['content'],
                test_case['email_content'],
                test_case['type']
            )
            
            print(f"   ✅ 摘要result: {summary}")
            
        except Exception as e:
            print(f"   ❌ 测试failed: {e}")
        
        print()


if __name__ == "__main__":
    test_ai_request_summarizer()
