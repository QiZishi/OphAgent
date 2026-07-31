#!/bin/sh
# ModelScope Studio 数据持久化入口。
#
# ModelScope 容器重启后默认丢数据；/mnt/workspace 是平台保留的持久化目录。
# 本脚本：
#   1. 探测 /mnt/workspace 是否已挂载且可写（FUSE 可能就绪较慢）；
#   2. 可用 -> 把所有运行时数据路径（SQLite、上传、记忆、技能、知识库、
#      进化状态等）指向 /mnt/workspace/ophagent 下，并预建目录；
#      幂等生成进化门禁密钥文件（已存在则保留）。
#   3. 不可用 -> 告警并回退容器内路径（数据重启后丢失）。
# 最后 exec 主进程，保证 SIGTERM/SIGINT 转发。

set -eu

PERSIST_BASE="/mnt/workspace/ophagent"

probe() {
    mkdir -p "${PERSIST_BASE}/probe" 2>/dev/null || return 1
    echo ok > "${PERSIST_BASE}/probe/.writable" 2>/dev/null || return 1
    rm -rf "${PERSIST_BASE}/probe" 2>/dev/null
}

if probe; then
    echo "PERSIST: /mnt/workspace writable, runtime data at ${PERSIST_BASE}"

    export DATABASE_URL="sqlite:///${PERSIST_BASE}/db/ophagent_pro.db"
    export UPLOAD_DIR="${PERSIST_BASE}/uploads"
    export ATTACHMENT_DIR="${PERSIST_BASE}/attachments"
    export ARTIFACT_DIR="${PERSIST_BASE}/artifacts"
    export RUNTIME_STATE_DIR="${PERSIST_BASE}/runtime/runs"
    export MEMORY_STATE_PATH="${PERSIST_BASE}/runtime/memories.json"
    export MEMORY_PREFERENCE_PATH="${PERSIST_BASE}/runtime/memory_preferences.json"
    export SKILL_STATE_PATH="${PERSIST_BASE}/runtime/skills.json"
    export SKILL_EVALUATION_DIR="${PERSIST_BASE}/runtime/skill_evaluations"
    export EVOLUTION_STATE_DIR="${PERSIST_BASE}/evolution"
    export EVOLUTION_WORKTREE_DIR="${PERSIST_BASE}/.worktrees/evolution"
    export EVOLUTION_GATE_SECRET_FILE="${PERSIST_BASE}/evolution/gate_secret"
    export KNOWLEDGE_RAW_DIR="${PERSIST_BASE}/knowledge/raw"
    export KNOWLEDGE_INDEX_DIR="${PERSIST_BASE}/knowledge/index"

    mkdir -p \
        "${PERSIST_BASE}/db" \
        "${PERSIST_BASE}/uploads" \
        "${PERSIST_BASE}/attachments" \
        "${PERSIST_BASE}/artifacts" \
        "${PERSIST_BASE}/runtime/runs" \
        "${PERSIST_BASE}/runtime/skill_evaluations" \
        "${PERSIST_BASE}/evolution" \
        "${PERSIST_BASE}/.worktrees" \
        "${PERSIST_BASE}/knowledge/raw" \
        "${PERSIST_BASE}/knowledge/index"

    # 进化门禁密钥文件：幂等生成，重启保留；0600 防止同容器其他进程读取
    if [ ! -f "${PERSIST_BASE}/evolution/gate_secret" ]; then
        python3 -c "import secrets; print(secrets.token_hex(32))" \
            > "${PERSIST_BASE}/evolution/gate_secret"
        chmod 600 "${PERSIST_BASE}/evolution/gate_secret"
        echo "PERSIST: generated evolution gate secret"
    fi
else
    echo "WARN: /mnt/workspace not writable (FUSE mount unavailable), using container paths. Data will be lost on restart!"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 7860
