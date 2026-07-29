# Knowledge

本地检索以指南优先，提供 BM25、BGE-M3 候选融合/持久化向量索引、可选 Rerank、PDF 页图定位和有来源的轻量 OphthaKG 查询扩展。每条证据保留来源、段落/页码、版本、状态和可选页图。

`SourceRegistry` 不会把联网结果写入本地指南库。用户导入记录默认 `verified=false`、`status=unknown`；失效与替代来源默认不参与召回，但仍保留在来源治理界面。文件名推断的年份、地区和机构只用于预填，必须人工核验。
