"""
Observability bootstrap for the NorthPeak Operations Copilot.

This module initializes three observability paths:

1. LangSmith
   - Cloud tracing for LangChain and LangGraph workflows.
   - Enabled through LangSmith environment variables.

2. Prometheus / OpenTelemetry Metrics
   - Exposes application metrics consumed by Prometheus and Grafana.

3. Arize Phoenix
   - Receives OpenTelemetry traces from LangChain and LangGraph.
   - Phoenix runs as a separate Docker service.
   - OpenInference instruments LangChain/LangGraph callbacks so those
     executions appear inside Phoenix.

All integrations are optional. If an observability provider is disabled
or unavailable, the application continues running.
"""

import logging
import os

from opentelemetry import metrics
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider

from app.config import settings


logger = logging.getLogger("commerceops.observability")

_initialized = False


def _langsmith_enabled() -> bool:
    """
    Support both the current LangSmith variable and the older
    LangChain tracing variable used elsewhere in the project.
    """
    langsmith_tracing = os.getenv(
        "LANGSMITH_TRACING",
        "",
    ).lower()

    langchain_tracing = str(
        settings.LANGCHAIN_TRACING_V2
    ).lower()

    return (
        langsmith_tracing == "true"
        or langchain_tracing == "true"
    )


def _langsmith_project() -> str:
    """
    Prefer the current LANGSMITH_PROJECT variable while keeping
    LANGCHAIN_PROJECT as a compatibility fallback.
    """
    return (
        os.getenv("LANGSMITH_PROJECT")
        or settings.LANGCHAIN_PROJECT
        or "northpeak-operations-copilot"
    )


def init_observability() -> None:
    global _initialized

    if _initialized:
        return

    project_name = _langsmith_project()

    # ---------------------------------------------------------
    # LangSmith
    # ---------------------------------------------------------

    if _langsmith_enabled():
        if os.getenv("LANGSMITH_API_KEY"):
            logger.info(
                "LangSmith tracing enabled for project '%s'.",
                project_name,
            )
        else:
            logger.warning(
                "LangSmith tracing is enabled but "
                "LANGSMITH_API_KEY is missing."
            )
    else:
        logger.info(
            "LangSmith tracing disabled."
        )

    # ---------------------------------------------------------
    # OpenTelemetry / Prometheus
    # ---------------------------------------------------------

    try:
        reader = PrometheusMetricReader()

        meter_provider = MeterProvider(
            metric_readers=[reader]
        )

        metrics.set_meter_provider(
            meter_provider
        )

        logger.info(
            "OpenTelemetry Prometheus metric provider initialized."
        )

    except Exception as exc:
        logger.warning(
            "OpenTelemetry Prometheus initialization failed (%s). "
            "Continuing without OpenTelemetry metrics.",
            exc,
        )

    # ---------------------------------------------------------
    # Arize Phoenix
    # ---------------------------------------------------------

    if settings.PHOENIX_ENABLED:
        try:
            from phoenix.otel import register

            tracer_provider = register(
                endpoint=settings.PHOENIX_COLLECTOR_ENDPOINT,
                project_name=project_name,
                protocol="http/protobuf",
                batch=True,
                verbose=False,
            )

            logger.info(
                "Arize Phoenix tracer registered for project '%s' "
                "using collector %s.",
                project_name,
                settings.PHOENIX_COLLECTOR_ENDPOINT,
            )

            # -------------------------------------------------
            # LangChain / LangGraph OpenInference instrumentation
            # -------------------------------------------------

            try:
                from openinference.instrumentation.langchain import (
                    LangChainInstrumentor,
                )

                instrumentor = LangChainInstrumentor()

                if not instrumentor.is_instrumented_by_opentelemetry:
                    instrumentor.instrument(
                        tracer_provider=tracer_provider
                    )

                    logger.info(
                        "LangChain/LangGraph OpenInference "
                        "instrumentation enabled for Phoenix."
                    )
                else:
                    logger.info(
                        "LangChain/LangGraph OpenInference "
                        "instrumentation was already enabled."
                    )

            except ImportError:
                logger.warning(
                    "Phoenix is connected, but LangChain "
                    "instrumentation is unavailable. Install "
                    "'openinference-instrumentation-langchain' "
                    "to capture LangChain/LangGraph traces."
                )

            except Exception as exc:
                logger.warning(
                    "LangChain OpenInference instrumentation "
                    "failed (%s). Phoenix remains connected.",
                    exc,
                )

        except Exception as exc:
            logger.warning(
                "Arize Phoenix registration failed (%s). "
                "Continuing without Phoenix tracing.",
                exc,
            )

    else:
        logger.info(
            "Arize Phoenix disabled. "
            "Set PHOENIX_ENABLED=true to enable it."
        )

    _initialized = True