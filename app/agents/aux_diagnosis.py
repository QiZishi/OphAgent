# app/agents/aux_diagnosis.py
"""辅助诊断智能体"""

import json
from typing import List, Dict
from app.services.model_service import get_model_full_response, encode_image_to_base64

def get_welcome_message():
    """获取智能体欢迎语"""
    return "你好，我是辅助诊断智能体。请上传眼科影像，我将为您提供多种可能的诊断结果、置信度及分析依据，以辅助您的临床决策。"

def get_agent_type():
    """获取智能体类型"""
    return "aux_diagnosis"

def get_display_name():
    """获取智能体显示名称"""
    return "辅助诊断"

def get_description():
    """获取智能体描述"""
    return "提供多种可能的疾病诊断，并附上置信度分数和分析依据"

def get_system_prompt():
    """获取系统提示语"""
    return """你是一位经验丰富的眼科诊断专家，拥有数十年的临床经验和深厚的专业知识。你的任务是分析用户上传的眼科医学影像，并提供专业的辅助诊断建议。

请仔细观察图像中的各种特征，包括但不限于：
- 视盘形态、大小、颜色
- 视网膜血管的形态、走向、口径
- 黄斑区域的结构和反光
- 视网膜各层结构的完整性
- 病理性改变如出血、渗出、新生血管等

基于你的观察和分析，请提供多个可能的诊断建议，并严格按照以下JSON格式输出：

{
  "diagnoses": [
    {
      "condition": "疾病名称",
      "confidence": 0.85,
      "reasoning": "详细的诊断依据和分析过程"
    }
  ]
}

要求：
1. 至少提供3-5个可能的诊断
2. 置信度为0-1之间的浮点数
3. 诊断依据要详细、专业、有说服力
4. 按置信度从高到低排序
5. 只输出JSON对象，不要添加任何其他文本"""

def process_request(messages: List[Dict[str, any]], uploaded_file_path: str) -> Dict:
    """
    处理辅助诊断请求的核心逻辑。
    与病灶定位类似，但解析不同的JSON结构。
    """
    # 从 messages 中提取用户问题（如果有）
    user_prompt = "请分析这张眼科影像并提供诊断建议。"
    for msg in reversed(messages):
        if msg.get("role") == "user" and isinstance(msg.get("content"), str):
            user_prompt = msg["content"]
            break

    # 检查是否有上传文件
    if not uploaded_file_path:
        return {"type": "error", "payload": {"message": "辅助诊断需要上传眼科影像。请先上传图片后再进行诊断。"}}

    # 编码图片为base64
    base64_image = encode_image_to_base64(uploaded_file_path)
    if not base64_image:
        return {"type": "error", "payload": {"message": "图片处理失败，请重新上传。"}}

    # 构造发送给模型的 messages 列表
    model_messages = [
        {"role": "system", "content": get_system_prompt()},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                },
            ],
        },
    ]

    # 获取完整响应
    full_response = get_model_full_response(model_messages)

    try:
        # 解析并验证模型输出
        print(f"[DEBUG] Trying to parse JSON from response: {full_response[:200]}...")
        
        # 尝试直接解析JSON
        try:
            parsed_data = json.loads(full_response)
        except json.JSONDecodeError:
            # 如果直接解析失败，尝试提取JSON部分
            import re
            json_match = re.search(r'\{.*\}', full_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                print(f"[DEBUG] Extracted JSON: {json_str[:200]}...")
                parsed_data = json.loads(json_str)
            else:
                # 如果没有找到JSON，创建一个错误响应
                raise json.JSONDecodeError("No JSON found in response", full_response, 0)
        
        return {
            "type": "final_structured_content",
            "payload": {
                "diagnoses": parsed_data.get("diagnoses", [])
            }
        }
    except (json.JSONDecodeError, KeyError) as e:
        # 如果模型返回格式错误，则返回错误信息
        print(f"[DEBUG] JSON parsing error: {e}")
        return {
            "type": "error",
            "payload": {
                "message": f"模型返回格式错误，期望JSON格式。实际返回: {full_response[:200]}..."
            }
        }
