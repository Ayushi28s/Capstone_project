"""
Seeds the Approval Queue with realistic pending items, for demo
purposes — without this, the queue is genuinely empty until someone
manually submits a request that trips a HITL trigger through the Chat
Console first.

This is SEPARATE from scripts/seed_db.py on purpose: seed_db.py needs
no API key at all (it only seeds SQLite rows, builds the vector index,
and trains the intent classifier). This script submits real requests
through the actual compiled Supervisor graph — including a real LLM
call for intent classification and the Support Triage Crew — so it
needs a working OPENROUTER_API_KEY, exactly like running the app live
would. It reuses app.worker.process_job() directly rather than
reimplementing the pipeline-invocation logic, so a seeded pending item
behaves identically to one a real employee submitted through the UI —
same checkpoint, same resumability, same audit trail.

Covers all THREE ways a request lands in the Approval Queue:
  1. THRESHOLD_SCENARIOS — a single refund request >= $250.
  2. ANOMALY_SCENARIO — three rapid refund requests from the same
     customer, each individually UNDER $250, which the anomaly check
     (recent_refund_request_count >= 3 within 60 minutes, see
     app/agents/support_crew.py's process_refund_tool) flags on the
     third request even though no single request crossed the line.
  3. ROLE_ONLY_SCENARIO — an ordinary order-status lookup from a
     non-Manager employee. Nothing about the request itself (amount,
     anomaly) would trigger approval — it's gated purely because the
     submitting employee isn't a Manager (see the role-based gate in
     app/agents/nodes.py's assemble_response_node). Without this
     scenario, that specific trigger — the one that now applies to
     every non-Manager request, not just refunds — has no seeded
     example showing it fire on a genuinely ordinary request.

Run after scripts/seed_db.py and after confirming a working
OPENROUTER_API_KEY (e.g. via `python preflight_check.py`):

    python scripts/seed_demo_approvals.py
"""
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.db import create_job, init_db

# Employee names are deliberately distinct from the seeded customer
# names (Jamie Rivera, Alex Chen, Morgan Ellis, Sam Patel, Taylor
# Brooks, Casey Kim — see scripts/seed_db.py) so a reviewer can't
# confuse "who's asking" with "whose account this is about." All are
# tier1_support or analyst here on purpose — a Manager submitting the
# exact same requests would only need approval for the threshold/
# anomaly scenarios, not the role-only one, since role is the fourth
# thing being demonstrated in this file, not incidental to it.
THRESHOLD_SCENARIOS = [
    {
        "employee_name": "Devon Walsh",
        "employee_role": "tier1_support",
        "customer_id": "CUST-002",
        "order_id": "NP-77410",
        "message": (
            "I'd like to process a $310 refund for order NP-77410 — the parka arrived with a "
            "broken zipper pull, customer sent photos and doesn't want a replacement, just a refund."
        ),
    },
    {
        "employee_name": "Priya Shah",
        "employee_role": "tier1_support",
        "customer_id": "CUST-003",
        "order_id": "NP-55660",
        "message": (
            "Requesting a $280 refund on order NP-55660 — customer ordered two pairs of hiking "
            "boots in the wrong size due to a sizing chart error on our end, wants a full refund "
            "rather than an exchange since the style is now out of stock in her size."
        ),
    },
    {
        "employee_name": "Chris Tanaka",
        "employee_role": "tier1_support",
        "customer_id": "CUST-006",
        "order_id": "NP-44550",
        "message": (
            "Customer is requesting a $275 refund for order NP-44550 — the rain shell has a "
            "defective seam that's letting water through, this is a manufacturing defect covered "
            "under warranty, not normal wear."
        ),
    },
]

# All three individually under $250 — the anomaly check should flag the
# THIRD one even though none of them alone crosses the threshold.
ANOMALY_SCENARIO = {
    "employee_name": "Jordan Reyes",
    "employee_role": "tier1_support",
    "customer_id": "CUST-004",
    "order_id": "NP-11220",
    "messages": [
        "$180 refund for order NP-11220 — one of the two base layers was the wrong size.",
        "Same customer, order NP-11220 — the second base layer was also wrong size, "
        "requesting a $185 refund for that one too, doesn't want an exchange.",
        "Following up again on order NP-11220 — customer says the whole order was "
        "disappointing and wants the remaining $190 balance refunded as well.",
    ],
}

# An ordinary order-status lookup — no refund, no dollar amount, no
# anomaly pattern. This should still land in the Approval Queue, purely
# because "analyst" isn't "manager."
ROLE_ONLY_SCENARIO = {
    "employee_name": "Sam Okafor",
    "employee_role": "analyst",
    "customer_id": "CUST-005",
    "order_id": "NP-22330",
    "message": "Can you check the status and estimated delivery for order NP-22330?",
}


def submit_one(session_id: str, message: str, employee_name: str, employee_role: str,
               customer_id: str, order_id: str) -> None:
    from app.worker import process_job  # imported lazily so the graph/checkpointer build after init_db()
    create_job(session_id, message, employee_name=employee_name, employee_role=employee_role, customer_id=customer_id)
    process_job(session_id, message, employee_name, employee_role, customer_id, order_id)


def run_threshold_scenarios() -> None:
    print(f"Submitting {len(THRESHOLD_SCENARIOS)} single refund requests >= $250 (threshold path)...")
    for i, scenario in enumerate(THRESHOLD_SCENARIOS, start=1):
        session_id = f"demo-approval-{uuid.uuid4().hex[:8]}"
        print(f"  [{i}/{len(THRESHOLD_SCENARIOS)}] {scenario['employee_name']} ({scenario['employee_role']}) -> "
              f"{scenario['customer_id']} ({scenario['order_id']}) — session {session_id}")
        submit_one(session_id, scenario["message"], scenario["employee_name"], scenario["employee_role"],
                   scenario["customer_id"], scenario["order_id"])


def run_anomaly_scenario() -> None:
    print(f"\nSubmitting 3 rapid sub-$250 refund requests from the same customer (anomaly path)...")
    for i, message in enumerate(ANOMALY_SCENARIO["messages"], start=1):
        session_id = f"demo-anomaly-{uuid.uuid4().hex[:8]}"
        print(f"  [{i}/3] {ANOMALY_SCENARIO['employee_name']} ({ANOMALY_SCENARIO['employee_role']}) -> "
              f"{ANOMALY_SCENARIO['customer_id']} — session {session_id}")
        submit_one(session_id, message, ANOMALY_SCENARIO["employee_name"], ANOMALY_SCENARIO["employee_role"],
                   ANOMALY_SCENARIO["customer_id"], ANOMALY_SCENARIO["order_id"])
        if i < len(ANOMALY_SCENARIO["messages"]):
            time.sleep(2)  # keeps all three inside the 60-minute anomaly window with room to spare


def run_role_only_scenario() -> None:
    print(f"\nSubmitting 1 ordinary order-status lookup from a non-Manager (role-only path)...")
    session_id = f"demo-role-{uuid.uuid4().hex[:8]}"
    print(f"  {ROLE_ONLY_SCENARIO['employee_name']} ({ROLE_ONLY_SCENARIO['employee_role']}) -> "
          f"{ROLE_ONLY_SCENARIO['customer_id']} — session {session_id}")
    submit_one(session_id, ROLE_ONLY_SCENARIO["message"], ROLE_ONLY_SCENARIO["employee_name"],
               ROLE_ONLY_SCENARIO["employee_role"], ROLE_ONLY_SCENARIO["customer_id"], ROLE_ONLY_SCENARIO["order_id"])


def main() -> None:
    if not settings.OPENROUTER_API_KEY:
        print(
            "OPENROUTER_API_KEY is not set. This script submits real requests through the live "
            "pipeline (unlike scripts/seed_db.py) and needs a working key. Add one to backend/.env "
            "first, or run `python preflight_check.py` to confirm it's valid."
        )
        sys.exit(1)

    init_db()
    run_threshold_scenarios()
    run_anomaly_scenario()
    run_role_only_scenario()

    print("\nDone. Open the Approval Queue page — these should now show as pending, covering all three")
    print("triggers: the >=$250 threshold, the 3rd item in the CUST-004 anomaly sequence, and the")
    print("role-only item from Sam Okafor (analyst) — an ordinary lookup gated purely by role.")
    print("If any didn't land as 'awaiting_approval', check that OPENROUTER_API_KEY is valid and retry.")


if __name__ == "__main__":
    main()
