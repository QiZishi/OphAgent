"""Deterministic online CRUD commands for low-authority user memory."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

MemoryAction = Literal["create", "update", "delete"]


@dataclass(frozen=True, slots=True)
class OnlineMemoryCommand:
    action: MemoryAction
    content: str
    replacement: str | None = None
    key: str | None = None
    category: Literal["preference", "workspace"] = "preference"
    clear_all: bool = False


KEY_PATTERNS = (
    ("response_style", r"简洁|详细|回复|回答|篇幅|长一点|短一点"),
    ("response_language", r"中文|英文|语言"),
    ("response_format", r"Markdown|表格|列表|格式|要点"),
    ("addressing", r"称呼|叫我"),
)
WORKSPACE_PATTERN = re.compile(r"工作区|项目偏好|仓库偏好")
PROTECTED_POLICY_PATTERN = re.compile(
    r"(?:系统|安全|红旗|急诊|权限|授权|工具|支付|退款|退费|审批|审核|"
    r"门禁|业务规则|业务红线).{0,12}(?:规则|策略|限制|要求|权限|忽略|"
    r"绕过|关闭|取消|修改|覆盖|改成|改为)"
    r"|(?:忽略|绕过|关闭|取消|修改|覆盖).{0,12}(?:系统|安全|红旗|急诊|"
    r"权限|授权|工具|支付|退款|退费|审批|审核|门禁|业务规则|业务红线)",
)
UPDATE_PATTERN = re.compile(
    r"(?:请)?(?:把|将)\s*(?P<old>.+?)\s*(?:改成|改为|换成)\s*(?P<new>.+)",
)
DELETE_PATTERN = re.compile(
    r"(?:请)?(?:忘记|删除|清除|不要再记住|别再记住)\s*(?P<content>.+)",
)
CREATE_PATTERN = re.compile(
    r"(?:请记住|记住|以后(?:请|回答|回复|都|统一|默认)|我的偏好是|我喜欢)"
    r"\s*[:：，,]?\s*(?P<content>.+)",
)


def _clean(value: str) -> str:
    return value.strip().strip("。！!；;，,：: ")[:500]


def preference_key(content: str) -> str | None:
    for key, pattern in KEY_PATTERNS:
        if re.search(pattern, content, flags=re.IGNORECASE):
            return key
    return None


def _is_low_authority_content(value: str) -> bool:
    return not PROTECTED_POLICY_PATTERN.search(value)


def parse_online_memory_commands(query: str) -> list[OnlineMemoryCommand]:
    """Parse explicit user intent; never infer clinical or policy memory."""
    text = _clean(query)
    if not text:
        return []
    category: Literal["preference", "workspace"] = (
        "workspace" if WORKSPACE_PATTERN.search(text) else "preference"
    )
    update_match = UPDATE_PATTERN.search(text)
    if update_match:
        old = _clean(update_match.group("old"))
        new = _clean(update_match.group("new"))
        if old and new and _is_low_authority_content(new):
            return [
                OnlineMemoryCommand(
                    action="update",
                    content=old,
                    replacement=new,
                    key=preference_key(old) or preference_key(new),
                    category=category,
                ),
            ]
    delete_match = DELETE_PATTERN.search(text)
    if delete_match:
        content = _clean(delete_match.group("content"))
        if content:
            clear_all = bool(re.search(r"全部|所有|一切", content))
            return [
                OnlineMemoryCommand(
                    action="delete",
                    content=content,
                    key=None if clear_all else preference_key(content),
                    category=category,
                    clear_all=clear_all,
                ),
            ]
    create_match = CREATE_PATTERN.search(text)
    if create_match:
        content = _clean(create_match.group("content"))
        if content and _is_low_authority_content(content):
            return [
                OnlineMemoryCommand(
                    action="create",
                    content=content,
                    key=preference_key(content),
                    category=category,
                ),
            ]
    return []
