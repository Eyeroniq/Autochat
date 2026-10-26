"""Vendor-neutral tracing for AutoChat.

Application code only talks to the plain OpenTelemetry API through the helpers
in :mod:`autochat.observability.tracing`. Where spans end up is decided
purely by ``observability.exporters`` in settings, see
:mod:`autochat.observability.setup`.

When tracing is disabled (or the ``observability-otel`` extra is missing) every
helper degrades to a no-op, so instrumented code never needs to guard itself.
"""

from autochat.observability.tracing import (
    SpanKind,
    current_trace_id,
    inject_trace_context,
    record_exception,
    retrieval_documents,
    set_span_attributes,
    set_span_status,
    start_span,
    trace_context_from,
    traced,
    using_trace_attributes,
)

__all__ = [
    "SpanKind",
    "current_trace_id",
    "inject_trace_context",
    "record_exception",
    "retrieval_documents",
    "set_span_attributes",
    "set_span_status",
    "start_span",
    "trace_context_from",
    "traced",
    "using_trace_attributes",
]
