"""
输出module - processJSONformat和输出逻辑

本module负责将extract的data转换为结构化的JSON格式，包括：
- datamodel定义（StructuredCaseData、ProcessingResult）
- data转换和validate
- success/errorresultcreate
- fileclass型validate
- JSONformat输出

mainfunction：
1. 定义A-Qfield的datamodel
2. 将原始data转换为结构化object
3. createprocessresult（success/failed）
4. validatefileclass型和格式
5. formatJSON输出

作者: Project3 Team
版本: 1.0
"""
from pydantic import BaseModel
from typing import Optional, Dict, Any


class StructuredCaseData(BaseModel):
    """
    结构化datamodel：严格对应新定义的A-Qfield
    
    按照SRR案件process规则定义的18个field，每个field都有默认值，
    确保JSON输出时所有键都存在，避免缺失field的问题。
    
    Attributes:
        A_date_received (str): 案件接收日期（AIMS生成）
        B_source (str): 来源（Web/RCC/ICC/1823等）
        C_1823_case_no (str): 1823案件号（仅RCC/ICC来源）
        D_type (str): 案件class型（Emergency/Urgent/General）
        E_caller_name (str): 来电人姓名
        F_contact_no (str): 联系电话
        G_slope_no (str): 斜坡编号
        H_location (str): 位置（从Exceldata获取）
        I_nature_of_request (str): 请求性质摘要
        J_subject_matter (str): 事项主题
        K_10day_rule_due_date (str): 10天规则截止日期
        L_icc_interim_due (str): ICC临时回复截止日期
        M_icc_final_due (str): ICC最终回复截止日期
        N_works_completion_due (str): 工程完成截止日期
        O1_fax_to_contractor (str): 发给承包商的传真日期
        O2_email_send_time (str): 邮件发送时间
        P_fax_pages (str): 传真页数（含附件）
        Q_case_details (str): 案件详情（带建议截止日期）
    """
    # A-Qfield按新规则定义，确保所有key始终存在（缺失时为空）
    A_date_received: str = ""                  # A: 案件接收日期（AIMS生成）
    B_source: str = ""                         # B: 来源（与Step 1相同）
    C_case_number: str = ""                    # C: 案件编号
    D_type: str = ""                           # D: 案件class型（根据历史record和规则classify）
    E_caller_name: str = ""                    # E: 来电人姓名（取决于B）
    F_contact_no: str = ""                     # F: 联系电话（取决于B）
    G_slope_no: str = ""                       # G: 斜坡编号（参考邮件）
    H_location: str = ""                       # H: 位置（根据G从slope data.xlsx获取）
    I_nature_of_request: str = ""              # I: 请求性质（从邮件/PDF生成摘要）
    J_subject_matter: str = ""                 # J: 事项主题（根据历史record和规则classify）
    K_10day_rule_due_date: str = ""            # K: 10天规则截止日期（A+10天）
    L_icc_interim_due: str = ""                # L: ICC临时回复截止日期（10日历日内）
    M_icc_final_due: str = ""                  # M: ICC最终回复截止日期（21日历日内）
    N_works_completion_due: str = ""           # N: 工程完成截止日期（取决于D）
    O1_fax_to_contractor: str = ""             # O1: 发给承包商的传真日期（通常同A）
    O2_email_send_time: str = ""               # O2: 邮件发送时间
    P_fax_pages: str = ""                      # P: 传真页数（含附件）
    Q_case_details: str = ""                   # Q: 案件详情（带建议截止日期）


class ProcessingResult(BaseModel):
    """
    processresultmodel
    
    用于封装APIprocessresult，包含文件名、状态、消息和结构化data
    
    Attributes:
        filename (str): process的文件名
        status (str): process状态（"success" 或 "error"）
        message (str): 状态消息
        structured_data (Optional[StructuredCaseData]): 结构化data（success时）
        case_id (Optional[int]): 案件ID（保存到数据库后）
    """
    filename: str
    status: str
    message: str
    structured_data: Optional[StructuredCaseData] = None
    case_id: Optional[int] = None
    summary: Optional[Dict[str, Any]] = None
    raw_content: Optional[str] = None
    similar_cases: Optional[list] = None  # 相似歷史案件

def create_structured_data(extracted_data: Dict[str, Any]) -> StructuredCaseData:
    """
    将extract的data转换为StructuredCaseDataobject
    
    将extractFromTxtmoduleextract的原始字典data转换为结构化的Pydanticmodel，
    确保所有A-Qfield都有值（缺失时使用空字符串）
    
    Args:
        extracted_data (Dict[str, Any]): 从extractFromTxt.pyextract的原始data字典
        
    Returns:
        StructuredCaseData: 结构化的案件dataobject
        
    Example:
        >>> data = {"A_date_received": "2024-01-15", "B_source": "Web"}
        >>> result = create_structured_data(data)
        >>> result.A_date_received
        "2024-01-15"
    """
    return StructuredCaseData(
        A_date_received=extracted_data.get('A_date_received', ''),
        B_source=extracted_data.get('B_source', ''),
        C_case_number=extracted_data.get('C_case_number', ''),
        D_type=extracted_data.get('D_type', ''),
        E_caller_name=extracted_data.get('E_caller_name', ''),
        F_contact_no=extracted_data.get('F_contact_no', ''),
        G_slope_no=extracted_data.get('G_slope_no', ''),
        H_location=extracted_data.get('H_location', ''),
        I_nature_of_request=extracted_data.get('I_nature_of_request', ''),
        J_subject_matter=extracted_data.get('J_subject_matter', ''),
        K_10day_rule_due_date=extracted_data.get('K_10day_rule_due_date', ''),
        L_icc_interim_due=extracted_data.get('L_icc_interim_due', ''),
        M_icc_final_due=extracted_data.get('M_icc_final_due', ''),
        N_works_completion_due=extracted_data.get('N_works_completion_due', ''),
        O1_fax_to_contractor=extracted_data.get('O1_fax_to_contractor', ''),
        O2_email_send_time=extracted_data.get('O2_email_send_time', ''),
        P_fax_pages=extracted_data.get('P_fax_pages', ''),
        Q_case_details=extracted_data.get('Q_case_details', '')
    )


def create_success_result(filename: str, 
                          structured_data: StructuredCaseData, 
                          summary: Optional[Dict[str, Any]] = None,
                          raw_content: Optional[str] = None,
                          case_id: Optional[int] = None,
                          similar_cases: Optional[list] = None
                         ) -> ProcessingResult:
    """
    创建successprocess的resultobject
    
    当文件processsuccess时，创建包含结构化data的successresultobject
    
    Args:
        filename (str): process的文件名
        structured_data (StructuredCaseData): 结构化的案件data
        summary (Optional[Dict[str, Any]]): 可选的summarizedata
        raw_content (Optional[str]): 原始文件内容
        case_id (Optional[int]): 案件ID
        
    Returns:
        ProcessingResult: successprocess的resultobject
        
    Example:
        >>> data = StructuredCaseData(A_date_received="2024-01-15")
        >>> result = create_success_result("test.txt", data, case_id=123)
        >>> result.status
        "success"
    """
    return ProcessingResult(
        filename=filename,
        status="success",
        message="SRR案件processsuccess",
        structured_data=structured_data,
        summary=summary,
        raw_content=raw_content,
        case_id=case_id,
        similar_cases=similar_cases
    )


def create_error_result(filename: str, error_message: str) -> ProcessingResult:
    """
    创建errorprocess的resultobject
    
    当文件processfailed时，创建包含errorinformation的resultobject
    
    Args:
        filename (str): process的文件名
        error_message (str): errorinformation描述
        
    Returns:
        ProcessingResult: errorprocess的resultobject
        
    Example:
        >>> result = create_error_result("test.txt", "文件格式不支持")
        >>> result.status
        "error"
    """
    return ProcessingResult(
        filename=filename,
        status="error",
        message=error_message,
        structured_data=None
    )


def format_json_output(processing_result: ProcessingResult) -> Dict[str, Any]:
    """
    将processresult格式化为JSON输出格式
    
    将ProcessingResultobject转换为字典格式，便于JSON序列化
    success时包含structured_data，failed时不包含
    
    Args:
        processing_result (ProcessingResult): processresultobject
        
    Returns:
        Dict[str, Any]: 格式化的JSON输出字典
        
    Example:
        >>> result = ProcessingResult(filename="test.txt", status="success", ...)
        >>> json_output = format_json_output(result)
        >>> json_output["filename"]
        "test.txt"
    """
    result_dict = {
        "filename": processing_result.filename,
        "status": processing_result.status,
        "message": processing_result.message
    }
    
    if processing_result.structured_data:
        result_dict["structured_data"] = processing_result.structured_data.dict()
    
    return result_dict


def validate_file_type(content_type: str) -> bool:
    """
    validate文件class型是否为支持的格式
    
    check上传文件的MIMEclass型是否为text/plain（TXT文件）
    
    Args:
        content_type (str): 文件的MIMEclass型
        
    Returns:
        bool: 是否为支持的文件class型
        
    Example:
        >>> validate_file_type("text/plain")
        True
        >>> validate_file_type("application/pdf")
        False
    """
    return content_type == "text/plain"


def get_file_type_error_message() -> str:
    """
    获取文件class型errorinformation
    
    return标准的文件class型error消息，用于用户友好的error提示
    
    Returns:
        str: 文件class型errorinformation
        
    Example:
        >>> get_file_type_error_message()
        "仅支持TXT文件格式"
    """
    return "仅支持TXT文件格式"
