"""
Observability bootstrap. LangSmith tracing and Phoenix are both opt-in
via env vars — a learner without those configured still gets a fully
working demo, just without hosted traces or drift monitoring.

Phoenix connects to a REMOTE Phoenix instance (the `phoenix` service in
docker-compose.yml, or your own `arizephoenix/phoenix` container) via
arize-phoenix-otel's register(), rather than launching a local instance
in-process. See requirements.txt for why: the full arize-phoenix
package hard-depends on sqlean-py, which has no Windows wheels and
needs a C++ compiler to build from source.
"""
import logging

from opentelemetry import metrics
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider

from app.config import settings

logger = logging.getLogger("commerceops.observability")
_initialized = False


def init_observability() -> None:
    global _initialized
    if _initialized:
        return

    if settings.LANGCHAIN_TRACING_V2 == "true":
        logger.info("LangSmith tracing enabled for project '%s'.", settings.LANGCHAIN_PROJECT)
    else:
        logger.info("LangSmith tracing disabled (no LANGSMITH_API_KEY set).")

    reader = PrometheusMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)
    logger.info("OpenTelemetry Prometheus exporter ready on port %s.", settings.OTEL_EXPORTER_PROMETHEUS_PORT)

    if settings.PHOENIX_ENABLED:
        try:
            from phoenix.otel import register
            register(
                endpoint=settings.PHOENIX_COLLECTOR_ENDPOINT,
                project_name=settings.LANGCHAIN_PROJECT,
                protocol="http/protobuf",
                batch=True,
                verbose=False,
            )
            logger.info(
                "Arize Phoenix tracing registered — sending to %s. "
                "Requires the `phoenix` container (or your own Phoenix instance) to be running.",
                settings.PHOENIX_COLLECTOR_ENDPOINT,
            )
        except Exception as exc:
            logger.warning("Arize Phoenix registration failed (%s) — continuing without it.", exc)
    else:
        logger.info("Arize Phoenix disabled (set PHOENIX_ENABLED=true to enable).")

    _initialized = True
