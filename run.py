# run.py
import uvicorn
from app.main import app

if __name__ == "__main__":
    # 使用uvicorn以编程方式运行FastAPI应用
    # reload=True 可以在开发时实现代码热重载
    uvicorn.run("app.main:app", host="0.0.0.0", port=8012, reload=True)
