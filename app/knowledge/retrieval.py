"""Guideline-first hybrid retrieval with persistent vectors and page evidence."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from app.core.config import Settings, settings
from app.domain.models import EvidenceItem, KnowledgeIndexStatus, KnowledgeSource
from app.knowledge.graph import OphthaGraph
from app.knowledge.sources import SourceRegistry, portable_path

TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9]+")
LOW_TRUST_SOURCE_MARKERS = (
    "baidubaike_",
    "xywy_",
    "dxy_",
    "百度百科",
    "寻医问药",
)
PRIMARY_SOURCE_MARKERS = (
    "指南",
    "专家共识",
    "诊疗规范",
    "clinical practice guideline",
    "preferred practice pattern",
    " ppp",
)


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


@dataclass(slots=True)
class Chunk:
    id: str
    source_id: str
    title: str
    source: str
    locator: str
    text: str
    terms: Counter[str]
    visual_path: str | None = None

    def serialize(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "title": self.title,
            "source": self.source,
            "locator": self.locator,
            "text": self.text,
            "visual_path": self.visual_path,
        }

    @classmethod
    def deserialize(cls, value: dict[str, Any]) -> Chunk:
        text = str(value["text"])
        return cls(
            id=str(value["id"]),
            source_id=str(value["source_id"]),
            title=str(value["title"]),
            source=str(value["source"]),
            locator=str(value["locator"]),
            text=text,
            terms=Counter(tokenize(text)),
            visual_path=value.get("visual_path"),
        )


class HybridKnowledgeRetriever:
    """BM25 + BGE-M3 vector recall + optional rerank.

    A missing embedding service degrades to genuine BM25. It never falls back
    to model memory or synthetic evidence.
    """

    SCHEMA_VERSION = 3

    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self.index_dir = config.resolve_path(config.KNOWLEDGE_INDEX_DIR)
        self.chunk_path = self.index_dir / "chunks.jsonl"
        self.vector_path = self.index_dir / "vectors.npy"
        self.manifest_path = self.index_dir / "manifest.json"
        self.registry = SourceRegistry(config)
        self.graph = OphthaGraph(config)
        self._chunks: list[Chunk] | None = None
        self._sources: dict[str, KnowledgeSource] = {}
        self._document_frequency: Counter[str] = Counter()
        self._average_length = 1.0
        self._vectors: np.ndarray | None = None
        self._manifest: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._last_embedding_error: str | None = None
        self._embedding_ready: bool | None = None
        self._rerank_ready: bool | None = None
        self._building = False

    async def _ensure_index(self) -> None:
        if self._chunks is not None:
            return
        async with self._lock:
            if self._chunks is not None:
                return
            await asyncio.to_thread(self._load_or_build_lexical_index)

    async def load(self) -> KnowledgeIndexStatus:
        """Load or build the lexical index and return its current status."""
        await self._ensure_index()
        return self.status()

    def invalidate(self) -> None:
        """Drop process-local caches after source import or lifecycle changes."""
        self._chunks = None
        self._sources = {}
        self._vectors = None
        self._manifest = {}

    def _corpus_fingerprint(self, sources: list[KnowledgeSource]) -> str:
        payload = [
            (item.path, item.checksum, item.status, item.version, item.superseded_by)
            for item in sources
        ]
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        ).hexdigest()

    def _load_or_build_lexical_index(self) -> None:
        # Build one physical index, then enforce source ownership before
        # ranking results. Public sources remain available to every user.
        sources = self.registry.list(include_private=True)
        self._sources = {item.id: item for item in sources}
        fingerprint = self._corpus_fingerprint(sources)
        manifest: dict[str, Any] = {}
        if self.manifest_path.exists():
            try:
                manifest = json.loads(self.manifest_path.read_text("utf-8"))
            except (OSError, ValueError):
                manifest = {}
        reusable = (
            manifest.get("schema_version") == self.SCHEMA_VERSION
            and manifest.get("fingerprint") == fingerprint
            and self.chunk_path.is_file()
        )
        if reusable:
            chunks = []
            for line in self.chunk_path.read_text("utf-8").splitlines():
                try:
                    chunks.append(Chunk.deserialize(json.loads(line)))
                except (KeyError, TypeError, ValueError):
                    continue
            self._chunks = chunks
            self._manifest = manifest
            self._load_vectors()
        else:
            self._chunks = self._build_chunks(sources)
            self._vectors = None
            if self.vector_path.exists():
                self.vector_path.unlink()
            self._manifest = {
                "schema_version": self.SCHEMA_VERSION,
                "fingerprint": fingerprint,
                "built_at": datetime.now(UTC).isoformat(),
                "documents": len(sources),
                "chunks": len(self._chunks),
                "page_visuals": sum(bool(item.visual_path) for item in self._chunks),
                "vectors": 0,
                "embedding_model": None,
            }
            self._persist_chunks()
            self._persist_manifest()
            self.graph.build((chunk.source, chunk.text) for chunk in self._chunks)
        self._rebuild_lexical_statistics()

    def _load_vectors(self) -> None:
        self._vectors = None
        if not self.vector_path.is_file():
            return
        try:
            vectors = np.load(self.vector_path, allow_pickle=False)
            if (
                vectors.ndim == 2
                and self._chunks is not None
                and vectors.shape[0] == len(self._chunks)
            ):
                self._vectors = self._normalize(vectors.astype(np.float32))
        except (OSError, ValueError):
            self._vectors = None

    def _build_chunks(self, sources: list[KnowledgeSource]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for source in sources:
            path = self.config.resolve_path(source.path)
            if not path.is_file():
                continue
            if path.suffix.lower() in {".md", ".txt"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
                chunks.extend(self._chunk_text(source, text))
            elif path.suffix.lower() == ".pdf":
                chunks.extend(self._chunk_pdf(source, path))
        return chunks

    def _chunk_text(
        self,
        source: KnowledgeSource,
        text: str,
        *,
        locator_prefix: str = "段落",
        visual_path: str | None = None,
    ) -> list[Chunk]:
        chunks: list[Chunk] = []
        paragraphs = [
            part.strip()
            for part in re.split(r"\n{2,}", text)
            if len(part.strip()) >= 20
        ]
        chunk_size = max(self.config.KNOWLEDGE_CHUNK_SIZE, 200)
        overlap = min(max(self.config.KNOWLEDGE_CHUNK_OVERLAP, 0), chunk_size // 2)
        step = chunk_size - overlap
        for paragraph_index, paragraph in enumerate(paragraphs, start=1):
            for start in range(0, len(paragraph), step):
                body = paragraph[start : start + chunk_size]
                terms = Counter(tokenize(body))
                if not terms:
                    continue
                locator = f"{locator_prefix} {paragraph_index}"
                if start:
                    locator += f"（续 {start // step + 1}）"
                stable = hashlib.sha1(
                    f"{source.id}:{locator}:{start}:{body[:80]}".encode(),
                ).hexdigest()[:20]
                chunks.append(
                    Chunk(
                        id=f"chk_{stable}",
                        source_id=source.id,
                        title=source.title,
                        source=source.path,
                        locator=locator,
                        text=body,
                        terms=terms,
                        visual_path=visual_path,
                    ),
                )
        return chunks

    def _chunk_pdf(self, source: KnowledgeSource, path: Path) -> list[Chunk]:
        import fitz

        document = fitz.open(path)
        output: list[Chunk] = []
        image_dir = self.index_dir / "page_visuals" / source.id
        image_dir.mkdir(parents=True, exist_ok=True)
        for index, page in enumerate(document):
            page_number = index + 1
            image_path = image_dir / f"page_{page_number:04d}.png"
            if not image_path.exists():
                pixmap = page.get_pixmap(matrix=fitz.Matrix(1.25, 1.25), alpha=False)
                pixmap.save(image_path)
            relative_image = portable_path(image_path, self.config)
            text = page.get_text("text").strip()
            if len(text) < 40:
                text = f"PDF 页面 {page_number}：文本层不足，请结合页图复核。"
            output.extend(
                self._chunk_text(
                    source,
                    text,
                    locator_prefix=f"第 {page_number} 页，段落",
                    visual_path=relative_image,
                ),
            )
        document.close()
        return output

    def _persist_chunks(self) -> None:
        assert self._chunks is not None
        self.index_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.chunk_path.with_suffix(".tmp")
        temporary.write_text(
            "\n".join(
                json.dumps(chunk.serialize(), ensure_ascii=False)
                for chunk in self._chunks
            ),
            "utf-8",
        )
        os.replace(temporary, self.chunk_path)

    def _persist_manifest(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.manifest_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self._manifest, ensure_ascii=False, indent=2),
            "utf-8",
        )
        os.replace(temporary, self.manifest_path)

    def _rebuild_lexical_statistics(self) -> None:
        assert self._chunks is not None
        self._document_frequency.clear()
        for chunk in self._chunks:
            self._document_frequency.update(chunk.terms.keys())
        if self._chunks:
            self._average_length = (
                sum(sum(chunk.terms.values()) for chunk in self._chunks) / len(self._chunks)
            )

    async def rebuild(self, *, include_embeddings: bool = True) -> KnowledgeIndexStatus:
        self._building = True
        try:
            async with self._lock:
                self._chunks = None
                await asyncio.to_thread(self._load_or_build_lexical_index)
                if include_embeddings and self._chunks:
                    texts = [chunk.text for chunk in self._chunks]
                    vectors = await self._embed(texts)
                    matrix = self._normalize(np.asarray(vectors, dtype=np.float32))
                    temporary = self.vector_path.with_suffix(".tmp.npy")
                    np.save(temporary, matrix, allow_pickle=False)
                    os.replace(temporary, self.vector_path)
                    self._vectors = matrix
                    self._manifest.update(
                        {
                            "vectors": len(matrix),
                            "embedding_model": self.config.EMBEDDING_MODEL,
                            "built_at": datetime.now(UTC).isoformat(),
                        },
                    )
                    self._persist_manifest()
        finally:
            self._building = False
        return self.status()

    async def search(
        self,
        query: str,
        top_k: int = 6,
        *,
        user_id: int | None = None,
    ) -> list[EvidenceItem]:
        await self._ensure_index()
        assert self._chunks is not None
        query_terms = tokenize(query)
        if not query_terms or all(term.isdigit() for term in query_terms):
            return []
        expansions = self.graph.expand(query)
        limit = max(top_k * 8, self.config.KNOWLEDGE_VECTOR_CANDIDATES)
        lexical = self._bm25(query, limit)
        candidates: dict[int, float] = {
            index: self._normalize_rank_score(score, lexical[0][0] if lexical else 1.0)
            for score, index in lexical
        }
        if expansions:
            expanded = self._bm25(" ".join(expansions), limit)
            maximum = expanded[0][0] if expanded else 1.0
            for score, index in expanded:
                candidates[index] = max(
                    candidates.get(index, 0.0),
                    0.15 * self._normalize_rank_score(score, maximum),
                )
        vector_scores = await self._vector_scores(query, [index for _, index in lexical])
        for index, score in vector_scores.items():
            candidates[index] = 0.45 * candidates.get(index, 0.0) + 0.55 * score
        ordered = sorted(
            ((score, self._chunks[index]) for index, score in candidates.items()),
            key=lambda item: item[0],
            reverse=True,
        )
        ordered = self._filter_source_access(ordered, user_id=user_id)
        ordered = self._filter_source_lifecycle(ordered)
        quality_ordered = sorted(
            (
                (self._quality_adjusted_score(score, chunk), chunk)
                for score, chunk in ordered
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        reranked = await self._rerank(
            query,
            quality_ordered[: max(top_k * 4, 20)],
        )
        reranked = sorted(
            (
                (self._quality_adjusted_score(score, chunk), chunk)
                for score, chunk in reranked
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        minimum = self.config.KNOWLEDGE_MIN_RELEVANCE
        selected: list[EvidenceItem] = []
        low_trust_fallbacks: list[tuple[float, Chunk]] = []
        seen_sources: set[str] = set()
        for score, chunk in reranked:
            if score < minimum or chunk.source_id in seen_sources:
                continue
            overlap = set(query_terms).intersection(chunk.terms)
            if not overlap:
                continue
            if self._is_low_trust(chunk):
                low_trust_fallbacks.append((score, chunk))
                continue
            selected.append(self._to_evidence(score, chunk))
            seen_sources.add(chunk.source_id)
            if len(selected) >= top_k:
                break
        if not selected:
            for score, chunk in low_trust_fallbacks[:top_k]:
                selected.append(self._to_evidence(score, chunk))
        return selected

    def _bm25(self, query: str, limit: int) -> list[tuple[float, int]]:
        assert self._chunks is not None
        query_terms = tokenize(query)
        if not query_terms:
            return []
        n_docs = max(len(self._chunks), 1)
        k1, b = 1.5, 0.75
        scored: list[tuple[float, int]] = []
        for index, chunk in enumerate(self._chunks):
            length = sum(chunk.terms.values())
            score = 0.0
            for term in query_terms:
                tf = chunk.terms.get(term, 0)
                if not tf:
                    continue
                df = self._document_frequency.get(term, 0)
                inverse = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
                denominator = tf + k1 * (1 - b + b * length / self._average_length)
                score += inverse * tf * (k1 + 1) / denominator
            if score:
                scored.append((score, index))
        return sorted(scored, reverse=True)[:limit]

    async def _vector_scores(
        self,
        query: str,
        lexical_indices: list[int],
    ) -> dict[int, float]:
        key = self.config.embedding_key.get_secret_value()
        if not key or not self.config.EMBEDDING_MODEL:
            return {}
        assert self._chunks is not None
        try:
            query_vector = self._normalize(
                np.asarray(await self._embed([query]), dtype=np.float32),
            )[0]
            if self._vectors is not None:
                scores = self._vectors @ query_vector
                count = min(
                    max(self.config.KNOWLEDGE_VECTOR_CANDIDATES, 1),
                    len(scores),
                )
                indices = np.argpartition(scores, -count)[-count:]
                return {
                    int(index): max(0.0, min(1.0, (float(scores[index]) + 1) / 2))
                    for index in indices
                }
            if not lexical_indices:
                return {}
            texts = [self._chunks[index].text for index in lexical_indices]
            candidate_vectors = self._normalize(
                np.asarray(await self._embed(texts), dtype=np.float32),
            )
            similarities = candidate_vectors @ query_vector
            return {
                index: max(0.0, min(1.0, (float(score) + 1) / 2))
                for index, score in zip(lexical_indices, similarities, strict=True)
            }
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            self._last_embedding_error = type(exc).__name__
            self._embedding_ready = False
            return {}

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        key = self.config.embedding_key.get_secret_value()
        if not key or not self.config.EMBEDDING_MODEL:
            raise ValueError("embedding capability unavailable")
        url = self.config.embedding_url.rstrip("/") + "/embeddings"
        output: list[list[float]] = []
        batch_size = max(1, self.config.KNOWLEDGE_EMBED_BATCH_SIZE)
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.config.REQUEST_TIMEOUT_SECONDS),
        ) as client:
            for start in range(0, len(texts), batch_size):
                response: httpx.Response | None = None
                for attempt in range(self.config.MAX_RETRIES + 1):
                    try:
                        response = await client.post(
                            url,
                            headers={
                                "Authorization": f"Bearer {key}",
                                "Content-Type": "application/json",
                            },
                            json={
                                "model": self.config.EMBEDDING_MODEL,
                                "input": texts[start : start + batch_size],
                                "encoding_format": "float",
                            },
                        )
                        response.raise_for_status()
                        break
                    except httpx.HTTPError:
                        if attempt >= self.config.MAX_RETRIES:
                            raise
                        await asyncio.sleep(min(0.25 * 2**attempt, 1.0))
                assert response is not None
                items = sorted(response.json()["data"], key=lambda item: item["index"])
                output.extend([item["embedding"] for item in items])
        self._embedding_ready = True
        return output

    @staticmethod
    def _normalize(matrix: np.ndarray) -> np.ndarray:
        denominators = np.linalg.norm(matrix, axis=1, keepdims=True)
        denominators[denominators == 0] = 1
        return matrix / denominators

    @staticmethod
    def _normalize_rank_score(score: float, maximum: float) -> float:
        return max(0.0, min(1.0, score / maximum if maximum else 0.0))

    def _filter_source_lifecycle(
        self,
        candidates: list[tuple[float, Chunk]],
    ) -> list[tuple[float, Chunk]]:
        if self.config.KNOWLEDGE_ALLOW_EXPIRED:
            return candidates
        return [
            item
            for item in candidates
            if self._sources.get(item[1].source_id, KnowledgeSource(
                id="missing",
                title=item[1].title,
                path=item[1].source,
            )).status not in {"expired", "superseded"}
        ]

    def _filter_source_access(
        self,
        candidates: list[tuple[float, Chunk]],
        *,
        user_id: int | None,
    ) -> list[tuple[float, Chunk]]:
        return [
            item
            for item in candidates
            if (
                (source := self._sources.get(item[1].source_id)) is not None
                and (source.imported_by is None or source.imported_by == user_id)
            )
        ]

    def _to_evidence(self, score: float, chunk: Chunk) -> EvidenceItem:
        source = self._sources.get(chunk.source_id)
        low_trust = self._is_low_trust(chunk)
        return EvidenceItem(
            title=chunk.title,
            source=chunk.source,
            excerpt=chunk.text,
            locator=chunk.locator,
            published_at=source.published_at if source else None,
            region=source.region if source else None,
            institution=source.institution if source else None,
            version=source.version if source else None,
            population=source.population if source else None,
            source_status=source.status if source else "unknown",
            superseded_by=source.superseded_by if source else None,
            visual_path=chunk.visual_path,
            score=max(0.0, min(1.0, score)),
            source_type=(
                "record"
                if low_trust
                else source.source_type if source else "guideline"
            ),
            verified=(source.verified if source else False) and not low_trust,
        )

    def _quality_adjusted_score(self, score: float, chunk: Chunk) -> float:
        source = self._sources.get(chunk.source_id)
        title = chunk.title.lower()
        if self._is_low_trust(chunk):
            return score * 0.18
        if any(marker in title for marker in PRIMARY_SOURCE_MARKERS):
            return score * 1.18
        if source and source.source_type == "user":
            return score * (1.0 if source.verified else 0.72)
        if source and source.verified:
            return score * 1.05
        return score * 0.82

    @staticmethod
    def _is_low_trust(chunk: Chunk) -> bool:
        identity = f"{chunk.title} {chunk.source}".lower()
        return any(marker in identity for marker in LOW_TRUST_SOURCE_MARKERS)

    async def _rerank(
        self,
        query: str,
        candidates: list[tuple[float, Chunk]],
    ) -> list[tuple[float, Chunk]]:
        key = self.config.rerank_key.get_secret_value()
        if not key or not self.config.RERANK_MODEL or not candidates:
            return candidates
        url = self.config.rerank_url.rstrip("/") + "/rerank"
        try:
            async with httpx.AsyncClient(
                timeout=self.config.REQUEST_TIMEOUT_SECONDS,
            ) as client:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.config.RERANK_MODEL,
                        "query": query,
                        "documents": [chunk.text for _, chunk in candidates],
                        "top_n": len(candidates),
                        "return_documents": False,
                    },
                )
                response.raise_for_status()
                rankings = response.json().get("results", [])
                reranked = [
                    (
                        max(0.0, float(item["relevance_score"])),
                        candidates[int(item["index"])][1],
                    )
                    for item in rankings
                ]
                self._rerank_ready = True
                return reranked or candidates
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            self._rerank_ready = False
            return candidates

    def status(self) -> KnowledgeIndexStatus:
        chunks = self._chunks or []
        nodes, edges = self.graph.status()
        current_sources = self.registry.list()
        sources = self._sources or {item.id: item for item in current_sources}
        stale = bool(
            self._manifest
            and self._manifest.get("fingerprint")
            != self._corpus_fingerprint(current_sources)
        )
        return KnowledgeIndexStatus(
            status="building" if self._building else ("ready" if chunks else "unavailable"),
            documents=len(sources),
            chunks=len(chunks),
            page_visuals=sum(bool(item.visual_path) for item in chunks),
            vectors=len(self._vectors) if self._vectors is not None else 0,
            embedding_model=self._manifest.get("embedding_model"),
            graph_nodes=nodes,
            graph_edges=edges,
            stale=stale,
            built_at=self._manifest.get("built_at"),
            detail=(
                f"embedding 最近一次降级：{self._last_embedding_error}"
                if self._last_embedding_error
                else None
            ),
        )
