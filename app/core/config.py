"""Application configuration.

The production application never fabricates credentials or medical results.
Every external capability has an explicit configuration block and can report
``unavailable`` independently.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_NAME: str = "OphAgent-Pro"
    APP_VERSION: str = "3.0.0"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    STRICT_STARTUP: bool = True
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    REQUEST_TIMEOUT_SECONDS: float = 60.0
    MAX_RETRIES: int = 2
    MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024
    RUN_MAX_CONCURRENCY: int = 3
    RUN_MAX_MODEL_CALLS: int = 12
    RUN_MAX_TOKENS: int = 40_000
    MODEL_MAX_OUTPUT_TOKENS: int = 4_096
    CONTEXT_MAX_INPUT_TOKENS: int = 3_600
    CONTEXT_RECENT_TURNS: int = 4
    CONTEXT_MAX_SOURCE_TURNS: int = 100

    JWT_SECRET_KEY: SecretStr = SecretStr("")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    DATABASE_URL: str = "sqlite:///./app/db/ophagent_pro.db"

    UPLOAD_DIR: str = "data/runtime/attachments/files"
    ATTACHMENT_DIR: str = "data/runtime/attachments"
    ARTIFACT_DIR: str = "data/runtime/artifacts"
    RUNTIME_STATE_DIR: str = "data/runtime/runs"
    MEMORY_STATE_PATH: str = "data/runtime/memories.json"
    MEMORY_PREFERENCE_PATH: str = "data/runtime/memory_preferences.json"
    SKILL_STATE_PATH: str = "data/runtime/skills.json"
    KNOWLEDGE_RAW_DIR: str = "data/knowledge_base/raw"
    KNOWLEDGE_INDEX_DIR: str = "data/knowledge_base/index"
    KNOWLEDGE_CHUNK_SIZE: int = 1400
    KNOWLEDGE_CHUNK_OVERLAP: int = 180
    KNOWLEDGE_EMBED_BATCH_SIZE: int = 32
    KNOWLEDGE_VECTOR_CANDIDATES: int = 60
    KNOWLEDGE_ALLOW_EXPIRED: bool = False
    KNOWLEDGE_MIN_RELEVANCE: float = 0.08
    TOOL_REGISTRY_PATH: Path = PROJECT_ROOT / "config" / "tool_registry.yaml"
    SKILL_ROOT: str = "skills"
    SKILL_EVALUATION_DIR: str = "data/runtime/skill_evaluations"

    # Main and specialist models. All are OpenAI-compatible endpoints.
    AGENT_URL: str = ""
    AGENT_API_KEY: SecretStr = SecretStr("")
    AGENT_MODEL: str = ""
    SUB_AGENT_URL: str = ""
    SUB_AGENT_API_KEY: SecretStr = SecretStr("")
    SUB_AGENT_MODEL: str = ""

    # Backward-compatible aliases are accepted during migration only.
    LLM_BASE_URL: str = ""
    LLM_API_KEY: SecretStr = SecretStr("")
    LLM_MODEL: str = ""
    OPENAI_API_BASE: str = ""
    OPENAI_API_KEY: SecretStr = SecretStr("")
    MODEL_NAME: str = ""
    TEMPERATURE: float = 0.2

    ASR_URL: str = ""
    ASR_API_KEY: SecretStr = SecretStr("")
    ASR_MODEL: str = ""
    TTS_URL: str = ""
    TTS_API_KEY: SecretStr = SecretStr("")
    TTS_MODEL: str = ""

    SILICONFLOW_URL: str = "https://api.siliconflow.cn/v1"
    SILICONFLOW_API_KEY: SecretStr = SecretStr("")
    EMBEDDING_URL: str = ""
    EMBEDDING_API_KEY: SecretStr = SecretStr("")
    EMBEDDING_MODEL: str = ""
    RERANK_URL: str = ""
    RERANK_API_KEY: SecretStr = SecretStr("")
    RERANK_MODEL: str = ""

    ANYSEARCH_URL: str = ""
    ANYSEARCH_API_KEY: SecretStr = SecretStr("")
    TAVILY_URL: str = "https://api.tavily.com/search"
    TAVILY_API_KEY: SecretStr = SecretStr("")
    # MinerU Agent API accepts direct multipart uploads. The address is fixed;
    # users may only override the access token.
    MINERU_URL: str = "https://mineru.net/api/v1/agent/parse/file"
    MINERU_API_KEY: SecretStr = SecretStr("")

    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    OTEL_SERVICE_NAME: str = "ophagent-pro"
    AGENTSCOPE_STUDIO_URL: str = ""
    AGENTSCOPE_DISABLE_CONSOLE_OUTPUT: bool = True
    AGENT_MAX_ITERS: int = 3
    AGENT_REASONING_EFFORT: str = "low"

    EVOLUTION_STATE_DIR: str = "data/evolution"
    EVOLUTION_WORKTREE_DIR: str = ".worktrees/evolution"
    EVOLUTION_SEALED_TEST_DIR: str = ""
    EVOLUTION_GATE_SECRET: SecretStr = SecretStr("")
    EVOLUTION_GATE_SECRET_FILE: str = "data/evolution/gate_secret"
    ADAPTIVE_HARNESS_ROOT: str = ""
    EVOLUTION_MAX_TOKEN_RATIO: float = 1.15
    EVOLUTION_MAX_LATENCY_RATIO: float = 1.20
    EVOLUTION_MIN_MEAN_IMPROVEMENT: float = 0.01
    EVOLUTION_MAX_SLICE_REGRESSION: float = 0.0
    EVOLUTION_MIN_CASES_PER_SLICE: int = 1
    EVOLUTION_REQUIRE_HUMAN_APPROVAL: bool = True
    EVOLUTION_MIN_FEEDBACK_SAMPLES: int = 3
    EVOLUTION_NEGATIVE_RATE_THRESHOLD: float = 0.60
    EVOLUTION_POSITIVE_RATE_THRESHOLD: float = 0.60
    EVOLUTION_MEMORY_RANKING_BOUND: float = 0.15
    EVOLUTION_SKILL_RANKING_BOUND: float = 0.20
    EVOLUTION_SKILL_AUTO_SUPPRESS_THRESHOLD: float = 0.90
    EVOLUTION_MAX_ONLINE_RECORDS: int = 5_000
    EVOLUTION_SIGNAL_LOG_MAX_BYTES: int = 20_000_000

    @property
    def project_root(self) -> Path:
        return PROJECT_ROOT

    def resolve_path(self, value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def main_model_url(self) -> str:
        return self.AGENT_URL or self.LLM_BASE_URL or self.OPENAI_API_BASE

    @property
    def main_model_key(self) -> SecretStr:
        for key in (self.AGENT_API_KEY, self.LLM_API_KEY, self.OPENAI_API_KEY):
            if key.get_secret_value():
                return key
        return SecretStr("")

    @property
    def main_model_name(self) -> str:
        return self.AGENT_MODEL or self.LLM_MODEL or self.MODEL_NAME

    @property
    def sub_model_url(self) -> str:
        return self.SUB_AGENT_URL or self.main_model_url

    @property
    def sub_model_key(self) -> SecretStr:
        return self.SUB_AGENT_API_KEY if self.SUB_AGENT_API_KEY.get_secret_value() else self.main_model_key

    @property
    def sub_model_name(self) -> str:
        return self.SUB_AGENT_MODEL or self.main_model_name

    @property
    def embedding_url(self) -> str:
        return self.EMBEDDING_URL or self.SILICONFLOW_URL

    @property
    def embedding_key(self) -> SecretStr:
        return self.EMBEDDING_API_KEY if self.EMBEDDING_API_KEY.get_secret_value() else self.SILICONFLOW_API_KEY

    @property
    def rerank_url(self) -> str:
        return self.RERANK_URL or self.SILICONFLOW_URL

    @property
    def rerank_key(self) -> SecretStr:
        return self.RERANK_API_KEY if self.RERANK_API_KEY.get_secret_value() else self.SILICONFLOW_API_KEY

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    def startup_errors(self) -> list[str]:
        errors: list[str] = []
        if not self.JWT_SECRET_KEY.get_secret_value():
            errors.append("JWT_SECRET_KEY 未配置")
        if not self.main_model_url:
            errors.append("AGENT_URL 未配置")
        if not self.main_model_key.get_secret_value():
            errors.append("AGENT_API_KEY 未配置")
        if not self.main_model_name:
            errors.append("AGENT_MODEL 未配置")
        if not self.sub_model_url:
            errors.append("SUB_AGENT_URL 未配置")
        if not self.sub_model_key.get_secret_value():
            errors.append("SUB_AGENT_API_KEY 未配置")
        if not self.sub_model_name:
            errors.append("SUB_AGENT_MODEL 未配置")
        return errors


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
