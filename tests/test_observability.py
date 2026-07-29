from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from app.observability.tracing import PrivacyFilteringExporter


class CaptureExporter(SpanExporter):
    def __init__(self) -> None:
        self.spans = []

    def export(self, spans):
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS


def test_exporter_drops_patient_text_prompts_events_and_links():
    capture = CaptureExporter()
    exporter = PrivacyFilteringExporter(capture)
    source = ReadableSpan(
        name="agent model 用户原文",
        attributes={
            "ophagent.run_id": "run_1",
            "gen_ai.prompt.0.content": "患者完整原文",
            "tool.arguments": '{"api_key":"secret"}',
            "error.type": "TimeoutError",
        },
        events=(Event("exception", {"exception.message": "患者隐私"}),),
    )
    result = exporter.export([source])
    assert result is SpanExportResult.SUCCESS
    exported = capture.spans[0]
    assert exported.attributes == {
        "ophagent.run_id": "run_1",
        "error.type": "TimeoutError",
    }
    assert not exported.events
    assert not exported.links
    assert "患者" not in exported.name
