"""
Terminal-only observability report. This replaces the removed
Observability Streamlit page — nothing in the frontend surfaces
guardrail events, tracing status, or metrics anymore; this script is
now the only way to check them, run directly from a terminal.

Covers all four observability tools without needing a browser for the
two that support a pure-terminal check:
  - Guardrail events: read straight from SQLite (app/db.py).
  - Prometheus metrics: fetched live from the backend's own /metrics
    endpoint via a plain HTTP GET — no browser, no separate curl needed.
  - LangSmith: config status only (it's a hosted SaaS with its own web
    UI — this script tells you whether tracing is even enabled, not a
    replacement for opening smith.langchain.com directly).
  - Arize Phoenix: config status only, same reasoning — it's a
    self-hosted web app, this reports whether it's receiving traces at
    all, not a replacement for opening its own UI.

Usage:
    python scripts/observability_report.py                # one-shot report
    python scripts/observability_report.py --events 50    # show more guardrail events
    python scripts/observability_report.py --watch 10     # re-print every 10s
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from app.config import settings
from app.db import init_db, list_guardrail_events


def _print_header(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def print_guardrail_events(limit: int) -> None:
    _print_header(f"GUARDRAIL EVENTS (last {limit})")
    events = list_guardrail_events(limit=limit)
    if not events:
        print("No guardrail events logged yet — submit a request through the Chat Console first.")
        return
    print(f"{'TIME':<20} {'SESSION':<16} {'RAIL TYPE':<28} {'ACTION':<10} DETAIL")
    print("-" * 110)
    for e in events:
        session_short = (e["session_id"] or "")[:14]
        detail_short = (e["detail"] or "")[:50]
        print(f"{e['occurred_at'][:19]:<20} {session_short:<16} {e['rail_type']:<28} {e['action']:<10} {detail_short}")

    action_counts: dict[str, int] = {}
    for e in events:
        action_counts[e["action"]] = action_counts.get(e["action"], 0) + 1
    print("\nAction breakdown:", ", ".join(f"{k}={v}" for k, v in sorted(action_counts.items())))


def _fetch_and_print_metrics(label: str, url: str) -> None:
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
    except Exception as exc:
        print(f"  [{label}] Couldn't reach {url} — is that process running? ({exc})")
        return

    lines = [l for l in resp.text.splitlines() if l.startswith("commerceops_") and not l.startswith("#")]
    if not lines:
        print(f"  [{label}] Reachable, but no commerceops_* metrics recorded yet from this process.")
        return
    for line in lines:
        print(f"  [{label}] {line}")


def print_prometheus_metrics() -> None:
    _print_header("PROMETHEUS METRICS (live, fetched directly from both processes)")
    print(
        "The backend (uvicorn) and the worker are separate OS processes, each with its own "
        "in-memory Prometheus registry — node latency, intent, and request-outcome metrics "
        "are only ever recorded inside the worker, so checking the backend's endpoint alone "
        "misses almost all of them. Checking both here, not just one."
    )
    _fetch_and_print_metrics("backend", f"http://localhost:{settings.API_PORT}/metrics")
    _fetch_and_print_metrics("worker", f"http://localhost:{settings.WORKER_METRICS_PORT}/metrics")
    print(f"\nFull raw output: curl http://localhost:{settings.API_PORT}/metrics"
          f"  and  curl http://localhost:{settings.WORKER_METRICS_PORT}/metrics")


def print_tracing_status() -> None:
    _print_header("LANGSMITH (config status only — open smith.langchain.com directly for the trace UI)")
    if settings.LANGCHAIN_TRACING_V2 == "true":
        print(f"  Status:  ENABLED")
        print(f"  Project: {settings.LANGCHAIN_PROJECT}")
        print("  Dashboard: open https://smith.langchain.com and select the configured project.")
    else:
        print("  Status: DISABLED — set LANGSMITH_API_KEY and LANGCHAIN_TRACING_V2=true in backend/.env to enable.")

    _print_header("ARIZE PHOENIX (config status only — open its own UI directly for trace details)")
    if settings.PHOENIX_ENABLED:
        print(f"  Status:   ENABLED")
        print(f"  Sending traces to: {settings.PHOENIX_COLLECTOR_ENDPOINT}")
        print(f"  Dashboard: http://localhost:6006")
    else:
        print("  Status: DISABLED — set PHOENIX_ENABLED=true in backend/.env to enable "
              "(requires the `phoenix` Docker service to be running: docker compose up phoenix -d).")


def print_grafana_info() -> None:
    _print_header("GRAFANA (requires a browser — no pure-terminal equivalent for the dashboard itself)")
    print("  URL:      http://localhost:3000")
    print("  Login:    admin / commerceops")
    print("  Note:     the underlying data is the same Prometheus metrics printed above —")
    print("            Grafana is a visualization layer on top of them, not a separate data source.")


def run_report(events_limit: int) -> None:
    init_db()
    print_guardrail_events(events_limit)
    print_prometheus_metrics()
    print_tracing_status()
    print_grafana_info()
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=20, help="Number of recent guardrail events to show")
    parser.add_argument("--watch", type=int, default=0, help="Re-print the report every N seconds instead of once")
    args = parser.parse_args()

    if args.watch:
        try:
            while True:
                run_report(args.events)
                print(f"(refreshing every {args.watch}s — Ctrl+C to stop)")
                time.sleep(args.watch)
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        run_report(args.events)
