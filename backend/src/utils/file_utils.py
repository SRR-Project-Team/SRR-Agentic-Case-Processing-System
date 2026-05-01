#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fileprocessutilitymodule

本module提供智能的fileencoding检测和securityfilereadfunction，专门用于process
各种encoding格式的文本file，特别是中文文档和邮件内容。

mainfunction：
1. 智能encoding检测（支持BOM、chardet、常见encoding）
2. securityfileread（automaticencoding检测 + errorprocess）
3. 多encoding格式支持（UTF-8、GBK、GB2312、Big5等）
4. error恢复机制（encodingfailed时的降级process）

技术特点：
- 基于chardet库的智能encoding检测
- 支持BOM标记识别
- 多级encoding尝试机制
- error忽略和容错process

作者: Project3 Team
版本: 2.0
"""

import chardet
import os
from typing import Optional

import pdfplumber
import PyPDF2
import pandas as pd


def detect_file_encoding(file_path: str) -> str:
    """
    智能检测文件encoding格式
    
    使用多级检测策略：
    1. checkBOM标记（UTF-8、UTF-16等）
    2. 使用chardet库进行智能检测
    3. 尝试常见encoding格式
    
    Args:
        file_path (str): file path
        
    Returns:
        str: 检测到的encoding格式，默认return'utf-8'
        
    Example:
        >>> encoding = detect_file_encoding('test.txt')
        >>> print(f"文件encoding: {encoding}")
    """
    # 1. checkBOM标记
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read(4)
            
        # UTF-8 BOM
        if raw_data.startswith(b'\xef\xbb\xbf'):
            print("🔍 检测到UTF-8 BOM")
            return 'utf-8-sig'
        # UTF-16 LE BOM
        elif raw_data.startswith(b'\xff\xfe'):
            print("🔍 检测到UTF-16 LE BOM")
            return 'utf-16-le'
        # UTF-16 BE BOM
        elif raw_data.startswith(b'\xfe\xff'):
            print("🔍 检测到UTF-16 BE BOM")
            return 'utf-16-be'
    except Exception as e:
        print(f"⚠️ BOM检测failed: {e}")
    
    # 2. 使用chardet检测
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read()
        
        result = chardet.detect(raw_data)
        if result and result['encoding']:
            confidence = result['confidence']
            encoding = result['encoding']
            print(f"🔍 chardet检测到encoding: {encoding} (confidence: {confidence:.2f})")
            
            # 如果confidence较高，直接使用
            if confidence > 0.7:
                return encoding
            
    except Exception as e:
        print(f"⚠️ chardet检测failed: {e}")
    
    # 3. 尝试常见encoding
    common_encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16', 'big5', 'latin1', 'cp1252']
    
    for encoding in common_encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                f.read(1024)  # 尝试读取前1024字符
            print(f"🔍 successvalidateencoding: {encoding}")
            return encoding
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception as e:
            print(f"⚠️ encoding {encoding} 测试failed: {e}")
            continue
    
    # 4. 默认returnUTF-8
    print("⚠️ 无法确定encoding，使用UTF-8作为默认")
    return 'utf-8'


def read_file_with_encoding(file_path: str) -> str:
    """
    使用智能encoding检测读取文件内容
    
    Args:
        file_path (str): file path
        
    Returns:
        str: 文件内容
        
    Raises:
        FileNotFoundError: 文件不存在
        Exception: 读取failed
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    # 检测encoding
    detected_encoding = detect_file_encoding(file_path)
    
    # 尝试使用检测到的encodingread
    encodings_to_try = [detected_encoding]
    
    # 添加备用encoding
    backup_encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'latin1', 'cp1252']
    for enc in backup_encodings:
        if enc not in encodings_to_try:
            encodings_to_try.append(enc)
    
    last_error = None
    
    for encoding in encodings_to_try:
        try:
            with open(file_path, 'r', encoding=encoding, errors='strict') as f:
                content = f.read()
            print(f"✅ 使用 {encoding} encoding读取文件success，文本长度: {len(content)} 字符")
            return content
            
        except UnicodeDecodeError as e:
            last_error = e
            print(f"⚠️ encoding {encoding} 读取failed: {e}")
            continue
        except Exception as e:
            last_error = e
            print(f"⚠️ 使用encoding {encoding} 时发生error: {e}")
            continue
    
    # 最后尝试忽略error的方式read
    try:
        print("🔄 尝试忽略encodingerror的方式读取...")
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        print(f"⚠️ 使用error忽略模式读取success，文本长度: {len(content)} 字符")
        return content
    except Exception as e:
        print(f"❌ error忽略模式也failed: {e}")
    
    # 如果所有method都failed，抛出exception
    raise Exception(f"无法读取文件 {file_path}，最后error: {last_error}")


def extract_text_with_ocr_fast(pdf_path: str) -> str:
    """
    快速OCRprocess，优先速度，限制process时间
    """
    import time
    start_time = time.time()
    max_processing_time = 60  # 最大process时间60秒
    content = ""
    
    # 只使用最快的EasyOCRmethod
    try:
        import easyocr
        import fitz  # PyMuPDF
        from PIL import Image
        import io
        
        # Compatibility fix for Pillow 10.0+: Add ANTIALIAS alias if missing
        # EasyOCR internally uses Image.ANTIALIAS which was removed in Pillow 10.0+
        if not hasattr(Image, 'ANTIALIAS'):
            Image.ANTIALIAS = Image.LANCZOS
        
        print("使用快速EasyOCRextract文本...")
        
        # initializeEasyOCR (只使用英文，最快settings)
        reader = easyocr.Reader(['en'], gpu=False, verbose=False, download_enabled=True)
        
        doc = fitz.open(pdf_path)
        
        # 只process前2页，避免process时间过长
        max_pages = min(2, len(doc))
        
        for page_num in range(max_pages):
            # checkprocess时间限制
            if time.time() - start_time > max_processing_time:
                print(f"⏰ 快速OCRprocess超时({max_processing_time}秒)，停止process")
                break
                
            page = doc.load_page(page_num)
            
            # 使用更低的分辨率，优先speed
            mat = fitz.Matrix(1.5, 1.5)  # 进一步降低到1.5倍分辨率
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            
            # 使用PIL打开图像
            image = Image.open(io.BytesIO(img_data))
            
            # 转换为numpyarray (EasyOCR需要numpyarray)
            import numpy as np
            image_array = np.array(image)
            
            # 使用EasyOCR进行OCR，降低confidence阈value
            results = reader.readtext(image_array)
            
            # extract文本
            page_text = ""
            for (bbox, text, confidence) in results:
                if confidence > 0.2:  # 进一步降低confidence阈值
                    page_text += text + " "
            
            if page_text.strip():
                content += page_text.strip() + "\n"
                print(f"快速OCRsuccessextract页面{page_num+1}文本: {len(page_text)}字符")
        
        doc.close()
        
        if content.strip():
            processing_time = time.time() - start_time
            print(f"✅ 快速OCR完成，耗时: {processing_time:.2f}秒")
            return content
        
    except ImportError:
        print("EasyOCR未安装，跳过快速OCR")
    except Exception as e:
        print(f"快速OCRextractexception: {e}")



def safe_file_read(file_path: str, default_content: str = "") -> str:
    """
    安全读取文件，failed时return默认内容
    
    Args:
        file_path (str): file path
        default_content (str): 默认内容
        
    Returns:
        str: 文件内容或默认内容
    """
    try:
        return read_file_with_encoding(file_path)
    except Exception as e:
        print(f"⚠️ 文件读取failed，使用默认内容: {e}")
        return default_content


def extract_text_from_pdf_fast(pdf_path: str) -> str:
    """
    快速PDF文本extract，优先速度
    """
    content = ""
    
    # method1: 使用pdfplumber (通常最快)
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    content += page_text + "\n"
        if content.strip():
            print(f"✅ pdfplumber快速extractsuccess: {len(content)}字符")
            return content
    except Exception as e:
        print(f"⚠️ pdfplumberextractfailed: {e}")
    
    # method2: 使用PyPDF2 (备选)
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                page_text = page.extract_text()
                if page_text:
                    content += page_text + "\n"
        if content.strip():
            print(f"✅ PyPDF2快速extractsuccess: {len(content)}字符")
            return content
    except Exception as e:
        print(f"⚠️ PyPDF2extractfailed: {e}")

def extract_content_with_multiple_methods(pdf_path: str) -> str:
    """
    使用多种methodextractPDF内容，包括process旋转页面
    
    Args:
        pdf_path (str): PDFfile path
        
    Returns:
        str: extract的text content
    """
    content = ""
    
    # method1: 使用pdfplumber，process旋转页面
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                # check页面旋转
                rotation = getattr(page, 'rotation', 0)
                if rotation:
                    print(f"检测到页面{i+1}旋转: {rotation}度")
                
                # 尝试原始extract
                text = page.extract_text()
                if text:
                    content += text + "\n"
                else:
                    # 如果原始extractfailed，尝试不同的parameter
                    try:
                        # 尝试不同的文本extractparameter
                        text = page.extract_text(
                            x_tolerance=3,
                            y_tolerance=3,
                            layout=True,
                            x_density=7.25,
                            y_density=13
                        )
                        if text:
                            content += text + "\n"
                            print(f"使用特殊parametersuccessextract页面{i+1}文本")
                    except Exception as e:
                        print(f"特殊parameterextractfailed: {e}")
                        
    except Exception as e:
        print(f"pdfplumberextractfailed: {e}")
    
    # method2: 使用PyPDF2
    if not content:
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for i, page in enumerate(reader.pages):
                    text = page.extract_text()
                    if text:
                        content += text + "\n"
                    else:
                        # 尝试不同的extractmethod
                        try:
                            # 尝试extract文本流
                            if hasattr(page, 'get_contents'):
                                contents = page.get_contents()
                                if contents:
                                    print(f"页面{i+1}包含内容流，但无法直接extract文本")
                        except Exception as e:
                            print(f"页面{i+1}内容流extractfailed: {e}")
        except Exception as e:
            print(f"PyPDF2extractfailed: {e}")
    
    # method3: 尝试快速OCR (如果安装了相关库)
    if not content:
        try:
            content = extract_text_with_ocr_fast(pdf_path)
        except Exception as e:
            print(f"快速OCRextractfailed: {e}")
    
    return content


def extract_case_data_from_pdf_with_llm(pdf_path: str, file_type: str, 
                                         parse_date_func, format_date_func, 
                                         calculate_due_date_func, format_date_only_func,
                                         get_location_from_slope_no_func) -> dict:
    """
    通用的PDF提取函数，使用OpenAI Vision API提取A-Q字段
    
    这个函数合并了RCC和TMO的共同处理逻辑，只保留必要的差异
    
    Args:
        pdf_path: PDF文件路径
        file_type: 文件类型 ("RCC" 或 "TMO")
        parse_date_func: 日期解析函数
        format_date_func: 日期格式化函数
        calculate_due_date_func: 计算截止日期函数
        format_date_only_func: 仅日期格式化函数
        get_location_from_slope_no_func: 从斜坡编号获取位置函数
        
    Returns:
        dict: 包含所有A-Q字段的字典
    """
    result = {}
    
    # 使用pdf2image将PDF转为图片，然后使用OpenAI Vision API提取字段
    try:
        from pdf2image import convert_from_path
        import tempfile
        import os
        from services.llm_service import get_llm_service
        
        print("📄 使用pdf2image将PDF转为图片...")
        # 将PDF转换为图片（处理所有页面）
        images = convert_from_path(pdf_path, dpi=200)
        
        if not images:
            print("⚠️ 无法将PDF转换为图片")
            return _get_empty_pdf_result()
        
        print(f"📄 PDF共有 {len(images)} 页，开始处理所有页面...")
        
        llm_service = get_llm_service()
        temp_image_paths = []
        
        try:
            # 处理第一页：提取主要字段（A-Q）
            print(f"🤖 处理第1页：使用OpenAI Vision API提取A-Q字段...")
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                temp_image_path = tmp_file.name
                temp_image_paths.append(temp_image_path)
                images[0].save(temp_image_path, 'PNG')
            
            extracted_data = llm_service.extract_fields_from_image(temp_image_path, file_type)
            
            if extracted_data:
                result = extracted_data
                print(f"✅ 成功从第1页提取 {len(result)} 个字段")
                
                # 如果有多个页面，处理其他页面以补充信息（特别是Q_case_details）
                if len(images) > 1:
                    print(f"📄 处理剩余 {len(images)-1} 页以补充信息...")
                    additional_details = []
                    
                    # 定义需要补充的字段（TMO多一个J_subject_matter / RCC的J_subject_matter由LLM自动生成）
                    supplement_fields = ['I_nature_of_request', 'Q_case_details']
                    if file_type == "TMO":
                        supplement_fields.append('J_subject_matter')
                    
                    for page_num in range(2, len(images) + 1):
                        try:
                            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                                page_image_path = tmp_file.name
                                temp_image_paths.append(page_image_path)
                                images[page_num - 1].save(page_image_path, 'PNG')
                            
                            # 从其他页面提取补充信息
                            print(f"🤖 处理第{page_num}页：提取补充信息...")
                            page_data = llm_service.extract_fields_from_image(page_image_path, file_type)
                            
                            if page_data:
                                # 合并补充信息到Q_case_details
                                if page_data.get('Q_case_details'):
                                    additional_details.append(f"第{page_num}页: {page_data['Q_case_details']}")
                                # 如果某些字段在第一页为空，尝试从其他页面补充
                                for key in supplement_fields:
                                    if not result.get(key) and page_data.get(key):
                                        result[key] = page_data[key]
                                        print(f"✅ 从第{page_num}页补充字段 {key}")
                        except Exception as e:
                            print(f"⚠️ 处理第{page_num}页时出错: {e}")
                            continue
                    
                    # 合并所有页面的详细信息
                    if additional_details:
                        original_q = result.get('Q_case_details', '')
                        combined_q = original_q
                        if original_q:
                            combined_q += "\n\n"
                        combined_q += "\n".join(additional_details)
                        result['Q_case_details'] = combined_q
                        print(f"✅ 已合并 {len(additional_details)} 页的补充信息")
                
                # 计算日期相关字段（如果A_date_received存在）
                if result.get('A_date_received'):
                    A_date = parse_date_func(result['A_date_received'])
                    if A_date:
                        # 重新格式化日期
                        result['A_date_received'] = format_date_func(A_date)
                        # 计算截止日期
                        result['K_10day_rule_due_date'] = calculate_due_date_func(A_date, 9)
                        if file_type != "RCC": result['L_icc_interim_due'] = calculate_due_date_func(A_date, 10)
                        if file_type != "RCC": result['M_icc_final_due'] = calculate_due_date_func(A_date, 21)
                        
                        # N: 工程完成截止日期 (取决于D)
                        days_map = {"Emergency": 1, "Urgent": 3, "General": 12}
                        result['N_works_completion_due'] = calculate_due_date_func(A_date, days_map.get(result.get('D_type', 'General'), 12))
                        
                        # O1: 发给承包商的传真日期
                        result['O1_fax_to_contractor'] = format_date_only_func(A_date)
                
                # P: 传真页数
                try:
                    import pdfplumber
                    with pdfplumber.open(pdf_path) as pdf:
                        result['P_fax_pages'] = str(len(pdf.pages))
                except:
                    result['P_fax_pages'] = "1"
                
                # H: 位置 (只要slope number存在，优先地址本地检索)
                if result.get('G_slope_no'):
                    if get_location_from_slope_no_func(result['G_slope_no']):
                        result['H_location'] = get_location_from_slope_no_func(result['G_slope_no'])
                
                return result
            else:
                print("⚠️ OpenAI Vision API未能从第1页提取字段，使用备用方法...")
        finally:
            # 清理所有临时文件
            for temp_path in temp_image_paths:
                try:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                except:
                    pass
                
    except ImportError:
        print("⚠️ pdf2image未安装，使用传统OCR方法...")
    except Exception as e:
        print(f"⚠️ pdf2image + Vision API方法失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 如果Vision API失败，返回空结果（调用者会使用备用方法）
    return None

def process_excel(excel_path: str) -> str:
    """
    Process Excel file for historical case RAG
    """
    try:
        excel_file = pd.ExcelFile(excel_path)
        content = ""
        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(excel_path,sheet_name=sheet_name).fillna("") 
            content += f"=== Sheet: {sheet_name} ===\n"
            # concat by row, a case for each row
            for index, row in df.iterrows():
                row_content = f"Case {index+1}: \n"
                for col in df.columns:
                    row_content += f"{col}: {row[col]}\n"
                content += row_content+"\n"
        return content
    except Exception as e:
        raise Exception(f"Failed to process Excel file: {e}")



def _get_empty_pdf_result() -> dict:
    """
    返回空的A-Q字段结果字典（用于PDF提取）
    
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
