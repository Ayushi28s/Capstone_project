import argparse
import sys
import time
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent),
)

import requests

from app.config import settings
from app.db import init_db, list_guardrail_events


def _print_header(title: str) -> None:
    print(
        f"\n{'=' * 70}\n"
        f"{title}\n"
        f"{'=' * 70}"
    )


def print_guardrail_events(limit: int) -> None:
    _print_header(
        f"GUARDRAIL EVENTS (last {limit})"
    )

    events = list_guardrail_events(
        limit=limit
    )

    if not events:
        print(
            "No guardrail events logged yet — "
            "submit a request through the Chat Console first."
        )
        return

    print(
        f"{'TIME':<20} "
        f"{'SESSION':<16} "
        f"{'RAIL TYPE':<28} "
        f"{'ACTION':<10} "
        f"DETAIL"
    )

    print("-" * 110)

    for event in events:
        session_short = (
            event["session_id"] or ""
        )[:14]

        detail_short = (
            event["detail"] or ""
        )[:50]

        print(
            f"{event['occurred_at'][:19]:<20} "
            f"{session_short:<16} "
            f"{event['rail_type']:<28} "
            f"{event['action']:<10} "
            f"{detail_short}"
        )

    action_counts: dict[str, int] = {}

    for event in events:
        action = event["action"]

        action_counts[action] = (
            action_counts.get(action, 0)
            + 1
        )

    print(
        "\nAction breakdown:",
        ", ".join(
            f"{key}={value}"
            for key, value
            in sorted(action_counts.items())
        ),
    )


def _fetch_and_print_metrics(
    label: str,
    url: str,
) -> None:
    try:
        resp = requests.get(
            url,
            timeout=5,
        )

        resp.raise_for_status()

    except Exception as exc:
        print(
            f"  [{label}] Couldn't reach {url} — "
            f"is that process running? ({exc})"
        )
        return

    lines = [
        line
        for line in resp.text.splitlines()
        if line.startswith("commerceops_")
        and not line.startswith("#")
    ]

    if not lines:
        print(
            f"  [{label}] Reachable, but no "
            "commerceops_* metrics recorded yet "
            "from this process."
        )
        return

    for line in lines:
        print(
            f"  [{label}] {line}"
        )


def print_prometheus_metrics() -> None:
    _print_header(
        "PROMETHEUS METRICS "
        "(live, fetched directly from both processes)"
    )

    print(
        "The backend (uvicorn) and the worker are "
        "separate OS processes, each with its own "
        "in-memory Prometheus registry. "
        "Node latency, intent, and request-outcome "
        "metrics are primarily recorded inside the "
        "worker, while approval-related metrics can "
        "be recorded by the backend. "
        "Both endpoints are checked below."
    )

    backend_url = (
        f"http://127.0.0.1:"
        f"{settings.API_PORT}/metrics"
    )

    worker_url = (
        f"http://127.0.0.1:"
        f"{settings.WORKER_METRICS_PORT}/metrics"
    )

    _fetch_and_print_metrics(
        "backend",
        backend_url,
    )

    _fetch_and_print_metrics(
        "worker",
        worker_url,
    )

    print(
        "\nFull raw output:"
    )

    print(
        f"  curl http://127.0.0.1:"
        f"{settings.API_PORT}/metrics"
    )

    print(
        f"  curl http://127.0.0.1:"
        f"{settings.WORKER_METRICS_PORT}/metrics"
    )


def print_tracing_status() -> None:
    _print_header(
        "LANGSMITH "
        "(config status only — open the hosted "
        "trace UI directly)"
    )

    if settings.LANGCHAIN_TRACING_V2 == "true":
        print(
            "  Status:   ENABLED"
        )

        print(
            f"  Project:  "
            f"{settings.LANGCHAIN_PROJECT}"
        )

        print(
            "  Dashboard: https://smith.langchain.com"
        )

        print(
            "  Note: select the configured project "
            "after opening the LangSmith workspace."
        )

    else:
        print(
            "  Status: DISABLED — set "
            "LANGSMITH_API_KEY and "
            "LANGCHAIN_TRACING_V2=true "
            "in backend/.env to enable."
        )

    _print_header(
        "ARIZE PHOENIX "
        "(config status only — open its own UI "
        "directly for trace details)"
    )

    if settings.PHOENIX_ENABLED:
        print(
            "  Status:   ENABLED"
        )

        print(
            "  Sending traces to: "
            f"{settings.PHOENIX_COLLECTOR_ENDPOINT}"
        )

        print(
            "  Dashboard: "
            "http://127.0.0.1:6006"
        )

        print(
            "  Trace endpoint: "
            "http://127.0.0.1:6006/v1/traces"
        )

        print(
            "  Note: Phoenix only receives traces "
            "created after tracing is enabled and "
            "the backend/worker are restarted."
        )

    else:
        print(
            "  Status: DISABLED — set "
            "PHOENIX_ENABLED=true in backend/.env "
            "to enable."
        )

        print(
            "  Start Phoenix with:"
        )

        print(
            "  docker compose up -d --no-deps phoenix"
        )


def print_grafana_info() -> None:
    _print_header(
        "GRAFANA "
        "(browser dashboard backed by Prometheus)"
    )

    print(
        "  URL:      "
        "http://127.0.0.1:3000"
    )

    print(
        "  Login:    "
        "admin / commerceops"
    )

    print(
        "  Note: Grafana visualizes the "
        "Prometheus metrics collected from "
        "the backend and worker."
    )

    print(
        "  Prometheus: "
        "http://127.0.0.1:9090"
    )


def run_report(
    events_limit: int,
) -> None:
    init_db()

    print_guardrail_events(
        events_limit
    )

    print_prometheus_metrics()

    print_tracing_status()

    print_grafana_info()

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--events",
        type=int,
        default=20,
        help=(
            "Number of recent guardrail "
            "events to show"
        ),
    )

    parser.add_argument(
        "--watch",
        type=int,
        default=0,
        help=(
            "Re-print the report every N "
            "seconds instead of once"
        ),
    )

    args = parser.parse_args()

    if args.watch:
        try:
            while True:
                run_report(
                    args.events
                )

                print(
                    f"(refreshing every "
                    f"{args.watch}s — "
                    "Ctrl+C to stop)"
                )

                time.sleep(
                    args.watch
                )

        except KeyboardInterrupt:
            print(
                "\nStopped."
            )

    else:
        run_report(
            args.events
        )