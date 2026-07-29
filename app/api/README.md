# API

版本化 API 提供 Run、事件流、Artifact、Memory、Skill、Knowledge 来源/索引与 Capability 管理。知识导入默认是待核验用户来源，重建索引返回 `202`。旧认证和会话接口保留；旧同步 `/diagnose` 返回 `410`，避免绕回已移除的 Mock 运行时。
