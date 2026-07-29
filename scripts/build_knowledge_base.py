#!/usr/bin/env python3
"""Portable knowledge-corpus import and index management CLI."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings  # noqa: E402
from app.knowledge import HybridKnowledgeRetriever  # noqa: E402

SUPPORTED_SUFFIXES = {".md", ".txt", ".pdf"}


@dataclass(frozen=True, slots=True)
class SourceSpec:
    name: str
    path: Path


def parse_source(value: str) -> SourceSpec:
    """Parse NAME=PATH without assuming a developer-specific directory layout."""
    name, separator, raw_path = value.partition("=")
    if not separator or not name.strip() or not raw_path.strip():
        raise argparse.ArgumentTypeError("来源格式应为 NAME=PATH")
    path = Path(raw_path).expanduser().resolve()
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"来源目录不存在：{path}")
    return SourceSpec(name=name.strip(), path=path)


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_name(value: str) -> str:
    normalized = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("._")
    return normalized or "source"


def collect_documents(
    sources: list[SourceSpec],
    target_dir: Path,
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Copy supported files into the configured raw corpus with checksum dedupe."""
    if not sources:
        raise ValueError("--collect 至少需要一个 --source NAME=PATH")
    target_dir.mkdir(parents=True, exist_ok=True)
    known = {
        _checksum(path)
        for path in target_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    }
    imported = 0
    skipped = 0
    for source in sources:
        for path in sorted(source.path.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            checksum = _checksum(path)
            if checksum in known:
                skipped += 1
                continue
            relative = path.relative_to(source.path)
            stem = _safe_name(f"{source.name}_{relative.with_suffix('')}")
            destination = target_dir / f"{stem}{path.suffix.lower()}"
            counter = 2
            while destination.exists():
                destination = target_dir / f"{stem}_{counter}{path.suffix.lower()}"
                counter += 1
            if not dry_run:
                temporary = destination.with_suffix(destination.suffix + ".tmp")
                shutil.copyfile(path, temporary)
                os.replace(temporary, destination)
            known.add(checksum)
            imported += 1
    return imported, skipped


async def rebuild_index(include_embeddings: bool) -> None:
    retriever = HybridKnowledgeRetriever(settings)
    status = await retriever.rebuild(include_embeddings=include_embeddings)
    print(status.model_dump_json(indent=2))


async def search_index(query: str, top_k: int) -> None:
    retriever = HybridKnowledgeRetriever(settings)
    evidence = await retriever.search(query, top_k=top_k)
    for index, item in enumerate(evidence, start=1):
        print(f"[{index}] {item.title} · {item.locator} · score={item.score:.3f}")
        print(item.excerpt[:300].replace("\n", " "))


async def show_status() -> None:
    retriever = HybridKnowledgeRetriever(settings)
    status = await retriever.load()
    print(status.model_dump_json(indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OphAgent 知识语料与混合索引管理")
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        type=parse_source,
        metavar="NAME=PATH",
        help="待导入语料目录；可重复指定，不再依赖本机固定路径",
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--collect", action="store_true", help="把来源语料导入 raw 目录")
    action.add_argument("--build-index", action="store_true", help="重建 BM25/图谱/可选向量索引")
    action.add_argument("--search", metavar="QUERY", help="检索当前知识索引")
    action.add_argument("--stats", action="store_true", help="显示当前索引状态")
    parser.add_argument("--top-k", type=int, default=5, help="检索返回数量")
    parser.add_argument(
        "--lexical-only",
        action="store_true",
        help="只构建 BM25 与图谱索引，不调用 Embedding 服务",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅统计待导入文件")
    return parser


async def async_main(args: argparse.Namespace) -> None:
    if args.collect:
        imported, skipped = collect_documents(
            args.source,
            settings.resolve_path(settings.KNOWLEDGE_RAW_DIR),
            dry_run=args.dry_run,
        )
        print(f"待导入/已导入 {imported} 个文件，按内容跳过 {skipped} 个重复文件")
    elif args.build_index:
        await rebuild_index(include_embeddings=not args.lexical_only)
    elif args.search:
        await search_index(args.search, max(1, args.top_k))
    else:
        await show_status()


def main() -> None:
    asyncio.run(async_main(build_parser().parse_args()))


if __name__ == "__main__":
    main()
