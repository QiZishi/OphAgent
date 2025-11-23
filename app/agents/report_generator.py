# app/agents/report_generator.py
"""报告生成智能体"""

from typing import List, Dict
from app.services.model_service import get_model_full_response, encode_image_to_base64

def get_welcome_message():
    """获取智能体欢迎语"""
    return "你好，我是报告生成智能体。请上传所需的影像资料，并可选择性地提供患者信息和初步发现，我将为您自动生成一份结构化的诊断报告初稿。"

def get_agent_type():
    """获取智能体类型"""
    return "report_generator"

def get_display_name():
    """获取智能体显示名称"""
    return "报告生成"

def get_description():
    """获取智能体描述"""
    return "根据用户提供的资料，生成一份完整的、分章节的结构化诊断报告"

def get_system_prompt():
    """获取系统提示语"""
    return """你是一名专业的医疗报告撰写员，具有丰富的眼科诊断报告写作经验。请基于用户上传的眼科影像和提供的信息，生成一份符合医疗规范的结构化诊断报告。
分析影像时，请考虑以下要素：
1. 影像类型和质量评估
2. 解剖结构的观察和描述
3. 病理性改变的识别和分析
4. 与临床症状的关联性
5. 诊断建议和进一步检查建议

请按照以下结构生成医疗报告（使用Markdown格式）：

# 眼科影像诊断报告

## 基本信息
- **检查日期**: [当前日期]
- **影像类型**: [检查类型]
- **影像质量**: [质量评估]

## 影像所见

### 视盘
[描述视盘的形态、大小、颜色、杯盘比等]

### 视网膜血管
[描述动静脉血管的走向、口径、反光等]

### 黄斑区
[描述黄斑的形态、反光、结构等]

### 视网膜其他区域
[描述周边视网膜的情况]

## 影像诊断
[基于影像所见提出的诊断意见]

## 建议
[进一步检查和治疗建议]

## 注意事项
本报告仅供参考，最终诊断请结合临床症状和其他检查结果，并咨询专业医生意见。


请确保报告内容专业、客观、严谨。"""

def process_request(messages: List[Dict[str, any]], uploaded_file_path: str) -> Dict:
    """
    处理报告生成请求的核心逻辑。
    返回完整的响应，让前端进行打字机效果显示。
    """
    # 从 messages 中提取用户问题
    user_prompt = "请基于这张眼科影像生成诊断报告。"
    for msg in reversed(messages):
        if msg.get("role") == "user" and isinstance(msg.get("content"), str):
            user_prompt = msg["content"]
            break

    # 检查是否有上传文件
    if not uploaded_file_path:
        return {"type": "error", "payload": {"message": "报告生成需要上传眼科影像。请先上传图片后再生成报告。"}}

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
    try:
        full_response = get_model_full_response(model_messages)
        
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
