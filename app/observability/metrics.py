"""
Prometheus metrics for CommerceOps AI, scraped by the Prometheus
container and visualized by the pre-provisioned Grafana dashboard.
"""
from prometheus_client import Counter, Histogram

NODE_LATENCY_SECONDS = Histogram(
    "commerceops_node_latency_seconds",
    "Time spent in each Supervisor graph node",
    labelnames=["node"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 20, 40, 60, 120),
)

REQUESTS_TOTAL = Counter(
    "commerceops_requests_total",
    "Chat requests processed, by final status",
    labelnames=["status"],  # completed | failed | rejected | awaiting_approval
)

INTENT_TOTAL = Counter(
    "commerceops_intent_total",
    "Requests classified per intent",
    labelnames=["intent", "used_llm_fallback"],
)

GUARDRAIL_EVENTS_TOTAL = Counter(
    "commerceops_guardrail_events_total",
    "Guardrail actions across input rail, PII/cost-data redaction, and output guard",
    labelnames=["rail_type", "action"],
)

HITL_DECISIONS_TOTAL = Counter(
    "commerceops_hitl_decisions_total",
    "Human-in-the-loop approval decisions",
    labelnames=["approved"],
)

ESTIMATED_TOKEN_COST_USD = Counter(
    "commerceops_estimated_token_cost_usd_total",
    "Rough running total of estimated OpenRouter spend for this deployment",
)


def record_node_latency(node: str, seconds: float) -> None:
    NODE_LATENCY_SECONDS.labels(node=node).observe(seconds)


def record_request_outcome(status: str) -> None:
    REQUESTS_TOTAL.labels(status=status).inc()


def record_intent(intent: str, used_llm_fallback: bool) -> None:
    INTENT_TOTAL.labels(intent=intent, used_llm_fallback=str(used_llm_fallback)).inc()


def record_guardrail_event(rail_type: str, action: str) -> None:
    GUARDRAIL_EVENTS_TOTAL.labels(rail_type=rail_type, action=action).inc()


def record_hitl_decision(approved: bool) -> None:
    HITL_DECISIONS_TOTAL.labels(approved=str(approved)).inc()


def record_token_cost(usd: float) -> None:
    ESTIMATED_TOKEN_COST_USD.inc(usd)
