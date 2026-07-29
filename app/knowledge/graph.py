"""Evidence-backed lightweight ophthalmology graph.

The graph is generated from local document co-occurrence and never introduces
an unsupported diagnosis or treatment relation.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from collections.abc import Iterable

from pydantic import BaseModel, Field

from app.core.config import Settings, settings


class GraphNode(BaseModel):
    id: str
    label: str
    kind: str


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str = "co_occurs_in_source"
    evidence_sources: list[str] = Field(default_factory=list)
    weight: int = 1


ENTITY_TYPES: dict[str, tuple[str, ...]] = {
    "disease": (
        "青光眼",
        "白内障",
        "近视",
        "黄斑变性",
        "糖尿病视网膜病变",
        "干眼",
        "葡萄膜炎",
        "视网膜脱离",
        "角膜炎",
        "弱视",
        "斜视",
    ),
    "symptom": ("视力下降", "视物模糊", "眼痛", "畏光", "飞蚊", "复视", "红眼"),
    "test": ("OCT", "眼压", "眼底照相", "视野", "裂隙灯", "荧光素血管造影"),
    "treatment": ("激光", "手术", "玻璃体内注射", "药物治疗"),
    "risk_factor": ("糖尿病", "高血压", "高度近视", "早产"),
    "referral": ("急诊", "转诊", "随访"),
}


def _node_id(kind: str, label: str) -> str:
    import hashlib

    return f"{kind}_{hashlib.sha1(label.encode('utf-8')).hexdigest()[:12]}"


class OphthaGraph:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self.path = config.resolve_path(config.KNOWLEDGE_INDEX_DIR) / "ophtha_graph.json"
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text("utf-8"))
            self.nodes = {
                item["id"]: GraphNode.model_validate(item)
                for item in payload.get("nodes", [])
            }
            self.edges = [GraphEdge.model_validate(item) for item in payload.get("edges", [])]
        except (OSError, ValueError, TypeError):
            self.nodes, self.edges = {}, []

    def build(self, sources: Iterable[tuple[str, str]]) -> None:
        """Build supported co-occurrence edges from ``(source, text)`` pairs."""
        node_map: dict[str, GraphNode] = {}
        edge_sources: dict[tuple[str, str], set[str]] = defaultdict(set)
        edge_counts: Counter[tuple[str, str]] = Counter()
        for source, text in sources:
            found: list[GraphNode] = []
            lowered = text.lower()
            for kind, labels in ENTITY_TYPES.items():
                for label in labels:
                    if label.lower() in lowered:
                        node = GraphNode(id=_node_id(kind, label), label=label, kind=kind)
                        node_map[node.id] = node
                        found.append(node)
            unique = sorted({node.id for node in found})
            for index, left in enumerate(unique):
                for right in unique[index + 1 :]:
                    edge_counts[(left, right)] += 1
                    if len(edge_sources[(left, right)]) < 12:
                        edge_sources[(left, right)].add(source)
        edges = [
            GraphEdge(
                source=left,
                target=right,
                evidence_sources=sorted(edge_sources[(left, right)]),
                weight=count,
            )
            for (left, right), count in edge_counts.items()
        ]
        self.nodes, self.edges = node_map, edges
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "nodes": [item.model_dump() for item in node_map.values()],
                    "edges": [item.model_dump() for item in edges],
                },
                ensure_ascii=False,
                indent=2,
            ),
            "utf-8",
        )
        os.replace(temporary, self.path)

    def expand(self, query: str, limit: int = 5) -> list[str]:
        matched = {
            node_id
            for node_id, node in self.nodes.items()
            if node.label.lower() in query.lower()
        }
        candidates: Counter[str] = Counter()
        for edge in self.edges:
            if edge.source in matched and edge.target not in matched:
                candidates[edge.target] += edge.weight
            elif edge.target in matched and edge.source not in matched:
                candidates[edge.source] += edge.weight
        return [
            self.nodes[node_id].label
            for node_id, _ in candidates.most_common(limit)
            if node_id in self.nodes
        ]

    def status(self) -> tuple[int, int]:
        return len(self.nodes), len(self.edges)
