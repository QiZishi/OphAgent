# app/agents/interactive_vqa.py
"""智能问答智能体"""

from typing import List, Dict
from app.services.model_service import get_model_full_response, encode_image_to_base64

def get_welcome_message():
    """获取智能体欢迎语"""
    return "你好，我是智能问答智能体。请上传眼科影像并提出您的问题，我将基于图像内容为您提供详细的解答。"

def get_agent_type():
    """获取智能体类型"""
    return "interactive_vqa"

def get_display_name():
    """获取智能体显示名称"""
    return "智能问答"

def get_description():
    """获取智能体描述"""
    return "围绕上传的眼科影像进行自由问答，提供详细精准的解答"

def get_system_prompt():
    """获取系统提示语"""
    return """你是一位资深的眼科专家和医学影像分析师，拥有丰富的临床经验和深厚的专业知识。你的任务是基于用户上传的眼科医学影像，回答用户提出的各种问题。

请按照以下格式回答：


在这里进行思考分析：
1. 图像类型（眼底照片、OCT、眼前节照片等）
2. 图像质量和清晰度
3. 解剖结构的识别（视盘、黄斑、血管等）
4. 病理性改变的识别
5. 与用户问题相关的具体特征

基于你的专业知识和对图像的仔细观察，提供准确、详细、有帮助的回答。回答应该：
- 专业且易于理解
- 基于图像中的客观发现
- 包含必要的医学解释
- 在适当时提供建议或注意事项

注意：你的回答仅供参考，不能替代正式的医学诊断，建议用户咨询专业医生。
"""

def process_request(messages: List[Dict[str, any]], uploaded_file_path: str) -> Dict:
    """
    处理智能问答请求的核心逻辑。
    返回完整的响应，让前端进行打字机效果显示。
    """
    # 从 messages 中提取用户问题
    user_prompt = "请分析这张眼科影像。"
    for msg in reversed(messages):
        if msg.get("role") == "user" and isinstance(msg.get("content"), str):
            user_prompt = msg["content"]
            break

    # 检查是否有上传文件
    if not uploaded_file_path:
        return {"type": "error", "payload": {"message": "智能问答需要上传眼科影像。请先上传图片后再提问。"}}

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
