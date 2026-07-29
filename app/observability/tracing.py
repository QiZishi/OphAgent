"""OpenTelemetry setup with an export-time privacy allowlist."""

from __future__ import annotations

import re
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

from app.core.config import Settings, settings

SAFE_ATTRIBUTE_PREFIXES = (
    "ophagent.",
    "http.request.method",
    "http.response.status_code",
    "server.address",
    "error.type",
    "gen_ai.system",
    "gen_ai.request.model",
    "gen_ai.response.model",
    "gen_ai.usage.",
)
SAFE_NAME = re.compile(r"[^A-Za-z0-9_.:/-]+")
_configuration_lock = threading.Lock()
_configured = False
_exporter_ready = False


def _safe_attributes(
    attributes: Mapping[str, Any] | None,
) -> dict[str, str | bool | int | float | Sequence[str] | Sequence[bool] | Sequence[int] | Sequence[float]]:
    if not attributes:
        return {}
    output: dict[str, Any] = {}
    for key, value in attributes.items():
        if not any(key.startswith(prefix) for prefix in SAFE_ATTRIBUTE_PREFIXES):
            continue
        if isinstance(value, str):
            output[key] = value[:240]
        elif isinstance(value, (bool, int, float)):
            output[key] = value
        elif isinstance(value, (list, tuple)):
            output[key] = list(value)[:20]
    return output


class PrivacyFilteringExporter(SpanExporter):
    """Remove prompt/content/events/links before spans leave the process."""

    def __init__(self, delegate: SpanExporter) -> None:
        self.delegate = delegate

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        filtered: list[ReadableSpan] = []
        for span in spans:
            name = SAFE_NAME.sub("_", span.name)[:120] or "ophagent.span"
            filtered.append(
                ReadableSpan(
                    name=name,
                    context=span.context,
                    parent=span.parent,
                    resource=span.resource,
                    attributes=_safe_attributes(span.attributes),
                    events=(),
                    links=(),
                    kind=span.kind,
                    status=span.status,
                    start_time=span.start_time,
                    end_time=span.end_time,
                    instrumentation_scope=span.instrumentation_scope,
                ),
            )
        return self.delegate.export(filtered)

    def shutdown(self) -> None:
        self.delegate.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return self.delegate.force_flush(timeout_millis)


def configure_tracing(config: Settings = settings) -> bool:
    """Configure once and return whether a remote exporter is active."""
    global _configured, _exporter_ready
    with _configuration_lock:
        if _configured:
            return _exporter_ready
        provider = trace.get_tracer_provider()
        if not isinstance(provider, TracerProvider):
            provider = TracerProvider(
                resource=Resource.create(
                    {
                        "service.name": config.OTEL_SERVICE_NAME,
                        "service.version": config.APP_VERSION,
                        "deployment.environment": config.ENVIRONMENT,
                    },
                ),
            )
            trace.set_tracer_provider(provider)
        if config.OTEL_EXPORTER_OTLP_ENDPOINT:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = PrivacyFilteringExporter(
                OTLPSpanExporter(endpoint=config.OTEL_EXPORTER_OTLP_ENDPOINT),
            )
            provider.add_span_processor(BatchSpanProcessor(exporter))
            _exporter_ready = True
        _configured = True
        return _exporter_ready


def tracer():
    return trace.get_tracer("ophagent-pro")


@contextmanager
def safe_span(name: str, **attributes: Any) -> Iterator[trace.Span]:
    """Start a span that accepts identifiers and aggregate metrics only."""
    with tracer().start_as_current_span(
        name,
        attributes=_safe_attributes(attributes),
    ) as span:
        try:
            yield span
        except Exception as exc:
            span.set_attribute("error.type", type(exc).__name__)
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            raise


def exporter_status() -> dict[str, Any]:
    return {
        "configured": _configured,
        "exporter_ready": _exporter_ready,
        "privacy_policy": "allowlist_no_prompt_no_events_no_links",
    }
