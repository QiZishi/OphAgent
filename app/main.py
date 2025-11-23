# app/main.py
from fastapi import FastAPI, Request, Depends, HTTPException, status, Cookie
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.api.router import router as api_router
from app.auth.router import router as auth_router
from app.db.database import create_db_and_tables
from jose import JWTError, jwt
from app.core.config import settings
from app.auth.security import try_get_current_user
from app.db.models import User

security = HTTPBearer(auto_error=False)

def verify_token_optional(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """可选的token验证，不抛出异常"""
    if not credentials:
        return None
    try:
        payload = jwt.decode(credentials.credentials, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id: int = payload.get("sub")
        return user_id if user_id else None
    except JWTError:
        return None

app = FastAPI(title="灵瞳医疗AI系统", version="1.0.0")

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8010", "http://127.0.0.1:8010"],  # 限制允许的域名
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],  # 限制允许的方法
    allow_headers=["Authorization", "Content-Type"],  # 限制允许的头部
)

# 1. 挂载静态文件目录
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# 2. 配置Jinja2模板目录
templates = Jinja2Templates(directory="app/templates")

# 3. 包含API路由
app.include_router(api_router, prefix="/api/v1")
app.include_router(auth_router, tags=["Authentication"])

# 4. 创建根路由以提供前端页面
@app.get("/", response_class=HTMLResponse)
async def serve_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/register", response_class=HTMLResponse)
async def serve_register(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/app", response_class=HTMLResponse)
async def serve_main_app(request: Request, access_token: str | None = Cookie(None)):
    """
    服务主应用页面。
    如果用户未认证（通过cookie验证），则重定向到登录页面。
    """
    if access_token is None:
        return RedirectResponse(url="/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    
    # 简单的token存在性检查
    # 更强的验证可以解码并验证token
    try:
        # 去掉 "bearer " 前缀
        token = access_token.split(" ")[1]
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except (JWTError, IndexError):
        # 如果解码失败或格式不正确，重定向到登录
        return RedirectResponse(url="/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/sw.js")
async def service_worker():
    """提供Service Worker文件"""
    return FileResponse("app/static/sw.js", media_type="application/javascript")

@app.on_event("startup")
async def startup_event():
    """应用启动时创建数据库表"""
    create_db_and_tables()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)
