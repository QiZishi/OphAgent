---
name: ophthalmic_interview
description: 将眼科主诉整理为结构化 ClinicalState，并提出最少必要追问。
---

# 眼科问诊

1. 区分用户原话、可观察事实、模型推测和未知项。
2. 优先补齐起病时间、单/双眼、疼痛、视力变化、外伤/化学暴露、用药与过敏。
3. 只把用户明确确认的信息写入 `ClinicalState`；推测进入 `unresolved_questions`。
4. 不给出无证据的确定诊断。
