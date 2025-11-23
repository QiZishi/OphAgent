# app/agents/knowledge_base.py
"""眼科知识库智能体"""

from typing import List, Dict
from app.services.model_service import get_model_full_response

def get_welcome_message():
    """获取智能体欢迎语"""
    return "你好，欢迎来到眼科知识库。您可以向我提问任何关于眼科学的医学知识、疾病定义、治疗方案等问题。"

def get_agent_type():
    """获取智能体类型"""
    return "knowledge_base"

def get_display_name():
    """获取智能体显示名称"""
    return "眼科知识库"

def get_description():
    """获取智能体描述"""
    return "一个纯文本问答功能，解答眼科领域的专业知识"

def get_system_prompt():
    """获取系统提示语"""
    return """你是一部权威的、动态更新的眼科医学百科全书，拥有最全面、最准确的眼科学知识。你可以回答关于眼科学的任何问题，包括但不限于：

- 眼部解剖结构和生理功能
- 各种眼科疾病的病因、病理、症状和体征
- 眼科检查方法和诊断技术
- 治疗方案和手术技术
- 眼科药物的作用机制和使用方法
- 眼科影像学解读
- 眼科急症处理
- 预防保健措施
- 最新的研究进展和治疗方法

请按照以下格式回答：

在回答问题时，请考虑：
1. 问题的具体内容和背景
2. 是否需要分步骤或分类别解答
3. 相关的医学概念和术语解释
4. 实际临床应用价值
5. 需要强调的重点或注意事项

请提供准确、详细、有条理的回答。你的回答应该：
- 基于循证医学和权威指南
- 逻辑清晰，条理分明
- 使用专业术语但确保可理解性
- 包含必要的背景知识和解释
- 在适当时提供实例或案例说明
- 强调重要的临床意义和注意事项

注意：所提供的信息仅供学习和参考，不能替代专业医疗建议。
"""

def process_request(messages: List[Dict[str, any]], uploaded_file_path: str = None) -> Dict:
    """
    处理知识库问答请求。
    注意：此函数故意忽略 uploaded_file_path 参数。
    """
    # 构造 model_messages 时，确保不包含任何 image_url 内容
    text_only_messages = []
    for msg in messages:
        if isinstance(msg.get("content"), str):
             text_only_messages.append({"role": msg["role"], "content": msg["content"]})

    # 在最前面插入系统提示
    text_only_messages.insert(0, {"role": "system", "content": get_system_prompt()})

    # 获取完整响应
    try:
        full_response = get_model_full_response(text_only_messages)
        
        # 解析thinking和answer内容
        thinking_content = ""
        answer_content = ""
        
        # 尝试提取<think>内容
        import re
        think_match = re.search(r"<think>(.*?)</think>", full_response, re.DOTALL)
        if think_match:
            thinking_content = think_match.group(1).strip()
        
        # 提取<answer>内容，或将无标签内容作为答案
        response_for_answer = re.sub(r"<think>.*?</think>", "", full_response, flags=re.DOTALL).strip()
        answer_match = re.search(r"<answer>(.*?)</answer>", response_for_answer, re.DOTALL)
        if answer_match:
            answer_content = answer_match.group(1).strip()
        else:
            answer_content = response_for_answer.replace("<answer>", "").replace("</answer>", "").strip()

        # 返回完整响应，让前端进行打字机效果
        return {
            "type": "complete_response",
            "payload": {
                "thinking_content": thinking_content,
                "answer_content": answer_content or full_response
            }
        }
    except Exception as e:
        return {"type": "error", "payload": {"message": f"调用模型服务时发生错误: {str(e)}"}}
