"""
Background worker for CommerceOps AI. The FastAPI /chat endpoint only
queues the message; this worker drives the actual Supervisor graph run,
updating the jobs table after every node so the frontend's progress bar
reflects real state, not a fake spinner.

Run standalone:
    python -m app.worker
"""
import json
import logging
import time

import redis

from app.agents.graph import get_graph
from app.config import settings
from app.db import get_job, init_db, update_job
from app.observability.metrics import record_intent, record_node_latency, record_request_outcome

logging.basicConfig(level=logging.INFO, format="%(asctime)s worker %(levelname)s %(message)s")
logger = logging.getLogger("commerceops.worker")


def process_job(
    session_id: str, message: str, employee_name: str, employee_role: str,
    customer_id: str, order_id: str,
) -> None:
    graph = get_graph()
    config = {"configurable": {"thread_id": session_id}}

    initial_state = {
        "session_id": session_id, "raw_message": message,
        "employee_name": employee_name, "employee_role": employee_role,
        "customer_id": customer_id, "order_id": order_id,
    }
    update_job(session_id, status="running")

    try:
        last_state = None
        for state in graph.stream(initial_state, config, stream_mode="values"):
            last_state = state
            node = state.get("current_node", "")
            t0 = time.time()
            update_job(session_id, status="running", current_node=node, progress_pct=state.get("progress_pct", 0))
            record_node_latency(node or "unknown", time.time() - t0)

            if node == "intent_router" and state.get("intent"):
                record_intent(state["intent"], state.get("used_llm_fallback", False))

        snapshot = graph.get_state(config)
        if snapshot.next:
            update_job(session_id, status="awaiting_approval", progress_pct=95)
            logger.info("Session %s paused for human approval.", session_id)
            return

        if last_state and last_state.get("guard_allowed") is False:
            update_job(
                session_id, status="rejected", progress_pct=100,
                error="Blocked by input guardrail: " + ", ".join(last_state.get("guard_notes", [])),
            )
            record_request_outcome("rejected")
            return

        update_job(session_id, status="completed", progress_pct=100)
        record_request_outcome("completed")
        logger.info("Session %s completed.", session_id)

    except Exception as exc:
        logger.exception("Session %s failed", session_id)
        update_job(session_id, status="failed", error=str(exc)[:500])
        record_request_outcome("failed")


def main() -> None:
    init_db()
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    logger.info("Worker started. Watching queue '%s'.", settings.JOB_QUEUE_KEY)
    while True:
        item = r.blpop(settings.JOB_QUEUE_KEY, timeout=5)
        if item is None:
            continue
        _, raw_payload = item
        payload = json.loads(raw_payload)
        session_id = payload["session_id"]
        job = get_job(session_id)
        if job is None:
            logger.warning("Unknown job %s in queue, skipping.", session_id)
            continue
        logger.info("Picked up session %s", session_id)
        process_job(
            session_id, payload["message"], payload.get("employee_name", ""),
            payload.get("employee_role", ""), payload["customer_id"], payload.get("order_id", ""),
        )


if __name__ == "__main__":
    main()
