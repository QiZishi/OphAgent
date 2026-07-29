#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_root="${MEDICAL_AGENT_HUST_ROOT:-}"
python_bin="${OPHAGENT_PYTHON:-${project_dir}/venv/bin/python}"

if [[ -z "${source_root}" ]]; then
  echo "请通过 MEDICAL_AGENT_HUST_ROOT 指定官方演化源码根目录" >&2
  exit 2
fi

manifest="${source_root}/evolution/upstream/SOURCE_MANIFEST.yaml"
a_evolve_source="${source_root}/evolution/upstream/a_evolve"
gepa_source="${source_root}/evolution/upstream/gepa"

if [[ ! -f "${manifest}" || ! -f "${a_evolve_source}/pyproject.toml" || ! -f "${gepa_source}/pyproject.toml" ]]; then
  echo "官方演化源码或 SOURCE_MANIFEST.yaml 不完整：${source_root}" >&2
  exit 1
fi

uv pip install \
  --reinstall \
  --python "${python_bin}" \
  "${a_evolve_source}" \
  "${gepa_source}" \
  "cloudpickle>=3.0,<4"

"${python_bin}" - <<'PY'
from importlib import metadata, util

expected = {
    "a-evolve": ("0.1.0", "agent_evolve"),
    "gepa": ("0.1.1", "gepa"),
}
for distribution, (version, module) in expected.items():
    installed = metadata.version(distribution)
    if installed != version or util.find_spec(module) is None:
        raise SystemExit(
            f"{distribution} 安装校验失败：expected={version}, installed={installed}"
        )
    print(f"{distribution} {installed}: ready")
PY
