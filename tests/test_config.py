import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.runtime.document_exports import answer_with_references, render_docx, render_jpg, render_pdf
from app.runtime.store import RuntimeStore
from app.services.provider_config import (
    MINERU_FIXED_URL,
    ProviderConfigInput,
    ProviderConfigStore,
)


def test_real_env_field_names_are_accepted():
    config = Settings(
        _env_file=None,
        JWT_SECRET_KEY=SecretStr("secret"),
        AGENT_URL="https://main.example/v1",
        AGENT_API_KEY=SecretStr("main-key"),
        AGENT_MODEL="main-model",
        SUB_AGENT_URL="https://sub.example/v1",
        SUB_AGENT_API_KEY=SecretStr("sub-key"),
        SUB_AGENT_MODEL="vision-model",
        EMBEDDING_MODEL="bge-m3",
        RERANK_MODEL="bge-reranker",
        ANYSEARCH_URL="https://search.example",
        MINERU_URL="https://mineru.example",
    )
    assert config.startup_errors() == []
    assert config.main_model_name == "main-model"
    assert config.sub_model_name == "vision-model"


def test_missing_core_credentials_are_explicit():
    config = Settings(_env_file=None)
    errors = config.startup_errors()
    assert "AGENT_API_KEY 未配置" in errors
    assert "SUB_AGENT_MODEL 未配置" in errors


def test_capability_package_imports_without_order_dependency():
    from app.tools import CapabilityClients

    assert CapabilityClients.__name__ == "CapabilityClients"


def test_provider_origins_receive_documented_paths():
    from app.tools.capabilities import _with_default_path

    assert _with_default_path("https://search.example", "/v1/search") == "https://search.example/v1/search"
    assert _with_default_path("https://search.example/custom", "/v1/search").endswith("/custom")


def test_anysearch_nested_results_are_normalized():
    from app.tools.capabilities import CapabilityClients

    normalized = CapabilityClients._normalize_search_payload(
        {
            "data": {
                "results": [
                    {
                        "title": "指南",
                        "url": "https://example.test/guideline",
                        "snippet": "可追踪摘要",
                    },
                ],
            },
        },
        "AnySearch",
    )
    assert len(normalized["evidence"]) == 1
    assert normalized["evidence"][0]["source_type"] == "web"


@pytest.mark.asyncio
async def test_personal_provider_keys_are_encrypted_and_resolved(tmp_path):
    config = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        JWT_SECRET_KEY=SecretStr("test-encryption-secret"),
        RUNTIME_STATE_DIR=str(tmp_path / "runs"),
        ARTIFACT_DIR=str(tmp_path / "artifacts"),
        ATTACHMENT_DIR=str(tmp_path / "attachments"),
        AGENT_URL="https://default.example/v1",
        AGENT_API_KEY=SecretStr("default-key"),
        AGENT_MODEL="default-model",
    )
    runtime = RuntimeStore(config)
    providers = ProviderConfigStore(runtime, config)
    public_default = await providers.public_config(7)
    assert public_default["providers"]["sub_agent"]["default_url"] == "https://default.example/v1"
    assert public_default["providers"]["embedding"]["default_url"] == config.SILICONFLOW_URL
    assert public_default["mineru_url"] == MINERU_FIXED_URL

    incoming = {
        provider: {"use_default": True}
        for provider in public_default["providers"]
    }
    incoming["agent"] = {
        "use_default": False,
        "url": "https://personal.example/v1",
        "model": "personal-model",
        "api_key": "personal-secret-key",
    }
    saved = await providers.save(7, ProviderConfigInput(providers=incoming))
    assert saved["providers"]["agent"]["has_api_key"] is True
    assert "api_key" not in saved["providers"]["agent"]
    raw = await runtime.get_provider_config(7)
    assert raw["agent"]["api_key_encrypted"] != "personal-secret-key"

    resolved = await providers.resolved_settings(7)
    assert resolved.main_model_url == "https://personal.example/v1"
    assert resolved.main_model_name == "personal-model"
    assert resolved.main_model_key.get_secret_value() == "personal-secret-key"


@pytest.mark.asyncio
async def test_personal_provider_rejects_local_and_plain_http_ssrf_targets(tmp_path):
    config = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        JWT_SECRET_KEY=SecretStr("test-encryption-secret"),
        RUNTIME_STATE_DIR=str(tmp_path / "runs"),
        ARTIFACT_DIR=str(tmp_path / "artifacts"),
        ATTACHMENT_DIR=str(tmp_path / "attachments"),
    )
    runtime = RuntimeStore(config)
    providers = ProviderConfigStore(runtime, config)
    defaults = await providers.public_config(7)
    incoming = {
        provider: {"use_default": True}
        for provider in defaults["providers"]
    }
    incoming["agent"] = {
        "use_default": False,
        "url": "http://127.0.0.1:8000/v1",
        "model": "private-model",
        "api_key": "secret",
    }

    with pytest.raises(ValueError, match="HTTPS"):
        await providers.save(7, ProviderConfigInput(providers=incoming))

    incoming["agent"]["url"] = "https://[::1]/v1"
    with pytest.raises(ValueError, match="本机、内网或保留地址"):
        await providers.save(7, ProviderConfigInput(providers=incoming))


def test_document_exports_have_expected_file_signatures():
    content = "# 检查摘要\n\n视神经乳头改变，建议结合眼压与视野。"
    assert render_pdf(content).startswith(b"%PDF")
    assert render_docx(content).startswith(b"PK")
    assert render_jpg(content).startswith(b"\xff\xd8")


def test_document_answer_replaces_internal_ids_and_appends_sources():
    content = "青光眼需要结合视神经与视野判断[ev_a1]。"
    rendered = answer_with_references(content, [{
        "id": "ev_a1",
        "title": "青光眼指南",
        "source": "https://example.test/guideline",
        "locator": "第 3 章",
        "excerpt": "诊断需要综合结构与功能证据。",
    }])
    assert "[ev_a1]" not in rendered
    assert "判断[1]" in rendered
    assert "## 参考来源" in rendered
    assert "[青光眼指南](https://example.test/guideline)" in rendered
