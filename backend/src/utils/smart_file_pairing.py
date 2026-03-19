#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能file配对module
用于识别和配对TXT案件file与对应的邮件file
"""

import re
from typing import List, Dict, Tuple, Optional


class FileInfo:
    """文件informationclass"""
    def __init__(self, filename: str, content_type: str, file_data: bytes = None):
        self.filename = filename
        self.content_type = content_type
        self.file_data = file_data
        self.is_email = self._is_email_file()
        self.case_id = self._extract_case_id()
    
    def _is_email_file(self) -> bool:
        """判断是否为邮件文件"""
        return self.filename.lower().startswith('emailcontent_')
    
    def _extract_case_id(self) -> Optional[str]:
        """extract案件ID"""
        if self.is_email:
            # 从 emailcontent_3-3YXXSJV.txt extract 3-3YXXSJV
            match = re.search(r'emailcontent_(.+?)\.txt$', self.filename, re.IGNORECASE)
            if match:
                return match.group(1)
        else:
            # 从 3-3YXXSJV.txt extract 3-3YXXSJV
            match = re.search(r'([^/\\]+)\.txt$', self.filename, re.IGNORECASE)
            if match:
                base_name = match.group(1)
                # 排除已知的邮件file前缀
                if not base_name.lower().startswith('emailcontent_'):
                    return base_name
        return None


class SmartFilePairing:
    """智能文件配对器"""
    
    def __init__(self):
        self.files: List[FileInfo] = []
    
    def add_file(self, filename: str, content_type: str, file_data: bytes = None) -> None:
        """添加文件到配对器"""
        file_info = FileInfo(filename, content_type, file_data)
        self.files.append(file_info)
    
    def pair_files(self) -> List[Dict]:
        """
        配对文件并returnprocess计划
        
        Returns:
            List[Dict]: process计划列table，每个元素包含：
            {
                'type': 'txt_with_email' | 'txt_only' | 'skip' ｜ 'pdf',
                'main_file': FileInfo,
                'email_file': Optional[FileInfo],
                'case_id': str,
                'description': str
            }
        """
        processing_plan = []
        processed_case_ids = set()
        
        # 分类files
        txt_files = [f for f in self.files if not f.is_email and f.filename.lower().endswith('.txt')]
        email_files = [f for f in self.files if f.is_email]
        pdf_files = [f for f in self.files if f.filename.lower().endswith('.pdf') and (f.filename.upper().startswith('ASD') or f.filename.upper().startswith('RCC'))]
        skip_files = [f for f in self.files if f not in txt_files and f not in email_files and f not in pdf_files]

        
        print(f"📁 文件分析:")
        print(f"   - TXT案件文件: {len(txt_files)} 个")
        print(f"   - 邮件文件: {len(email_files)} 个")
        print(f"   - 可处理PDF文件: {len(pdf_files)} 个")
        print(f"   - 无法处理文件: {len(skip_files)} 个")

        
        # 为每个TXTfile寻找对应的邮件file
        for txt_file in txt_files:
            if txt_file.case_id and txt_file.case_id not in processed_case_ids:
                # 寻找match的邮件file
                matching_email = self._find_matching_email(txt_file, email_files)
                
                if matching_email:
                    processing_plan.append({
                        'type': 'txt_with_email',
                        'main_file': txt_file,
                        'email_file': matching_email,
                        'case_id': txt_file.case_id,
                        'description': f'process案件 {txt_file.case_id}（包含邮件information）'
                    })
                    print(f"✅ 配对success: {txt_file.filename} + {matching_email.filename}")
                else:
                    processing_plan.append({
                        'type': 'txt_only',
                        'main_file': txt_file,
                        'email_file': None,
                        'case_id': txt_file.case_id,
                        'description': f'process案件 {txt_file.case_id}（仅TXT文件）'
                    })
                    print(f"📄 单独process: {txt_file.filename}")
                
                processed_case_ids.add(txt_file.case_id)
        
        # check未配对的邮件file
        unmatched_emails = [e for e in email_files if not any(
            plan['email_file'] and plan['email_file'].filename == e.filename 
            for plan in processing_plan
        )]
        
        for email_file in unmatched_emails:
            processing_plan.append({
                'type': 'skip',
                'main_file': email_file,
                'email_file': None,
                'case_id': email_file.case_id or 'unknown',
                'description': f'跳过独立邮件文件 {email_file.filename}无对应TXT文件'
            })
            print(f"⚠️ 跳过邮件文件: {email_file.filename} 无对应TXT文件")

        for skip_file in skip_files:
            processing_plan.append({
                'type': 'skip',
                'main_file': skip_file,
                'email_file': None,
                'case_id': skip_file.case_id or 'unknown',
                'description': f'跳过独立文件 {skip_file.filename}无法处理'
            })
            print(f"⚠️ 跳过邮件文件: {skip_file.filename} 无法处理")
        
        return processing_plan
    
    def _find_matching_email(self, txt_file: FileInfo, email_files: List[FileInfo]) -> Optional[FileInfo]:
        """为TXT文件寻找匹配的邮件文件"""
        if not txt_file.case_id:
            return None
        
        for email_file in email_files:
            if email_file.case_id == txt_file.case_id:
                return email_file
        
        return None
    
    def get_processing_summary(self) -> Dict:
        """获取process摘要"""
        plan = self.pair_files()
        
        summary = {
            'total_files': len(self.files),
            'txt_with_email': len([p for p in plan if p['type'] == 'txt_with_email']),
            'txt_only': len([p for p in plan if p['type'] == 'txt_only']),
            'skipped': len([p for p in plan if p['type'] == 'skip']),
            'processing_plan': plan
        }
        
        return summary


def test_smart_file_pairing():
    """测试智能文件配对function"""
    
    print("=== 智能文件配对测试 ===\n")
    
    # createpairing
    pairing = SmartFilePairing()
    
    # test场景1: 完整配对
    print("📋 测试场景1: 完整配对")
    pairing.add_file('3-3YXXSJV.txt', 'text/plain')
    pairing.add_file('emailcontent_3-3YXXSJV.txt', 'text/plain')
    
    summary1 = pairing.get_processing_summary()
    print(f"process摘要: {summary1['txt_with_email']} 个完整配对, {summary1['txt_only']} 个单独TXT, {summary1['skipped']} 个跳过")
    print()
    
    # test场景2: 混合情况
    print("📋 测试场景2: 混合情况")
    pairing = SmartFilePairing()
    pairing.add_file('3-3YXXSJV.txt', 'text/plain')
    pairing.add_file('emailcontent_3-3YXXSJV.txt', 'text/plain')
    pairing.add_file('3-3XYHOGP.txt', 'text/plain')  # 没有对应邮件
    pairing.add_file('emailcontent_3-3ZZZZZZ.txt', 'text/plain')  # 没有对应TXT
    
    summary2 = pairing.get_processing_summary()
    print(f"process摘要: {summary2['txt_with_email']} 个完整配对, {summary2['txt_only']} 个单独TXT, {summary2['skipped']} 个跳过")
    print()
    
    # 显示详细process计划
    print("📋 详细process计划:")
    for i, plan in enumerate(summary2['processing_plan'], 1):
        print(f"   {i}. {plan['description']}")


if __name__ == "__main__":
    test_smart_file_pairing()
