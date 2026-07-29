# Observability

OpenTelemetry 覆盖 API、Run、Agent、工具和检索的标识、耗时、状态及 token 聚合指标。远端导出前执行属性白名单，并删除 event/link，禁止导出 prompt、回答全文、工具参数、患者原文、凭据和异常详情。

未配置 `OTEL_EXPORTER_OTLP_ENDPOINT` 时仍可创建本地 span，但能力状态会明确显示没有远端 exporter。
