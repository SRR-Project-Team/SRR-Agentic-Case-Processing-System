"""
D_type fallback 规则（LLM 失败时使用）

当 LLM 提取失败时，根据关键词推断案件类型：Emergency / Urgent / General。
供 extractFromTxt、extractFromRCC、extractFromTMO 共用。
"""


def infer_d_type_from_content(content: str) -> str:
    """
    根据文本内容推断案件类型（传统规则备用）

    Args:
        content: 案件描述或全文内容

    Returns:
        "Emergency" | "Urgent" | "General"
    """
    if not content:
        return "General"
    text_lower = content.lower()
    if "emergency" in text_lower or "紧急" in content:
        return "Emergency"
    if "urgent" in text_lower:
        return "Urgent"
    return "General"
