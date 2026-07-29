#!/usr/bin/env python3

from app.db.database import engine
from app.db.models import SQLModel


def init_db():
    print("正在初始化 OphAgent-Pro 数据库...")
    SQLModel.metadata.create_all(engine)
    print("数据库初始化完成！")


if __name__ == "__main__":
    init_db()
