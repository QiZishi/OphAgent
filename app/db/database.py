# app/db/database.py
from sqlmodel import SQLModel, create_engine, Session
from app.core.config import settings
import os

# 确保数据库目录存在
db_dir = os.path.dirname("app/db/lingtong.db")
if not os.path.exists(db_dir):
    os.makedirs(db_dir)

# 创建数据库引擎
sqlite_file_name = "app/db/lingtong.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

engine = create_engine(sqlite_url, echo=False)

def create_db_and_tables():
    """创建数据库表"""
    SQLModel.metadata.create_all(engine)

def get_session():
    """获取数据库会话"""
    with Session(engine) as session:
        yield session
