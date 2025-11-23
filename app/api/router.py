# app/api/router.py
import json
import inspect
from typing import List, Optional
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
from sqlmodel import Session
from app.db.database import get_session
from app.db.models import User
from app.db.crud import (
    create_conversation, get_user_conversations, get_conversation_by_id,
    get_conversation_messages, update_conversation_title, delete_conversation
)
from app.auth.security import get_current_user
from app.auth.schemas import UserResponse
from app.services.chat_service import connection_manager
from app.services.file_service import process_uploaded_file
from pydantic import BaseModel

# 导入所有智能体处理模块
from app.agents import interactive_vqa, lesion_localizer, aux_diagnosis, report_generator, knowledge_base

router = APIRouter()

# 将智能体名称映射到其处理函数
agent_processors = {
    "interactive_vqa": interactive_vqa.process_request,
    "lesion_localizer": lesion_localizer.process_request,
    "aux_diagnosis": aux_diagnosis.process_request,
    "report_generator": report_generator.process_request,
    "knowledge_base": knowledge_base.process_request,
}

# Pydantic模型
class ConversationCreate(BaseModel):
    title: str
    agent_type: str

class ConversationUpdate(BaseModel):
    title: str

class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    thinking_content: Optional[str] = None
    thinking_time_s: Optional[float] = None
    created_at: str
    attachments: List[dict] = []

class ConversationResponse(BaseModel):
    id: int
    title: str
    agent_type: str
    created_at: str
    messages: List[MessageResponse] = []

# 消息处理API（替换WebSocket）
@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: int,
    message: str = Form(...),
    files: List[UploadFile] = File(default=[]),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """发送消息到指定对话"""
    print(f"[DEBUG] Send message API called - conversation_id: {conversation_id}")
    print(f"[DEBUG] Message: {message[:200]}...")
    print(f"[DEBUG] Files count: {len(files)}")
    
    # 验证对话存在且属于当前用户
    conversation = get_conversation_by_id(session, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # 处理上传的文件
    file_path = None
    if files and len(files) > 0 and files[0].filename:
        file_path = await process_uploaded_file(files[0], current_user.id)
        print(f"[DEBUG] File uploaded to: {file_path}")
    
    try:
        # 获取对话历史
        messages = get_conversation_messages(session, conversation_id)
        history = []
        
        for msg in messages:
            history.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # 添加当前用户消息
        history.append({
            "role": "user",
            "content": message
        })
        
        print(f"[DEBUG] History length: {len(history)}")
        
        # 根据对话的agent_type选择处理器
        processor = agent_processors.get(conversation.agent_type)
        if not processor:
            raise HTTPException(status_code=400, detail="Unknown agent type")
        
        print(f"[DEBUG] Using processor for agent_type: {conversation.agent_type}")
        
        # 调用处理器
        response = processor(messages=history, uploaded_file_path=file_path)
        print(f"[DEBUG] Processor response: {str(response)[:200]}...")
        
        # 保存用户消息到数据库
        from app.db.models import Message, Attachment
        user_message = Message(
            conversation_id=conversation_id,
            role="user",
            content=message,
            file_path=file_path
        )
        session.add(user_message)
        session.commit()
        session.refresh(user_message)
        print(f"[DEBUG] User message saved with ID: {user_message.id}")
        
        # 如果有文件，创建附件记录
        if file_path:
            attachment = Attachment(
                message_id=user_message.id,
                file_path=file_path,
                original_filename=files[0].filename
            )
            session.add(attachment)
            session.commit()
            session.refresh(attachment)
            print(f"[DEBUG] Attachment saved with ID: {attachment.id}")
        
        # 保存AI响应到数据库
        if response.get("type") == "complete_response":
            payload = response.get("payload", {})
            assistant_message = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=payload.get("answer_content", ""),
                thinking_content=payload.get("thinking_content", ""),
                thinking_time_s=payload.get("thinking_time_s", 0.0)
            )
        else:
            # 处理其他响应格式
            assistant_message = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=response.get("answer_content", response.get("content", "")),
                thinking_content=response.get("thinking_content", ""),
                thinking_time_s=response.get("thinking_time_s", 0.0)
            )
        
        session.add(assistant_message)
        session.commit()
        session.refresh(assistant_message)
        print(f"[DEBUG] Assistant message saved with ID: {assistant_message.id}")
        
        # 在响应中添加消息ID信息
        if isinstance(response, dict):
            response["message_id"] = assistant_message.id
            if response.get("type") == "complete_response" and "payload" in response:
                response["payload"]["message_id"] = assistant_message.id
        
        return response
        
    except Exception as e:
        print(f"[DEBUG] Error in send_message: {type(e).__name__}: {e}")
        import traceback
        print(f"[DEBUG] Traceback: {traceback.format_exc()}")
        # 回滚事务
        session.rollback()
        raise HTTPException(status_code=500, detail=f"处理消息时发生错误: {str(e)}")

# 重新生成消息API
@router.post("/conversations/{conversation_id}/messages/{message_id}/regenerate")
async def regenerate_message(
    conversation_id: int,
    message_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """重新生成指定的助手消息"""
    print(f"[DEBUG] Regenerate message API called - conversation_id: {conversation_id}, message_id: {message_id}")
    
    # 验证对话存在且属于当前用户
    conversation = get_conversation_by_id(session, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # 获取要重新生成的助手消息
    from app.db.models import Message
    assistant_message = session.get(Message, message_id)
    if not assistant_message or assistant_message.conversation_id != conversation_id:
        raise HTTPException(status_code=404, detail="Message not found")
    
    if assistant_message.role != "assistant":
        raise HTTPException(status_code=400, detail="Only assistant messages can be regenerated")
    
    # 找到对应的用户消息（通常是前一条消息）
    user_message = None
    all_messages = get_conversation_messages(session, conversation_id)
    
    for i, msg in enumerate(all_messages):
        if msg.id == message_id and i > 0:
            user_message = all_messages[i - 1]
            break
    
    if not user_message or user_message.role != "user":
        raise HTTPException(status_code=400, detail="Cannot find corresponding user message")
    
    print(f"[DEBUG] Found user message: {user_message.id}")
    print(f"[DEBUG] User message content: {user_message.content[:200]}...")
    print(f"[DEBUG] User message attachments count: {len(user_message.attachments) if user_message.attachments else 0}")
    
    try:
        # 获取对话历史（直到用户消息为止）
        history = []
        for msg in all_messages:
            if msg.id == user_message.id:
                break
            history.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # 添加当前用户消息
        history.append({
            "role": "user", 
            "content": user_message.content
        })
        
        print(f"[DEBUG] History length: {len(history)}")
        
        # 确定文件路径（从用户消息的附件或file_path字段）
        file_path = None
        if user_message.attachments and len(user_message.attachments) > 0:
            file_path = user_message.attachments[0].file_path
            print(f"[DEBUG] Using file from attachments: {file_path}")
        elif user_message.file_path:
            file_path = user_message.file_path
            print(f"[DEBUG] Using file from message file_path: {file_path}")
        
        # 根据对话的agent_type选择处理器
        processor = agent_processors.get(conversation.agent_type)
        if not processor:
            raise HTTPException(status_code=400, detail="Unknown agent type")
        
        print(f"[DEBUG] Using processor for agent_type: {conversation.agent_type}")
        print(f"[DEBUG] File path: {file_path}")
        
        # 调用处理器
        response = processor(messages=history, uploaded_file_path=file_path)
        print(f"[DEBUG] Processor response: {str(response)[:200]}...")
        
        # 更新现有的助手消息内容
        if response.get("type") == "complete_response":
            payload = response.get("payload", {})
            assistant_message.content = payload.get("answer_content", "")
            assistant_message.thinking_content = payload.get("thinking_content", "")
            assistant_message.thinking_time_s = payload.get("thinking_time_s", 0.0)
        else:
            # 处理其他响应格式
            assistant_message.content = response.get("answer_content", response.get("content", ""))
            assistant_message.thinking_content = response.get("thinking_content", "")
            assistant_message.thinking_time_s = response.get("thinking_time_s", 0.0)
        
        session.add(assistant_message)
        session.commit()
        session.refresh(assistant_message)
        print(f"[DEBUG] Assistant message updated with ID: {assistant_message.id}")
        
        return response
        
    except Exception as e:
        print(f"[DEBUG] Error in regenerate_message: {type(e).__name__}: {e}")
        import traceback
        print(f"[DEBUG] Traceback: {traceback.format_exc()}")
        # 回滚事务
        session.rollback()
        raise HTTPException(status_code=500, detail=f"重新生成消息时发生错误: {str(e)}")

# WebSocket端点
@router.websocket("/ws/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: int):
    """WebSocket聊天端点"""
    print(f"[DEBUG] WebSocket connection established for conversation {conversation_id}")
    await connection_manager.connect(websocket, conversation_id)
    try:
        while True:
            data = await websocket.receive_text()
            print(f"[DEBUG] Received WebSocket message: {data[:200]}...")
            
            # 1. 解析前端发来的消息
            # 消息格式: {"agent_type": "...", "history": [...], "file_path": "..."}
            try:
                request_data = json.loads(data)
                agent_type = request_data.get("agent_type")
                history = request_data.get("history", [])
                file_path = request_data.get("file_path")  # 文件已在HTTP端点上传并保存
                
                print(f"[DEBUG] Parsed request - agent_type: {agent_type}, history length: {len(history)}, file_path: {file_path}")
            except json.JSONDecodeError as e:
                print(f"[DEBUG] JSON decode error: {e}")
                error_msg = json.dumps({"type": "error", "payload": {"message": "消息格式错误"}})
                await connection_manager.send_personal_message(error_msg, websocket)
                continue

            # 2. 根据 agent_type 选择处理器
            processor = agent_processors.get(agent_type)
            if not processor:
                print(f"[DEBUG] Unknown agent type: {agent_type}")
                error_msg = json.dumps({"type": "error", "payload": {"message": "未知的智能体类型"}})
                await connection_manager.send_personal_message(error_msg, websocket)
                continue

            print(f"[DEBUG] Found processor for agent_type: {agent_type}")
            
            # 3. 调用处理器并返回结果
            # 所有处理器现在都是同步函数，返回完整的响应
            try:
                print(f"[DEBUG] Calling processor...")
                response = processor(messages=history, uploaded_file_path=file_path)
                print(f"[DEBUG] Processor returned response: {str(response)[:200]}...")
                await connection_manager.send_personal_message(json.dumps(response), websocket)
                print(f"[DEBUG] Response sent to WebSocket")
            except Exception as proc_e:
                print(f"[DEBUG] Error in processor: {type(proc_e).__name__}: {proc_e}")
                import traceback
                print(f"[DEBUG] Processor traceback: {traceback.format_exc()}")
                error_msg = json.dumps({"type": "error", "payload": {"message": f"处理器错误: {str(proc_e)}"}})
                await connection_manager.send_personal_message(error_msg, websocket)

            # 4. 发送流结束信号
            completion_signal = json.dumps({"type": "status_update", "payload": {"status": "complete"}})
            await connection_manager.send_personal_message(completion_signal, websocket)

    except WebSocketDisconnect:
        connection_manager.disconnect(conversation_id)
    except Exception as e:
        # 统一异常处理
        error_msg = json.dumps({"type": "error", "payload": {"message": f"服务器内部错误: {str(e)}"}})
        await connection_manager.send_personal_message(error_msg, websocket)
        connection_manager.disconnect(conversation_id)

# 用户信息端点
@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    """获取当前用户信息"""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        created_at=current_user.created_at.isoformat()
    )

# 对话管理API
@router.post("/conversations", response_model=ConversationResponse)
async def create_new_conversation(
    conversation_data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """创建新对话"""
    conversation = create_conversation(
        session, 
        conversation_data.title, 
        current_user.id, 
        conversation_data.agent_type
    )
    
    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        agent_type=conversation.agent_type,
        created_at=conversation.created_at.isoformat(),
        messages=[]
    )

@router.get("/conversations", response_model=List[ConversationResponse])
async def get_conversations(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """获取用户的所有对话"""
    conversations = get_user_conversations(session, current_user.id)
    
    result = []
    for conv in conversations:
        messages = get_conversation_messages(session, conv.id)
        message_responses = []
        
        for msg in messages:
            attachments = []
            if msg.attachments:
                attachments = [
                    {
                        "file_path": att.file_path,
                        "original_filename": att.original_filename
                    }
                    for att in msg.attachments
                ]
            
            message_responses.append(MessageResponse(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                thinking_content=msg.thinking_content,
                thinking_time_s=msg.thinking_time_s,
                created_at=msg.created_at.isoformat(),
                attachments=attachments
            ))
        
        result.append(ConversationResponse(
            id=conv.id,
            title=conv.title,
            agent_type=conv.agent_type,
            created_at=conv.created_at.isoformat(),
            messages=message_responses
        ))
    
    return result

@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """获取特定对话"""
    conversation = get_conversation_by_id(session, conversation_id)
    
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    messages = get_conversation_messages(session, conversation_id)
    message_responses = []
    
    for msg in messages:
        attachments = []
        if msg.attachments:
            attachments = [
                {
                    "file_path": att.file_path,
                    "original_filename": att.original_filename
                }
                for att in msg.attachments
            ]
        
        message_responses.append(MessageResponse(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            thinking_content=msg.thinking_content,
            thinking_time_s=msg.thinking_time_s,
            created_at=msg.created_at.isoformat(),
            attachments=attachments
        ))
    
    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        agent_type=conversation.agent_type,
        created_at=conversation.created_at.isoformat(),
        messages=message_responses
    )

@router.put("/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: int,
    conversation_data: ConversationUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """更新对话标题"""
    conversation = get_conversation_by_id(session, conversation_id)
    
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    updated_conversation = update_conversation_title(session, conversation_id, conversation_data.title)
    
    messages = get_conversation_messages(session, conversation_id)
    message_responses = []
    
    for msg in messages:
        attachments = []
        if msg.attachments:
            attachments = [
                {
                    "file_path": att.file_path,
                    "original_filename": att.original_filename
                }
                for att in msg.attachments
            ]
        
        message_responses.append(MessageResponse(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            thinking_content=msg.thinking_content,
            thinking_time_s=msg.thinking_time_s,
            created_at=msg.created_at.isoformat(),
            attachments=attachments
        ))
    
    return ConversationResponse(
        id=updated_conversation.id,
        title=updated_conversation.title,
        agent_type=updated_conversation.agent_type,
        created_at=updated_conversation.created_at.isoformat(),
        messages=message_responses
    )

@router.delete("/conversations/{conversation_id}")
async def delete_conversation_endpoint(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """删除对话"""
    conversation = get_conversation_by_id(session, conversation_id)
    
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    success = delete_conversation(session, conversation_id)
    
    if success:
        return {"message": "Conversation deleted successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to delete conversation")

# 文件上传API
@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """上传文件"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected")
    
    file_path = await process_uploaded_file(file, current_user.id)
    
    if file_path:
        return {"file_path": file_path, "filename": file.filename}
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type or processing failed")

# 获取智能体信息API
@router.get("/agents")
async def get_agents():
    """获取所有智能体信息"""
    from app.agents import (
        interactive_vqa, lesion_localizer, aux_diagnosis, 
        report_generator, knowledge_base
    )
    
    agents = [
        {
            "type": interactive_vqa.get_agent_type(),
            "name": interactive_vqa.get_display_name(),
            "description": interactive_vqa.get_description(),
            "welcome_message": interactive_vqa.get_welcome_message(),
            "icon": "💬"
        },
        {
            "type": lesion_localizer.get_agent_type(),
            "name": lesion_localizer.get_display_name(),
            "description": lesion_localizer.get_description(),
            "welcome_message": lesion_localizer.get_welcome_message(),
            "icon": "🎯"
        },
        {
            "type": aux_diagnosis.get_agent_type(),
            "name": aux_diagnosis.get_display_name(),
            "description": aux_diagnosis.get_description(),
            "welcome_message": aux_diagnosis.get_welcome_message(),
            "icon": "🩺"
        },
        {
            "type": report_generator.get_agent_type(),
            "name": report_generator.get_display_name(),
            "description": report_generator.get_description(),
            "welcome_message": report_generator.get_welcome_message(),
            "icon": "📄"
        },
        {
            "type": knowledge_base.get_agent_type(),
            "name": knowledge_base.get_display_name(),
            "description": knowledge_base.get_description(),
            "welcome_message": knowledge_base.get_welcome_message(),
            "icon": "🧠"
        }
    ]
    
    return {"agents": agents}
