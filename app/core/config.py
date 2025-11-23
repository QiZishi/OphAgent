# app/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # OpenAI API Configuration
    OPENAI_API_BASE: str = "your-api-base-url"
    OPENAI_API_KEY: str = "your-api-key"

    # Model Configuration
    MODEL_NAME: str = "your-model-name"
    TEMPERATURE: float = 0.7
      
    # JWT Secret Key
    JWT_SECRET_KEY: str = "a_very_secret_key"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings()

# 打印配置信息用于调试
print(f"[CONFIG] OpenAI API Base: {settings.OPENAI_API_BASE}")
print(f"[CONFIG] OpenAI API Key: {settings.OPENAI_API_KEY[:10]}...{settings.OPENAI_API_KEY[-4:]}")
print(f"[CONFIG] Model Name: {settings.MODEL_NAME}")
print(f"[CONFIG] Temperature: {settings.TEMPERATURE}")
