# app/db/models.py
from typing import List, Optional
from sqlmodel import Field, Relationship, SQLModel
from datetime import datetime, timezone, timedelta

# 北京时间时区
BEIJING_TZ = timezone(timedelta(hours=8))

def beijing_now():
    """返回当前北京时间"""
    return datetime.now(BEIJING_TZ)

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True, max_length=50)
    hashed_password: str
    created_at: datetime = Field(default_factory=beijing_now, nullable=False)
    conversations: List["Conversation"] = Relationship(back_populates="user")

class Conversation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True, max_length=100)
    user_id: int = Field(foreign_key="user.id")
    agent_type: str
    created_at: datetime = Field(default_factory=beijing_now, nullable=False)
    user: User = Relationship(back_populates="conversations")
    messages: List["Message"] = Relationship(back_populates="conversation", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id")
    role: str
    content: str
    thinking_content: Optional[str] = None
    thinking_time_s: Optional[float] = None
    file_path: Optional[str] = None  # 添加文件路径字段
    parent_message_id: Optional[int] = Field(default=None, foreign_key="message.id")
    version: int = Field(default=1, nullable=False)
    is_active: bool = Field(default=True, nullable=False)
    created_at: datetime = Field(default_factory=beijing_now, nullable=False)
    conversation: Conversation = Relationship(back_populates="messages")
    attachments: List["Attachment"] = Relationship(back_populates="message", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

class Attachment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    message_id: int = Field(foreign_key="message.id")
    file_path: str
    original_filename: str
    message: Message = Relationship(back_populates="attachments")
