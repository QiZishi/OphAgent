# app/services/model_service.py
import openai
import re
import base64
from typing import Generator, List, Dict
from app.core.config import settings

# 初始化可复用的OpenAI客户端（改为同步）
print(f"[DEBUG] Initializing OpenAI client...")
print(f"[DEBUG] API Base: {settings.OPENAI_API_BASE}")
print(f"[DEBUG] API Key: {settings.OPENAI_API_KEY[:10]}...{settings.OPENAI_API_KEY[-4:]}")

client = openai.OpenAI(
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.OPENAI_API_BASE,
)
print(f"[DEBUG] OpenAI client initialized successfully")

# 定义解析状态
class ParseState:
    IDLE = 0
    THINKING = 1
    ANSWERING = 2

def encode_image_to_base64(image_path: str) -> str:
    """将图片文件编码为base64字符串"""
    if not image_path:
        print("[DEBUG] encode_image_to_base64: image_path is None or empty")
        return ""
    
    try:
        print(f"[DEBUG] encode_image_to_base64: Processing {image_path}")
        
        # 如果是URL路径（以/static/开头），转换为实际文件系统路径
        if image_path.startswith('/static/'):
            # 移除前缀 '/static/' 并添加 'app/static/'
            actual_path = 'app' + image_path
        else:
            actual_path = image_path
            
        print(f"[DEBUG] encode_image_to_base64: Actual file path: {actual_path}")
        
        with open(actual_path, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode('utf-8')
            print(f"[DEBUG] encode_image_to_base64: Successfully encoded, length: {len(encoded)}")
            return encoded
    except Exception as e:
        print(f"[DEBUG] Error encoding image to base64: {e}")
        return ""

def get_model_full_response(messages: List[Dict[str, any]]) -> str:
    """
    调用模型并返回完整的响应内容（非流式）。
    主要用于需要JSON格式输出的智能体。
    """
    print(f"[DEBUG] get_model_full_response called with {len(messages)} messages")
    print(f"[DEBUG] Model: {settings.MODEL_NAME}")
    print(f"[DEBUG] API Base: {settings.OPENAI_API_BASE}")
    print(f"[DEBUG] Temperature: {settings.TEMPERATURE}")
    
    # 打印前几条消息内容（避免过长）
    for i, msg in enumerate(messages[:3]):
        content = msg.get('content', '')
        if isinstance(content, str):
            content_preview = content[:200] + '...' if len(content) > 200 else content
        else:
            content_preview = f"[Complex content with {len(content)} items]" if isinstance(content, list) else str(content)
        print(f"[DEBUG] Message {i}: role={msg.get('role')}, content={content_preview}")
    
    try:
        print(f"[DEBUG] Sending request to OpenAI API...")
        response = client.chat.completions.create(
            model=settings.MODEL_NAME,
            messages=messages,
            temperature=settings.TEMPERATURE,
            stream=False,
        )
        print(f"[DEBUG] API call successful, response received")
        
        if response.choices and len(response.choices) > 0:
            content = response.choices[0].message.content
            print(f"[DEBUG] Response content length: {len(content) if content else 0}")
            print(f"[DEBUG] Response preview: {content[:200] + '...' if content and len(content) > 200 else content}")
            return content
        else:
            print(f"[DEBUG] ERROR: No choices in response")
            return "模型响应格式异常，请稍后重试。"
            
    except Exception as e:
        print(f"[DEBUG] ERROR calling model API: {type(e).__name__}: {e}")
        import traceback
        print(f"[DEBUG] Full traceback: {traceback.format_exc()}")
        return "调用模型服务时发生错误，请稍后重试。"

def get_model_response_stream(
    messages: List[Dict[str, any]]
) -> Generator[Dict[str, str], None, None]:
    """
    调用模型，获取完整响应，然后分割并返回用于前端打字机效果的数据块。
    这种方法先收集完整内容，然后进行伪流式输出。
      
    Yields:
        A dictionary with "type" and "content",   
        e.g., {"type": "thinking_chunk", "content": "..."}
              {"type": "answer_chunk", "content": "..."}
              {"type": "error", "content": "..."}
    """
    try:
        # 1. 获取完整的模型响应（同步方式）
        response = client.chat.completions.create(
            model=settings.MODEL_NAME,
            messages=messages,
            temperature=settings.TEMPERATURE,
            stream=False,  # 改为非流式，先获取完整内容
        )
        
        full_response = response.choices[0].message.content or ""
        
        # 2. 解析完整响应
        think_content = ""
        answer_content = ""

        # 尝试提取<think>内容
        think_match = re.search(r"<think>(.*?)</think>", full_response, re.DOTALL)
        if think_match:
            think_content = think_match.group(1).strip()
        
        # 提取<answer>内容，或将无标签内容作为答案
        # 先移除<think>部分，避免干扰
        response_for_answer = re.sub(r"<think>.*?</think>", "", full_response, flags=re.DOTALL).strip()
        answer_match = re.search(r"<answer>(.*?)</answer>", response_for_answer, re.DOTALL)
        if answer_match:
            answer_content = answer_match.group(1).strip()
        else:
            # 如果没有<answer>标签，则将剩余的所有内容视为答案
            answer_content = response_for_answer.replace("<answer>", "").replace("</answer>", "").strip()

        # 3. 返回完整的内容块（让前端进行伪流式显示）
        if think_content:
            yield {"type": "thinking_chunk", "content": think_content}
        
        if answer_content:
            yield {"type": "answer_chunk", "content": answer_content}
        
        if not think_content and not answer_content and full_response:
            # 如果模型没有返回任何有效内容（或没有按预期格式返回），则返回原始响应
            yield {"type": "answer_chunk", "content": full_response}
        
        # 4. 发送完成信号
        yield {"type": "message_complete", "content": ""}

    except Exception as e:
        # 统一错误处理
        print(f"Error calling model API: {e}")
        yield {"type": "error", "content": f"调用模型服务时发生错误: {e}"}
