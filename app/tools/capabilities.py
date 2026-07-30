"""Typed clients for external and local capabilities."""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import re
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, Field

from app.core.config import Settings, settings
from app.domain.models import EvidenceItem, ImageRegion
from app.knowledge.retrieval import HybridKnowledgeRetriever
from app.observability.tracing import safe_span
from app.runtime.errors import CapabilityUnavailable


class ToolResult(BaseModel):
    status: Literal["ok", "unavailable", "failed"]
    capability: str
    data: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    message: str | None = None
    attempts: int = 1


class ImageAnalysisRequest(BaseModel):
    image_paths: list[str] = Field(min_length=1, max_length=8)
    image_ids: list[str] = Field(default_factory=list, max_length=8)
    question: str = Field(min_length=1, max_length=10_000)
    request_regions: bool = False


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    max_results: int = Field(default=5, ge=1, le=10)
    recency_days: int | None = Field(default=None, ge=1, le=3650)


class DocumentParseRequest(BaseModel):
    path: str


class SpeechRequest(BaseModel):
    path: str


class SynthesisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    voice: str | None = None


def _normalize_image_analysis_payload(decoded: Any) -> dict[str, Any]:
    """Normalize common OpenAI-compatible JSON response shapes."""

    if isinstance(decoded, dict):
        parsed = dict(decoded)
    elif isinstance(decoded, list):
        mappings = [item for item in decoded if isinstance(item, dict)]
        if not mappings:
            observations = [
                str(item).strip()
                for item in decoded
                if str(item).strip()
            ]
            return {
                "summary": observations[0] if observations else "",
                "observations": observations,
                "limitations": [],
                "uncertainty": "",
                "regions": [],
            }
        summaries: list[str] = []
        observations: list[Any] = []
        limitations: list[Any] = []
        regions: list[Any] = []
        uncertainties: list[str] = []
        for item in mappings:
            if item.get("summary"):
                summaries.append(str(item["summary"]).strip())
            raw_observations = item.get("observations", [])
            observations.extend(
                raw_observations
                if isinstance(raw_observations, list)
                else [raw_observations]
            )
            raw_limitations = item.get("limitations", [])
            limitations.extend(
                raw_limitations
                if isinstance(raw_limitations, list)
                else [raw_limitations]
            )
            raw_regions = item.get("regions", [])
            regions.extend(
                raw_regions if isinstance(raw_regions, list) else [raw_regions]
            )
            if item.get("uncertainty"):
                uncertainties.append(str(item["uncertainty"]).strip())
        parsed = {
            **mappings[0],
            "summary": "\n".join(item for item in summaries if item),
            "observations": observations,
            "limitations": limitations,
            "uncertainty": "\n".join(item for item in uncertainties if item),
            "regions": regions,
        }
    else:
        parsed = {
            "summary": str(decoded).strip() if decoded is not None else "",
        }
    for field in ("observations", "limitations", "regions"):
        value = parsed.get(field, [])
        parsed[field] = value if isinstance(value, list) else [value]
    parsed.setdefault("summary", "")
    parsed.setdefault("uncertainty", "")
    return parsed


def _parse_image_analysis_content(raw: Any) -> dict[str, Any]:
    """Parse provider content without failing the whole medical workflow on shape drift."""

    if isinstance(raw, list):
        raw = "".join(
            str(block.get("text") or "")
            for block in raw
            if isinstance(block, dict)
        )
    if isinstance(raw, (dict, list)):
        return _normalize_image_analysis_payload(raw)
    text = str(raw or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        return _normalize_image_analysis_payload(json.loads(cleaned or "{}"))
    except (json.JSONDecodeError, TypeError, ValueError):
        for left, right in (("{", "}"), ("[", "]")):
            start = cleaned.find(left)
            end = cleaned.rfind(right)
            if start < 0 or end <= start:
                continue
            try:
                return _normalize_image_analysis_payload(
                    json.loads(cleaned[start : end + 1]),
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return {
            "summary": cleaned,
            "observations": [cleaned] if cleaned else [],
            "limitations": ["图像观察未能细分为结构化字段"] if cleaned else [],
            "uncertainty": "",
            "regions": [],
        }


class CapabilityClients:
    def __init__(
        self,
        config: Settings = settings,
        retriever: HybridKnowledgeRetriever | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.retriever = retriever or HybridKnowledgeRetriever(config)
        self.http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(config.REQUEST_TIMEOUT_SECONDS),
            # Provider APIs should use canonical endpoints. Arbitrary redirects
            # can bypass endpoint validation and create an SSRF redirect chain.
            follow_redirects=False,
        )
        self._owns_http = http_client is None
        self.health: dict[str, str] = {}

    async def close(self) -> None:
        if self._owns_http:
            await self.http.aclose()

    async def _post_with_retry(
        self,
        capability: str,
        url: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        if not url:
            raise CapabilityUnavailable(capability, f"{capability} URL 未配置")
        last_error: Exception | None = None
        with safe_span(
            "tool.http",
            **{"ophagent.capability": capability},
        ) as span:
            for attempt in range(self.config.MAX_RETRIES + 1):
                try:
                    response = await self.http.post(
                        url,
                        headers=headers,
                        json=json_body,
                        files=files,
                        data=data,
                    )
                    span.set_attribute("http.response.status_code", response.status_code)
                    span.set_attribute("ophagent.attempt", attempt + 1)
                    if response.status_code == 429 or response.status_code >= 500:
                        response.raise_for_status()
                    if response.status_code >= 400:
                        self.health[capability] = "unavailable"
                        raise CapabilityUnavailable(
                            capability,
                            f"{capability} 返回 HTTP {response.status_code}",
                        )
                    self.health[capability] = "ready"
                    return response
                except CapabilityUnavailable:
                    raise
                except (httpx.HTTPError, TimeoutError) as exc:
                    last_error = exc
                    if attempt < self.config.MAX_RETRIES:
                        await asyncio.sleep(min(0.25 * 2**attempt, 1.0))
        self.health[capability] = "unavailable"
        raise CapabilityUnavailable(capability, f"{capability} 请求失败：{last_error}")

    async def analyze_image(self, request: ImageAnalysisRequest) -> ToolResult:
        key = self.config.sub_model_key.get_secret_value()
        if not key or not self.config.sub_model_url or not self.config.sub_model_name:
            raise CapabilityUnavailable("sub_model", "多模态子模型未完整配置")

        content: list[dict[str, Any]] = [{"type": "text", "text": request.question}]
        image_ids = request.image_ids or [
            f"image_{index}"
            for index in range(1, len(request.image_paths) + 1)
        ]
        if len(image_ids) != len(request.image_paths):
            raise ValueError("image_ids 必须与 image_paths 一一对应")
        for raw_path, image_id in zip(
            request.image_paths,
            image_ids,
            strict=True,
        ):
            path = self.config.resolve_path(raw_path)
            if not path.is_file():
                raise CapabilityUnavailable("medical_image_analysis", f"影像文件不存在：{raw_path}")
            mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            content.append(
                {
                    "type": "text",
                    "text": f"下一张影像的唯一标识为 IMAGE_ID={image_id}",
                },
            )
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{encoded}"},
                },
            )

        region_contract = ""
        if request.request_regions:
            region_contract = (
                "如且仅如你能够从图像中可靠定位，请在 JSON 的 regions 数组给出"
                " image_id,label,x,y,width,height,coordinate_space,confidence；"
                "image_id 必须使用对应输入影像前声明的 IMAGE_ID；否则返回空数组。"
                "禁止猜测坐标或生成热图。"
            )
        prompt = (
            "你是研究级眼科多模态分析组件。只描述图像可见内容，区分观察、推测和未知；"
            "不得宣称确诊。输出严格 JSON：summary, observations[], limitations[],"
            " uncertainty, regions[]。"
            + region_contract
        )
        url = self.config.sub_model_url.rstrip("/") + "/chat/completions"
        response = await self._post_with_retry(
            "sub_model",
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json_body={
                "model": self.config.sub_model_name,
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": content},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
        )
        payload = response.json()
        raw = payload["choices"][0]["message"].get("content") or "{}"
        parsed = _parse_image_analysis_content(raw)
        valid_regions: list[dict[str, Any]] = []
        for region in parsed.get("regions", []):
            try:
                candidate = dict(region)
                if len(image_ids) == 1 and not candidate.get("image_id"):
                    candidate["image_id"] = image_ids[0]
                validated = ImageRegion.model_validate(candidate)
                if validated.image_id not in image_ids:
                    continue
                valid_regions.append(validated.model_dump())
            except ValueError:
                continue
        parsed["regions"] = valid_regions
        parsed["usage"] = payload.get("usage", {})
        self.health["medical_image_analysis"] = "ready"
        return ToolResult(status="ok", capability="medical_image_analysis", data=parsed)

    async def retrieve_medical_evidence(
        self,
        query: str,
        top_k: int = 6,
        *,
        user_id: int | None = None,
    ) -> ToolResult:
        evidence = await self.retriever.search(
            query,
            top_k=top_k,
            user_id=user_id,
        )
        self.health["medical_retrieval"] = "ready"
        return ToolResult(
            status="ok",
            capability="medical_retrieval",
            data={"evidence": [item.model_dump(mode="json") for item in evidence]},
        )

    async def search_web(self, request: SearchRequest) -> ToolResult:
        errors: list[str] = []
        if self.config.ANYSEARCH_URL and self.config.ANYSEARCH_API_KEY.get_secret_value():
            try:
                response = await self._post_with_retry(
                    "anysearch",
                    _with_default_path(self.config.ANYSEARCH_URL, "/v1/search"),
                    headers={
                        "Authorization": f"Bearer {self.config.ANYSEARCH_API_KEY.get_secret_value()}",
                        "Content-Type": "application/json",
                    },
                    json_body=request.model_dump(exclude_none=True),
                )
                return ToolResult(
                    status="ok",
                    capability="web_search",
                    data=self._normalize_search_payload(response.json(), "AnySearch"),
                )
            except (CapabilityUnavailable, ValueError, KeyError) as exc:
                errors.append(str(exc))

        if self.config.TAVILY_API_KEY.get_secret_value():
            try:
                response = await self._post_with_retry(
                    "tavily",
                    _with_default_path(self.config.TAVILY_URL, "/search"),
                    headers={"Content-Type": "application/json"},
                    json_body={
                        "api_key": self.config.TAVILY_API_KEY.get_secret_value(),
                        "query": request.query,
                        "max_results": request.max_results,
                        "search_depth": "advanced",
                    },
                )
                return ToolResult(
                    status="ok",
                    capability="web_search",
                    data=self._normalize_search_payload(response.json(), "Tavily"),
                )
            except (CapabilityUnavailable, ValueError, KeyError) as exc:
                errors.append(str(exc))

        raise CapabilityUnavailable(
            "web_search",
            "AnySearch 与 Tavily 均不可用" + (f"：{'；'.join(errors)}" if errors else ""),
        )

    @staticmethod
    def _normalize_search_payload(payload: dict[str, Any], provider: str) -> dict[str, Any]:
        candidates: Any = payload.get("results")
        if not candidates:
            data = payload.get("data")
            candidates = (
                data.get("results") or data.get("items") or []
                if isinstance(data, dict)
                else data or []
            )
        results: list[dict[str, Any]] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            url = candidate.get("url") or candidate.get("link")
            title = candidate.get("title") or url
            excerpt = candidate.get("content") or candidate.get("snippet") or candidate.get("description")
            if url and title and excerpt:
                results.append(
                    EvidenceItem(
                        title=str(title),
                        source=str(url),
                        excerpt=str(excerpt)[:2500],
                        score=float(candidate.get("score") or 0.0),
                        source_type="web",
                    ).model_dump(mode="json"),
                )
        return {"provider": provider, "evidence": results}

    async def parse_document(self, request: DocumentParseRequest) -> ToolResult:
        path = self.config.resolve_path(request.path)
        if not path.is_file():
            raise CapabilityUnavailable("document_parser", f"文档不存在：{request.path}")
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md"}:
            return ToolResult(
                status="ok",
                capability="document_parser",
                data={"text": path.read_text(encoding="utf-8", errors="ignore"), "parser": "local"},
            )
        if suffix == ".pdf" and self.config.MINERU_URL and self.config.MINERU_API_KEY.get_secret_value():
            with path.open("rb") as handle:
                response = await self._post_with_retry(
                    "mineru",
                    self.config.MINERU_URL,
                    headers={"Authorization": f"Bearer {self.config.MINERU_API_KEY.get_secret_value()}"},
                    files={"file": (path.name, handle, "application/pdf")},
                )
            return ToolResult(status="ok", capability="document_parser", data=response.json())
        if suffix == ".pdf":
            import fitz

            def extract_pdf() -> list[dict[str, Any]]:
                document = fitz.open(path)
                return [
                    {"page": index + 1, "text": page.get_text("text")}
                    for index, page in enumerate(document)
                ]

            pages = await asyncio.to_thread(extract_pdf)
            return ToolResult(
                status="ok",
                capability="document_parser",
                data={"pages": pages, "parser": "pymupdf", "visual_elements_preserved": False},
            )
        raise CapabilityUnavailable("document_parser", f"暂不支持的文档格式：{suffix}")

    async def transcribe(self, request: SpeechRequest) -> ToolResult:
        path = self.config.resolve_path(request.path)
        key = self.config.ASR_API_KEY.get_secret_value()
        if not path.is_file() or not key or not self.config.ASR_URL or not self.config.ASR_MODEL:
            raise CapabilityUnavailable("asr", "ASR 未配置或音频文件不存在")
        model = self.config.ASR_MODEL.strip()
        if model.startswith("fun-asr"):
            mime_type = mimetypes.guess_type(path.name)[0] or "audio/webm"
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            response = await self._post_with_retry(
                "asr",
                _dashscope_generation_endpoint(self.config.ASR_URL),
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "X-DashScope-SSE": "disable",
                },
                json_body={
                    "model": model,
                    "input": {
                        "messages": [{
                            "role": "user",
                            "content": [{
                                "type": "input_audio",
                                "input_audio": {"data": f"data:{mime_type};base64,{encoded}"},
                            }],
                        }]
                    },
                    "parameters": {"format": path.suffix.lower().lstrip(".") or "webm"},
                },
            )
            payload = response.json()
            output = payload.get("output") if isinstance(payload, dict) else None
            nested = output.get("output") if isinstance(output, dict) else None
            sentence = (
                nested.get("sentence") if isinstance(nested, dict)
                else output.get("sentence") if isinstance(output, dict)
                else None
            )
            text = (
                nested.get("text") if isinstance(nested, dict)
                else output.get("text") if isinstance(output, dict)
                else ""
            ) or (sentence.get("text") if isinstance(sentence, dict) else "")
            return ToolResult(
                status="ok",
                capability="asr",
                data={"text": str(text).strip(), "request_id": payload.get("request_id")},
            )
        with path.open("rb") as handle:
            response = await self._post_with_retry(
                "asr",
                _openai_audio_endpoint(self.config.ASR_URL, "transcriptions"),
                headers={"Authorization": f"Bearer {key}"},
                files={"file": (path.name, handle)},
                data={"model": model},
            )
        return ToolResult(status="ok", capability="asr", data=response.json())

    async def synthesize_speech(self, request: SynthesisRequest) -> ToolResult:
        key = self.config.TTS_API_KEY.get_secret_value()
        if not key or not self.config.TTS_URL or not self.config.TTS_MODEL:
            raise CapabilityUnavailable("tts", "TTS 未完整配置")
        model = self.config.TTS_MODEL.strip()
        if model.startswith("qwen3-tts"):
            response = await self._post_with_retry(
                "tts",
                _dashscope_generation_endpoint(self.config.TTS_URL),
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json_body={
                    "model": model,
                    "input": {
                        "text": request.text,
                        "voice": request.voice or "Cherry",
                        "language_type": "Chinese",
                    },
                },
            )
            payload = response.json()
            output = payload.get("output") if isinstance(payload, dict) else None
            audio_meta = output.get("audio") if isinstance(output, dict) else None
            encoded = audio_meta.get("data") if isinstance(audio_meta, dict) else ""
            if encoded:
                audio = base64.b64decode(encoded)
                mime_type = "audio/wav"
            else:
                audio_url = audio_meta.get("url") if isinstance(audio_meta, dict) else ""
                if not _trusted_dashscope_audio_url(audio_url):
                    raise CapabilityUnavailable("tts", "TTS 未返回可信的音频地址")
                audio_url = _force_https(audio_url)
                try:
                    audio_response = await self.http.get(audio_url)
                    audio_response.raise_for_status()
                except httpx.HTTPError as exc:
                    raise CapabilityUnavailable("tts", "TTS 音频下载失败") from exc
                audio = audio_response.content
                mime_type = audio_response.headers.get("content-type", "audio/wav").split(";", 1)[0]
            return ToolResult(
                status="ok",
                capability="tts",
                data={
                    "audio_base64": base64.b64encode(audio).decode("ascii"),
                    "mime_type": mime_type,
                },
            )
        response = await self._post_with_retry(
            "tts",
            _openai_audio_endpoint(self.config.TTS_URL, "speech"),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json_body={
                "model": model,
                "input": request.text,
                "voice": request.voice or "alloy",
            },
        )
        return ToolResult(
            status="ok",
            capability="tts",
            data={
                "audio_base64": base64.b64encode(response.content).decode("ascii"),
                "mime_type": response.headers.get("content-type", "audio/mpeg").split(";", 1)[0],
            },
        )

    @staticmethod
    def canonicalize_citations(answer: str, evidence: list[EvidenceItem]) -> str:
        """Expand only unambiguous evidence prefixes emitted by a provider.

        Some OpenAI-compatible models shorten long opaque IDs even when asked
        to copy them. A prefix is safe to repair only when it contains at
        least eight hexadecimal characters and maps to exactly one evidence
        item; unknown or ambiguous markers remain invalid.
        """
        known = {item.id for item in evidence}

        def replace(match):
            marker = match.group(1)
            if marker in known or len(marker.removeprefix("ev_")) < 8:
                return match.group(0)
            matches = [identifier for identifier in known if identifier.startswith(marker)]
            return f"[{matches[0]}]" if len(matches) == 1 else match.group(0)

        return re.sub(r"\[(ev_[0-9a-f]+)\]", replace, answer)

    @staticmethod
    def validate_citations(answer: str, evidence: list[EvidenceItem]) -> ToolResult:
        cited = {marker for marker in _citation_markers(answer)}
        known = {item.id for item in evidence}
        unknown = sorted(cited - known)
        claim_paragraphs = _medical_claim_paragraphs(answer)
        cited_claims = [
            paragraph for paragraph in claim_paragraphs
            if set(_citation_markers(paragraph)) & known
        ]
        coverage = (
            len(cited_claims) / len(claim_paragraphs)
            if claim_paragraphs
            else 1.0
        )
        uncited_claims = bool(evidence and claim_paragraphs and coverage < 0.6)
        return ToolResult(
            status="ok",
            capability="citation_verification",
            data={
                "valid": not unknown and not uncited_claims,
                "unknown_citations": unknown,
                "has_citations": bool(cited),
                "claim_paragraph_count": len(claim_paragraphs),
                "cited_claim_paragraph_count": len(cited_claims),
                "claim_coverage": round(coverage, 3),
            },
        )


def _citation_markers(text: str) -> list[str]:
    import re

    return re.findall(r"\[(ev_[0-9a-f]+)\]", text)


def _medical_claim_paragraphs(text: str) -> list[str]:
    """Approximate citation coverage without pretending to prove semantic entailment."""
    import re

    excluded = (
        "本系统用于研究级诊疗增强",
        "不能替代医生诊断",
        "不替代医生诊断",
        "检测到需要优先处理的红旗",
    )
    paragraphs: list[str] = []
    for raw in re.split(r"\n\s*\n", text):
        paragraph = raw.strip()
        if (
            not paragraph
            or paragraph.startswith(("#", ">", "⚠️"))
            or any(term in paragraph for term in excluded)
        ):
            continue
        paragraph = re.sub(r"^(?:[-*]|\d+[.)])\s*", "", paragraph)
        if len(paragraph) >= 16 and re.search(r"[\u4e00-\u9fff]", paragraph):
            paragraphs.append(paragraph)
    return paragraphs


def _with_default_path(url: str, default_path: str) -> str:
    """Append a documented endpoint when configuration contains only an origin."""
    parts = urlsplit(url)
    if parts.path not in {"", "/"}:
        return url
    return urlunsplit((parts.scheme, parts.netloc, default_path, parts.query, parts.fragment))


def _openai_audio_endpoint(url: str, operation: Literal["transcriptions", "speech"]) -> str:
    """Accept a complete audio endpoint or an OpenAI-compatible ``/v1`` base URL."""
    clean = url.rstrip("/")
    expected = f"/audio/{operation}"
    if clean.endswith(expected):
        return clean
    if clean.endswith("/v1"):
        return f"{clean}{expected}"
    return clean


def _dashscope_generation_endpoint(url: str) -> str:
    parts = urlsplit(url)
    path = "/api/v1/services/aigc/multimodal-generation/generation"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _trusted_dashscope_audio_url(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme in {"http", "https"} and host.endswith(
        (".aliyuncs.com", ".aliyuncs.com.cn"),
    )


def _force_https(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(("https", parts.netloc, parts.path, parts.query, parts.fragment))
