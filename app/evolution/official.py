"""Thin adapters to official evolution projects.

No local optimizer is substituted when an optional official package is absent.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.core.config import Settings, settings


class OfficialEvolutionUnavailable(RuntimeError):
    pass


class OfficialEvolverRegistry:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config

    def status(self) -> dict[str, dict[str, Any]]:
        adaptive_root = (
            self.config.resolve_path(self.config.ADAPTIVE_HARNESS_ROOT)
            if self.config.ADAPTIVE_HARNESS_ROOT
            else None
        )
        return {
            "a-evolve": {
                "available": importlib.util.find_spec("agent_evolve") is not None,
                "module": "agent_evolve",
                "official": "https://github.com/A-EVO-Lab/a-evolve",
            },
            "gepa": {
                "available": importlib.util.find_spec("gepa") is not None,
                "module": "gepa",
                "official": "https://github.com/gepa-ai/gepa",
            },
            "adaptive-auto-harness": {
                "available": bool(
                    adaptive_root
                    and (adaptive_root / "solve_all_with_evolution.py").is_file()
                    and (adaptive_root / "agent_evolve").is_dir()
                ),
                "root": str(adaptive_root) if adaptive_root else None,
                "official": (
                    "https://github.com/A-EVO-Lab/a-evolve/"
                    "tree/release/adaptive-auto-harness"
                ),
            },
        }

    def run_a_evolve(
        self,
        *,
        agent: str | object,
        benchmark: str | object,
        cycles: int,
        **kwargs: Any,
    ) -> Any:
        if not self.status()["a-evolve"]["available"]:
            raise OfficialEvolutionUnavailable(
                "官方 a-evolve 未安装；请使用 requirements-evolution.txt",
            )
        import agent_evolve as ae

        evolver = ae.Evolver(agent=agent, benchmark=benchmark, **kwargs)
        return evolver.run(cycles=cycles)

    def run_gepa(
        self,
        *,
        seed_candidate: dict[str, str],
        trainset: list[Any],
        valset: list[Any],
        evaluator: Callable[..., Any],
        **kwargs: Any,
    ) -> Any:
        if not self.status()["gepa"]["available"]:
            raise OfficialEvolutionUnavailable(
                "官方 gepa 未安装；请使用 requirements-evolution.txt",
            )
        import gepa

        return gepa.optimize(
            seed_candidate=seed_candidate,
            trainset=trainset,
            valset=valset,
            evaluator=evaluator,
            **kwargs,
        )

    def run_adaptive(self, arguments: list[str], timeout_seconds: int = 86_400) -> subprocess.CompletedProcess:
        state = self.status()["adaptive-auto-harness"]
        if not state["available"]:
            raise OfficialEvolutionUnavailable(
                "官方 Adaptive Auto-Harness release branch 未配置",
            )
        root = Path(str(state["root"]))
        if any("\x00" in argument for argument in arguments):
            raise ValueError("非法 Adaptive Harness 参数")
        return subprocess.run(
            [sys.executable, "solve_all_with_evolution.py", *arguments],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
