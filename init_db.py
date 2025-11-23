#!/usr/bin/env python3
# 数据库初始化脚本
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import engine
from app.db.models import SQLModel

def init_db():
    """初始化数据库"""
    print("正在初始化数据库...")
    SQLModel.metadata.create_all(engine)
    print("数据库初始化完成！")

if __name__ == "__main__":
    init_db()
