# Tools

工具层只保留稳定真实能力：多模态分析、文档解析、指南检索、联网检索、引用核验、ClinicalState、文件产物与 ASR/TTS。每个失败都返回或抛出显式 capability 错误。

测试替身只能放在 `tests/fakes` 并通过构造器注入。
