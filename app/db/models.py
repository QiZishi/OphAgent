# app/db/models.py
from datetime import datetime, timedelta, timezone

from sqlmodel import Field, Relationship, SQLModel

BEIJING_TZ = timezone(timedelta(hours=8))

def beijing_now():
    return datetime.now(BEIJING_TZ)

class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True, max_length=50)
    hashed_password: str
    role: str = Field(default="patient", max_length=20)
    created_at: datetime = Field(default_factory=beijing_now, nullable=False)
    conversations: list["Conversation"] = Relationship(back_populates="user")

class Conversation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(index=True, max_length=100)
    user_id: int = Field(foreign_key="user.id")
    agent_type: str
    pinned: bool = Field(default=False, nullable=False)
    project_id: int | None = Field(default=None, foreign_key="project.id", index=True)
    created_at: datetime = Field(default_factory=beijing_now, nullable=False)
    user: User = Relationship(back_populates="conversations")
    messages: list["Message"] = Relationship(back_populates="conversation", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

class Message(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id")
    role: str
    content: str
    thinking_content: str | None = None
    thinking_time_s: float | None = None
    file_path: str | None = None
    parent_message_id: int | None = Field(default=None, foreign_key="message.id")
    version: int = Field(default=1, nullable=False)
    is_active: bool = Field(default=True, nullable=False)
    idempotency_key: str | None = Field(default=None, max_length=128, index=True)
    created_at: datetime = Field(default_factory=beijing_now, nullable=False)
    conversation: Conversation = Relationship(back_populates="messages")
    attachments: list["Attachment"] = Relationship(back_populates="message", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

class Project(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str = Field(max_length=80)
    description: str = Field(default="", max_length=500)
    color: str = Field(default="#35A9D6", max_length=20)
    created_at: datetime = Field(default_factory=beijing_now, nullable=False)
    updated_at: datetime = Field(default_factory=beijing_now, nullable=False)


class AuditLog(SQLModel, table=True):
    """Content-free governance audit record.

    Patient text, file contents and secrets are intentionally excluded.
    """

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    action: str = Field(max_length=80, index=True)
    resource_type: str = Field(max_length=80, index=True)
    resource_id: str | None = Field(default=None, max_length=160)
    details: str = Field(default="{}", max_length=2000)
    created_at: datetime = Field(default_factory=beijing_now, nullable=False, index=True)


class SessionToken(SQLModel, table=True):
    jti: str = Field(primary_key=True, max_length=64)
    user_id: int = Field(foreign_key="user.id", index=True)
    expires_at: datetime
    revoked_at: datetime | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=beijing_now, nullable=False)


class Attachment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    message_id: int = Field(foreign_key="message.id")
    file_path: str
    original_filename: str
    message: Message = Relationship(back_populates="attachments")
