# app/db/crud.py
from datetime import datetime

from sqlmodel import Session, func, select

from app.db.models import (
    Attachment,
    AuditLog,
    Conversation,
    Message,
    Project,
    SessionToken,
    User,
)


def create_user(session: Session, username: str, hashed_password: str) -> User:
    user = User(username=username, hashed_password=hashed_password)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def get_user_by_username(session: Session, username: str) -> User | None:
    statement = select(User).where(User.username == username)
    return session.exec(statement).first()


def get_user_by_id(session: Session, user_id: int) -> User | None:
    statement = select(User).where(User.id == user_id)
    return session.exec(statement).first()


def record_audit(
    session: Session,
    user_id: int,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: str = "{}",
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def create_session_token(
    session: Session,
    jti: str,
    user_id: int,
    expires_at: datetime,
) -> SessionToken:
    token = SessionToken(jti=jti, user_id=user_id, expires_at=expires_at)
    session.add(token)
    session.commit()
    session.refresh(token)
    return token


def get_session_token(
    session: Session,
    jti: str,
    user_id: int,
) -> SessionToken | None:
    return session.exec(
        select(SessionToken).where(
            SessionToken.jti == jti,
            SessionToken.user_id == user_id,
            SessionToken.revoked_at.is_(None),
        )
    ).first()


def revoke_session_token(session: Session, jti: str) -> None:
    token = session.get(SessionToken, jti)
    if token is None or token.revoked_at is not None:
        return
    token.revoked_at = datetime.now(token.created_at.tzinfo)
    session.add(token)
    session.commit()


def revoke_user_sessions(session: Session, user_id: int) -> None:
    tokens = session.exec(
        select(SessionToken).where(
            SessionToken.user_id == user_id,
            SessionToken.revoked_at.is_(None),
        )
    ).all()
    for token in tokens:
        token.revoked_at = datetime.now(token.created_at.tzinfo)
        session.add(token)
    session.commit()


def list_projects(session: Session, user_id: int) -> list[Project]:
    return list(
        session.exec(
            select(Project)
            .where(Project.user_id == user_id)
            .order_by(Project.updated_at.desc())
        ).all()
    )


def get_project(session: Session, project_id: int, user_id: int) -> Project | None:
    return session.exec(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    ).first()


def create_project(session: Session, user_id: int, name: str, description: str = "") -> Project:
    project = Project(user_id=user_id, name=name, description=description)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def update_project(session: Session, project: Project, values: dict) -> Project:
    for key, value in values.items():
        setattr(project, key, value)
    project.updated_at = datetime.now(project.updated_at.tzinfo)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def delete_project(session: Session, project: Project) -> None:
    conversations = session.exec(
        select(Conversation).where(Conversation.project_id == project.id)
    ).all()
    for conversation in conversations:
        conversation.project_id = None
        session.add(conversation)
    session.delete(project)
    session.commit()


def count_project_conversations(session: Session, project_id: int) -> int:
    return int(
        session.exec(
            select(func.count(Conversation.id)).where(Conversation.project_id == project_id)
        ).one()
    )


def create_conversation(
    session: Session,
    title: str,
    user_id: int,
    agent_type: str = "aux_diagnosis",
    project_id: int | None = None,
) -> Conversation:
    conversation = Conversation(
        title=title,
        user_id=user_id,
        agent_type=agent_type,
        project_id=project_id,
    )
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


def get_user_conversations(
    session: Session, 
    user_id: int, 
    skip: int = 0, 
    limit: int = 20
) -> tuple[list[Conversation], int]:
    count_statement = select(func.count(Conversation.id)).where(Conversation.user_id == user_id)
    total = session.exec(count_statement).one()
    
    statement = select(Conversation).where(
        Conversation.user_id == user_id
    ).order_by(
        Conversation.created_at.desc()
    ).offset(skip).limit(limit)
    conversations = session.exec(statement).all()
    return conversations, total


def get_conversation_by_id(session: Session, conversation_id: int) -> Conversation | None:
    statement = select(Conversation).where(Conversation.id == conversation_id)
    return session.exec(statement).first()


def create_message(
    session: Session, 
    conversation_id: int, 
    role: str, 
    content: str,
    file_path: str | None = None,
    thinking_content: str | None = None,
    thinking_time_s: float | None = None,
    idempotency_key: str | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation_id, 
        role=role, 
        content=content,
        file_path=file_path,
        thinking_content=thinking_content,
        thinking_time_s=thinking_time_s,
        idempotency_key=idempotency_key,
    )
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


def get_message_by_idempotency(
    session: Session,
    conversation_id: int,
    idempotency_key: str,
) -> Message | None:
    statement = select(Message).where(
        Message.conversation_id == conversation_id,
        Message.idempotency_key == idempotency_key,
    )
    return session.exec(statement).first()


def get_conversation_messages(session: Session, conversation_id: int) -> list[Message]:
    statement = select(Message).where(
        Message.conversation_id == conversation_id,
        Message.is_active == True
    ).order_by(Message.created_at.asc())
    return session.exec(statement).all()


def create_attachment(session: Session, message_id: int, file_path: str, original_filename: str) -> Attachment:
    attachment = Attachment(
        message_id=message_id,
        file_path=file_path,
        original_filename=original_filename
    )
    session.add(attachment)
    session.commit()
    session.refresh(attachment)
    return attachment


def update_conversation_title(session: Session, conversation_id: int, title: str) -> Conversation | None:
    conversation = get_conversation_by_id(session, conversation_id)
    if conversation:
        conversation.title = title
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
    return conversation


def update_conversation_project(
    session: Session,
    conversation: Conversation,
    project_id: int | None,
) -> Conversation:
    conversation.project_id = project_id
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


def delete_conversation(session: Session, conversation_id: int) -> bool:
    conversation = get_conversation_by_id(session, conversation_id)
    if conversation:
        session.delete(conversation)
        session.commit()
        return True
    return False
