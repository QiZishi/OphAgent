# app/db/database.py
import os

from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

db_path = settings.DATABASE_URL.replace("sqlite:///", "")
db_dir = os.path.dirname(db_path)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir)

engine = create_engine(settings.DATABASE_URL, echo=False)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    # Backward-compatible additive migration for existing local installations.
    with engine.begin() as connection:
        user_columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(user)").fetchall()
        }
        if "role" not in user_columns:
            connection.exec_driver_sql(
                "ALTER TABLE user ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'patient'",
            )
        conversation_columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(conversation)").fetchall()
        }
        if "pinned" not in conversation_columns:
            connection.exec_driver_sql(
                "ALTER TABLE conversation ADD COLUMN pinned BOOLEAN NOT NULL DEFAULT 0",
            )
        if "project_id" not in conversation_columns:
            connection.exec_driver_sql(
                "ALTER TABLE conversation ADD COLUMN project_id INTEGER",
            )
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_conversation_project_id ON conversation (project_id)",
            )
        message_columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(message)").fetchall()
        }
        if "idempotency_key" not in message_columns:
            connection.exec_driver_sql(
                "ALTER TABLE message ADD COLUMN idempotency_key VARCHAR(128)",
            )
        connection.exec_driver_sql("DROP INDEX IF EXISTS ix_message_idempotency_key")
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_message_conversation_idempotency "
            "ON message (conversation_id, idempotency_key) "
            "WHERE idempotency_key IS NOT NULL",
        )

def get_session():
    with Session(engine) as session:
        yield session
