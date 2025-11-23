# app/agents/lesion_localizer.py
"""病灶定位智能体"""

import json
import re
from typing import List, Dict, Any
from app.services.model_service import get_model_full_response, encode_image_to_base64

def get_welcome_message():
    """获取智能体欢迎语"""
    return "你好，我是病灶定位智能体。请上传眼科影像，我将为您自动识别并标注图中的可疑病灶区域。"

def get_agent_type():
    """获取智能体类型"""
    return "lesion_localizer"

def get_display_name():
    """获取智能体显示名称"""
    return "病灶定位"

def get_description():
    """获取智能体描述"""
    return "在用户上传的医学图像上用边界框标出检测到的病灶"

def get_system_prompt():
    """获取系统提示语"""
    return """你是一个顶级的眼科影像分析引擎，专门用于在眼科医学图像中精确定位和标注病灶区域。你的任务是：

1. 仔细分析用户上传的眼科影像（如眼底彩照、OCT扫描等）
2. 识别图像中的所有可疑病灶和异常区域
3. 为每个检测到的病灶提供精确的边界框坐标
4. 对每个病灶进行分类和置信度评估

请严格按照以下JSON格式输出结果，不要包含任何其他文本：

{
  "boxes": [
    {
      "label": "病灶类型名称",
      "coords": [x_min, y_min, x_max, y_max],
      "confidence": 0.95
    }
  ]
}

坐标说明：
- x_min, y_min: 边界框左上角坐标
- x_max, y_max: 边界框右下角坐标
- confidence: 置信度(0-1之间的浮点数)

只输出JSON对象，不要添加任何解释或其他文本。"""

def process_request(messages: List[Dict[str, Any]], uploaded_file_path: str) -> Dict:
    """
    处理病灶定位请求的核心逻辑。
    1. 构造包含系统提示和用户图片内容的请求。
    2. 调用模型服务，获取完整响应。
    3. 解析JSON，验证格式，并返回给API端点。
    """
    # 从 messages 中提取用户问题（如果有）
    user_prompt = "请分析这张图片中的病灶。"
    for msg in reversed(messages):
        if msg.get("role") == "user" and isinstance(msg.get("content"), str):
            user_prompt = msg["content"]
            break

    # 检查是否有上传文件
    if not uploaded_file_path:
        return {"type": "error", "payload": {"message": "病灶定位需要上传眼科影像。请先上传图片后再进行分析。"}}

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
            # 检查是否是Markdown代码块格式
            markdown_pattern = r'```(?:json)?\s*\n(.*?)\n```'
            markdown_match = re.search(markdown_pattern, full_response, re.DOTALL)
            
            if markdown_match:
                # 提取Markdown代码块中的JSON内容
                json_str = markdown_match.group(1).strip()
                print(f"[DEBUG] Extracted JSON from Markdown: {json_str[:200]}...")
                try:
                    parsed_data = json.loads(json_str)
                except json.JSONDecodeError:
                    # 如果代码块内容不是有效的JSON，尝试常规提取
                    print(f"[DEBUG] Markdown content is not valid JSON, trying regular extraction...")
                    raise
            else:
                # 如果不是Markdown，尝试直接提取JSON部分
                # 使用非贪婪模式可能会导致嵌套JSON解析不完整，这里使用更复杂但更准确的模式
                json_pattern = r'\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\}))*\}))*\}'
                json_match = re.search(json_pattern, full_response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    print(f"[DEBUG] Extracted JSON: {json_str[:200]}...")
                    parsed_data = json.loads(json_str)
                else:
                    # 如果没有找到JSON，创建一个错误响应
                    raise json.JSONDecodeError("No JSON found in response", full_response, 0)
        
        # 验证解析出的数据包含必需的boxes字段
        if "boxes" not in parsed_data:
            print(f"[WARNING] Parsed data missing 'boxes' field: {parsed_data}")
            # 尝试兼容不同的字段名称，如results, detections等
            for alt_field in ["results", "detections", "findings", "lesions"]:
                if alt_field in parsed_data and isinstance(parsed_data[alt_field], list):
                    parsed_data["boxes"] = parsed_data[alt_field]
                    break
        
        boxes = parsed_data.get("boxes", [])
        
        # 验证boxes数组中的每个元素格式
        valid_boxes = []
        for box in boxes:
            if not isinstance(box, dict):
                continue
                
            # 检查必需的字段
            if "coords" not in box or "label" not in box:
                continue
                
            # 确保coords是长度为4的数组
            if not isinstance(box["coords"], list) or len(box["coords"]) != 4:
                continue
                
            # 确保confidence存在且为数值
            if "confidence" not in box:
                box["confidence"] = 0.9  # 如果没有置信度，给一个默认值
                
            valid_boxes.append(box)
            
        print(f"[INFO] Successfully parsed {len(valid_boxes)} valid lesion boxes")
            
        return {
            "type": "final_structured_content",
            "payload": {
                "image_url": uploaded_file_path,
                "boxes": valid_boxes
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
