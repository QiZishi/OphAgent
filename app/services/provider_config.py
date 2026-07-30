"""Encrypted per-user provider overrides with explicit default fallback."""

from __future__ import annotations

import base64
import hashlib
import ipaddress
from typing import Any
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, Field, SecretStr

from app.core.config import Settings
from app.runtime.store import RuntimeStore

MINERU_FIXED_URL = "https://mineru.net/api/v1/agent/parse/file"

PROVIDERS: dict[str, dict[str, str | None]] = {
    "agent": {"url": "AGENT_URL", "key": "AGENT_API_KEY", "model": "AGENT_MODEL"},
    "sub_agent": {"url": "SUB_AGENT_URL", "key": "SUB_AGENT_API_KEY", "model": "SUB_AGENT_MODEL"},
    "asr": {"url": "ASR_URL", "key": "ASR_API_KEY", "model": "ASR_MODEL"},
    "tts": {"url": "TTS_URL", "key": "TTS_API_KEY", "model": "TTS_MODEL"},
    "embedding": {"url": "EMBEDDING_URL", "key": "EMBEDDING_API_KEY", "model": "EMBEDDING_MODEL"},
    "reranker": {"url": "RERANK_URL", "key": "RERANK_API_KEY", "model": "RERANK_MODEL"},
    "search": {"url": "ANYSEARCH_URL", "key": "ANYSEARCH_API_KEY", "model": None},
    "mineru": {"url": None, "key": "MINERU_API_KEY", "model": None},
}


class ProviderOverrideInput(BaseModel):
    use_default: bool = True
    url: str = Field(default="", max_length=2_000)
    api_key: str | None = Field(default=None, max_length=8_000)
    model: str = Field(default="", max_length=500)


class ProviderConfigInput(BaseModel):
    providers: dict[str, ProviderOverrideInput]


class ProviderConfigStore:
    def __init__(self, store: RuntimeStore, defaults: Settings) -> None:
        self.store = store
        self.defaults = defaults
        digest = hashlib.sha256(defaults.JWT_SECRET_KEY.get_secret_value().encode("utf-8")).digest()
        self.cipher = Fernet(base64.urlsafe_b64encode(digest))

    async def public_config(self, user_id: int) -> dict[str, Any]:
        raw = await self.store.get_provider_config(user_id)
        providers: dict[str, Any] = {}
        for provider, fields in PROVIDERS.items():
            saved = raw.get(provider, {})
            default_url, default_model, default_key = self._effective_default(provider, fields)
            providers[provider] = {
                "use_default": bool(saved.get("use_default", True)),
                "url": MINERU_FIXED_URL if provider == "mineru" else str(saved.get("url") or ""),
                "model": str(saved.get("model") or ""),
                "has_api_key": bool(saved.get("api_key_encrypted")),
                "default_url": default_url,
                "default_model": default_model,
                "default_configured": bool(default_key and (provider == "mineru" or default_url)),
            }
        return {"providers": providers, "mineru_url": MINERU_FIXED_URL}

    async def save(self, user_id: int, payload: ProviderConfigInput) -> dict[str, Any]:
        current = await self.store.get_provider_config(user_id)
        next_payload: dict[str, Any] = {}
        for provider, fields in PROVIDERS.items():
            incoming = payload.providers.get(provider, ProviderOverrideInput())
            existing = current.get(provider, {})
            if incoming.use_default:
                next_payload[provider] = {"use_default": True}
                continue
            if provider != "mineru" and not incoming.url.strip():
                raise ValueError(f"{provider} 使用个人配置时必须填写 URL")
            if provider != "mineru":
                _validate_personal_provider_url(
                    incoming.url,
                    allow_private=self.defaults.ALLOW_PRIVATE_PROVIDER_URLS,
                )
            if fields["model"] and not incoming.model.strip():
                raise ValueError(f"{provider} 使用个人配置时必须填写模型名")
            encrypted = existing.get("api_key_encrypted")
            if incoming.api_key:
                encrypted = self.cipher.encrypt(incoming.api_key.encode("utf-8")).decode("ascii")
            if not encrypted:
                raise ValueError(f"{provider} 使用个人配置时必须填写 API 密钥")
            next_payload[provider] = {
                "use_default": False,
                "url": MINERU_FIXED_URL if provider == "mineru" else incoming.url.strip(),
                "model": incoming.model.strip(),
                "api_key_encrypted": encrypted,
            }
        await self.store.save_provider_config(user_id, next_payload)
        return await self.public_config(user_id)

    async def resolved_settings(self, user_id: int) -> Settings:
        raw = await self.store.get_provider_config(user_id)
        updates: dict[str, Any] = {}
        for provider, fields in PROVIDERS.items():
            saved = raw.get(provider, {})
            if saved.get("use_default", True):
                continue
            if fields["url"]:
                updates[str(fields["url"])] = saved.get("url", "")
            if fields["model"]:
                updates[str(fields["model"])] = saved.get("model", "")
            if fields["key"]:
                updates[str(fields["key"])] = SecretStr(self._decrypt(saved.get("api_key_encrypted", "")))
        if raw.get("mineru", {}).get("use_default") is False:
            updates["MINERU_URL"] = MINERU_FIXED_URL
        return self.defaults.model_copy(update=updates)

    async def has_overrides(self, user_id: int) -> bool:
        raw = await self.store.get_provider_config(user_id)
        return any(not value.get("use_default", True) for value in raw.values())

    def _default(self, field: str | None, *, secret: bool = False) -> str:
        if not field:
            return ""
        value = getattr(self.defaults, field)
        if secret:
            return value.get_secret_value()
        return str(value)

    def _effective_default(
        self,
        provider: str,
        fields: dict[str, str | None],
    ) -> tuple[str, str, str]:
        """Return the effective system default after compatibility fallbacks."""
        if provider == "agent":
            return (
                self.defaults.main_model_url,
                self.defaults.main_model_name,
                self.defaults.main_model_key.get_secret_value(),
            )
        if provider == "sub_agent":
            return (
                self.defaults.sub_model_url,
                self.defaults.sub_model_name,
                self.defaults.sub_model_key.get_secret_value(),
            )
        if provider == "embedding":
            return (
                self.defaults.embedding_url,
                self.defaults.EMBEDDING_MODEL,
                self.defaults.embedding_key.get_secret_value(),
            )
        if provider == "reranker":
            return (
                self.defaults.rerank_url,
                self.defaults.RERANK_MODEL,
                self.defaults.rerank_key.get_secret_value(),
            )
        if provider == "search":
            return (
                self.defaults.ANYSEARCH_URL or self.defaults.TAVILY_URL,
                "",
                (
                    self.defaults.ANYSEARCH_API_KEY.get_secret_value()
                    or self.defaults.TAVILY_API_KEY.get_secret_value()
                ),
            )
        if provider == "mineru":
            return (
                MINERU_FIXED_URL,
                "",
                self.defaults.MINERU_API_KEY.get_secret_value(),
            )
        return (
            self._default(fields["url"]),
            self._default(fields["model"]),
            self._default(fields["key"], secret=True),
        )

    def _decrypt(self, value: str) -> str:
        if not value:
            return ""
        try:
            return self.cipher.decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError):
            return ""


def _validate_personal_provider_url(
    value: str,
    *,
    allow_private: bool,
) -> None:
    """Prevent user-configured provider endpoints from becoming an SSRF path.

    Operators can still configure trusted local providers through ``.env``.
    Private endpoints for per-user configuration require an explicit deployment
    opt-in because all ordinary accounts share the same product capabilities.
    """
    parts = urlsplit(value.strip())
    allowed_schemes = {"http", "https"} if allow_private else {"https"}
    if parts.scheme not in allowed_schemes:
        raise ValueError("个人 Provider URL 必须使用 HTTPS")
    if not parts.hostname or parts.username or parts.password:
        raise ValueError("个人 Provider URL 缺少主机或包含不允许的凭据")
    hostname = parts.hostname.rstrip(".").casefold()
    if not allow_private and (
        hostname == "localhost"
        or hostname.endswith((".localhost", ".local", ".internal", ".home.arpa"))
    ):
        raise ValueError("个人 Provider URL 不能指向本机或内网主机")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if not allow_private and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise ValueError("个人 Provider URL 不能指向本机、内网或保留地址")
