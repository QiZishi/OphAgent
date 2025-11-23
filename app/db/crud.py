# app/db/crud.py
from typing import List, Optional
from sqlmodel import Session, select
from app.db.models import User, Conversation, Message, Attachment
from datetime import datetime

def create_user(session: Session, username: str, hashed_password: str) -> User:
    """创建新用户"""
    user = User(username=username, hashed_password=hashed_password)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user

def get_user_by_username(session: Session, username: str) -> Optional[User]:
    """根据用户名获取用户"""
    statement = select(User).where(User.username == username)
    return session.exec(statement).first()

def get_user_by_id(session: Session, user_id: int) -> Optional[User]:
    """根据ID获取用户"""
    statement = select(User).where(User.id == user_id)
    return session.exec(statement).first()

def create_conversation(session: Session, title: str, user_id: int, agent_type: str) -> Conversation:
    """创建新对话"""
    conversation = Conversation(title=title, user_id=user_id, agent_type=agent_type)
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation

def get_user_conversations(session: Session, user_id: int) -> List[Conversation]:
    """获取用户的所有对话"""
    statement = select(Conversation).where(Conversation.user_id == user_id).order_by(Conversation.created_at.desc())
    return session.exec(statement).all()

def get_conversation_by_id(session: Session, conversation_id: int) -> Optional[Conversation]:
    """根据ID获取对话"""
    statement = select(Conversation).where(Conversation.id == conversation_id)
    return session.exec(statement).first()

def create_message(session: Session, conversation_id: int, role: str, content: str, 
                  thinking_content: Optional[str] = None, thinking_time_s: Optional[float] = None) -> Message:
    """创建新消息"""
    message = Message(
        conversation_id=conversation_id, 
        role=role, 
        content=content,
        thinking_content=thinking_content,
        thinking_time_s=thinking_time_s
    )
    session.add(message)
    session.commit()
    session.refresh(message)
    return message

def get_conversation_messages(session: Session, conversation_id: int) -> List[Message]:
    """获取对话的所有消息"""
    statement = select(Message).where(
        Message.conversation_id == conversation_id,
        Message.is_active == True
    ).order_by(Message.created_at.asc())
    return session.exec(statement).all()

def create_attachment(session: Session, message_id: int, file_path: str, original_filename: str) -> Attachment:
    """创建附件"""
    attachment = Attachment(
        message_id=message_id,
        file_path=file_path,
        original_filename=original_filename
    )
    session.add(attachment)
    session.commit()
    session.refresh(attachment)
    return attachment

def update_conversation_title(session: Session, conversation_id: int, title: str) -> Optional[Conversation]:
    """更新对话标题"""
    conversation = get_conversation_by_id(session, conversation_id)
    if conversation:
        conversation.title = title
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
    return conversation

def delete_conversation(session: Session, conversation_id: int) -> bool:
    """删除对话"""
    conversation = get_conversation_by_id(session, conversation_id)
    if conversation:
        session.delete(conversation)
        session.commit()
        return True
    return False
