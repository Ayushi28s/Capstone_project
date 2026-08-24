"""
Support Triage Crew: order-status, refund, and billing-dispute agents
under CrewAI's hierarchical process.

The intent router performs coarse routing into the support domain.
Inside the support domain, this crew delegates to the appropriate
specialist based on the actual employee request.

Refund approval is enforced deterministically in Python:
- refunds at or above the configured threshold require HITL approval
- repeated rapid sub-threshold refund requests can also trigger review
- approval-relevant flags are only valid for genuine refund results

CrewAI is configured with output_pydantic=SupportCrewOutput, so the
structured Pydantic result is used first. Raw JSON parsing is retained
only as a fallback.
"""

import asyncio
import json

from crewai import Agent, Crew, Process, Task
from crewai.tools import tool as crewai_tool
from pydantic import BaseModel, Field

from app.config import settings
from app.db import (
    get_order,
    log_guardrail_event,
    record_refund_request,
    recent_refund_request_count,
)
from app.llm_client import crew_agent_llm
from app.mcp_tools import order_db_client, ticketing_client


_VALID_RESULT_TYPES = {
    "order_status",
    "refund",
    "billing_dispute",
}


class SupportCrewOutput(BaseModel):
    handled_by: str = Field(
        description="Which specialist(s) actually handled this"
    )
    result_type: str = Field(
        description="order_status | refund | billing_dispute"
    )
    summary: str
    requires_human_approval: bool = False
    anomaly_flagged: bool = False
    order_id: str = ""
    amount_usd: float = 0.0


def _run_async(coro):
    """
    CrewAI tools are synchronous while MCP clients are async.

    Use a fresh asyncio event loop for each tool call. This matches the
    previously working project behavior and avoids coupling CrewAI tool
    execution to a long-lived persistent MCP session.
    """
    return asyncio.run(coro)


@crewai_tool("Look up order status")
def lookup_order_tool(order_id: str) -> str:
    """Look up an order's status, carrier, and delivery estimate."""
    try:
        result = _run_async(
            order_db_client.get_order(order_id)
        )
        return json.dumps(result)
    except Exception as exc:
        return json.dumps({
            "error": (
                f"Order lookup failed for {order_id}: "
                f"{type(exc).__name__}: {exc}"
            )
        })


@crewai_tool("Look up customer's order history")
def lookup_customer_orders_tool(customer_id: str) -> str:
    """List all orders belonging to a customer."""
    try:
        result = _run_async(
            order_db_client.get_customer_orders(customer_id)
        )
        return json.dumps(result)
    except Exception as exc:
        return json.dumps({
            "error": (
                f"Customer-order lookup failed for {customer_id}: "
                f"{type(exc).__name__}: {exc}"
            )
        })


@crewai_tool("Process a refund decision")
def process_refund_tool(
    order_id: str,
    customer_id: str,
    amount_usd: float,
    reason: str,
) -> str:
    """
    Validate and evaluate a refund request.

    This tool does not issue money. It determines whether the request
    can continue automatically or must pause for human approval.
    """
    order = get_order(order_id)

    if order is None:
        return json.dumps({
            "error": f"No order found with ID {order_id}"
        })

    if order["customer_id"] != customer_id:
        return json.dumps({
            "error": (
                f"Order {order_id} does not belong to "
                f"customer {customer_id}."
            )
        })

    if amount_usd <= 0:
        return json.dumps({
            "error": "Refund amount must be greater than zero."
        })

    order_total = float(order["total_amount_usd"])

    if amount_usd > order_total:
        return json.dumps({
            "error": (
                f"Requested refund ${amount_usd:.2f} exceeds "
                f"the recorded order total of ${order_total:.2f}."
            )
        })

    record_refund_request(
        order_id,
        customer_id,
        amount_usd,
    )

    recent_count = recent_refund_request_count(
        customer_id,
        window_minutes=60,
    )

    requires_approval = (
        amount_usd
        >= settings.REFUND_APPROVAL_THRESHOLD_USD
    )

    anomaly = False

    if not requires_approval and recent_count >= 3:
        requires_approval = True
        anomaly = True

        log_guardrail_event(
            None,
            "anomaly_check",
            "flagged",
            (
                f"{recent_count} refund requests from "
                f"{customer_id} in the last 60 minutes; "
                f"individual request below the "
                f"${settings.REFUND_APPROVAL_THRESHOLD_USD:.2f} "
                "approval threshold."
            ),
        )

    return json.dumps({
        "order_id": order_id,
        "customer_id": customer_id,
        "amount_usd": amount_usd,
        "order_total_usd": order_total,
        "reason": reason,
        "requires_human_approval": requires_approval,
        "anomaly_flagged": anomaly,
    })


@crewai_tool("Create or escalate a support ticket")
def ticket_tool(
    customer_id: str,
    category: str,
    subject: str,
    order_id: str = "",
    escalate: bool = False,
) -> str:
    """Create a support ticket and optionally escalate it."""
    try:
        ticket = _run_async(
            ticketing_client.create_ticket(
                customer_id,
                category,
                subject,
                order_id,
            )
        )

        if escalate and "ticket_id" in ticket:
            ticket = _run_async(
                ticketing_client.escalate_ticket(
                    ticket["ticket_id"],
                    subject,
                )
            )

        return json.dumps(ticket)

    except Exception as exc:
        return json.dumps({
            "error": (
                f"Ticketing operation failed: "
                f"{type(exc).__name__}: {exc}"
            )
        })


def _build_crew() -> Crew:
    llm = crew_agent_llm()

    order_status_agent = Agent(
        role="Order Status Specialist",
        goal=(
            "Answer order-status and shipping questions accurately "
            "using the Order DB tool. Never guess order information."
        ),
        backstory=(
            "A NorthPeak support specialist who verifies every order "
            "against the operational database before writing a case note."
        ),
        llm=llm,
        tools=[
            lookup_order_tool,
            lookup_customer_orders_tool,
        ],
        allow_delegation=False,
        verbose=False,
    )

    refund_agent = Agent(
        role="Refund Specialist",
        goal=(
            f"Evaluate refund requests against the "
            f"${settings.REFUND_APPROVAL_THRESHOLD_USD:.2f} "
            "approval threshold and refund-anomaly checks. "
            "Use the refund decision tool for every refund request "
            "and never bypass its result."
        ),
        backstory=(
            "A NorthPeak refund specialist who verifies the order, "
            "customer, refund value, and approval requirements before "
            "making any recommendation."
        ),
        llm=llm,
        tools=[
            lookup_order_tool,
            process_refund_tool,
        ],
        allow_delegation=False,
        verbose=False,
    )

    billing_agent = Agent(
        role="Billing Dispute Specialist",
        goal=(
            "Resolve billing disputes by checking the real order first. "
            "Identify likely authorization holds and escalate genuine "
            "billing disputes through the ticketing tool."
        ),
        backstory=(
            "A NorthPeak billing specialist who verifies evidence "
            "before escalating a financial dispute."
        ),
        llm=llm,
        tools=[
            lookup_order_tool,
            ticket_tool,
        ],
        allow_delegation=False,
        verbose=False,
    )

    triage_task = Task(
        description=(
            "A NorthPeak employee submitted the following internal "
            "operations request.\n\n"

            "The employee is NOT the customer. Write the final summary "
            "as an internal employee case note, not as a customer-facing "
            "reply.\n\n"

            "Message: {message}\n"
            "Customer ID: {customer_id}\n"
            "Order ID: {order_id}\n\n"

            "Delegate to the appropriate support specialist.\n\n"

            "RULES:\n"
            "1. result_type must be exactly one of: "
            "'order_status', 'refund', 'billing_dispute'.\n"
            "2. For every refund request, the Refund Specialist must "
            "call 'Process a refund decision'.\n"
            "3. requires_human_approval and anomaly_flagged may only be "
            "True if the refund decision tool explicitly returned True.\n"
            "4. Never infer approval requirements from the wording of "
            "the request.\n"
            "5. Never set refund approval flags for an order-status or "
            "billing-dispute request.\n"
            "6. If a tool returns an error, report that error clearly "
            "instead of inventing order information.\n"
            "7. Preserve the actual refund amount returned by the refund "
            "decision tool in amount_usd.\n"
        ),
        expected_output=(
            "A structured SupportCrewOutput object containing: "
            "handled_by, result_type, summary, "
            "requires_human_approval, anomaly_flagged, "
            "order_id, and amount_usd."
        ),
        agent=order_status_agent,
        output_pydantic=SupportCrewOutput,
    )

    return Crew(
        agents=[
            order_status_agent,
            refund_agent,
            billing_agent,
        ],
        tasks=[triage_task],
        process=Process.hierarchical,
        manager_llm=llm,
        verbose=False,
    )


def _looks_like_raw_object_dump(text: str) -> bool:
    """
    Detect a CrewAI/Pydantic repr accidentally copied into summary text.
    """
    return (
        "handled_by=" in text
        and "result_type=" in text
    )


def _sanitize_payload(
    payload: dict,
    order_id: str,
) -> dict:
    """
    Normalize all support-crew outputs before returning to LangGraph.
    """
    result_type = payload.get(
        "result_type",
        "order_status",
    )

    if result_type not in _VALID_RESULT_TYPES:
        result_type = "order_status"

    summary = payload.get("summary", "") or ""

    if _looks_like_raw_object_dump(summary):
        summary = (
            "The support request was processed, but the generated "
            "summary was malformed. Please retry the request."
        )

    requires_human_approval = (
        bool(
            payload.get(
                "requires_human_approval",
                False,
            )
        )
        and result_type == "refund"
    )

    anomaly_flagged = (
        bool(
            payload.get(
                "anomaly_flagged",
                False,
            )
        )
        and result_type == "refund"
    )

    try:
        amount_usd = float(
            payload.get("amount_usd", 0.0)
            or 0.0
        )
    except (TypeError, ValueError):
        amount_usd = 0.0

    return {
        "handled_by": payload.get(
            "handled_by",
            "unknown",
        ),
        "result_type": result_type,
        "summary": summary,
        "requires_human_approval":
            requires_human_approval,
        "anomaly_flagged": anomaly_flagged,
        "order_id": payload.get(
            "order_id",
            order_id,
        ),
        "amount_usd": amount_usd,
    }


def run_support_crew(
    message: str,
    customer_id: str,
    order_id: str = "",
) -> dict:
    """
    Run the support crew and return a normalized dictionary.

    CrewAI's structured Pydantic output is preferred. Raw JSON is only
    used as a compatibility fallback.
    """
    try:
        crew = _build_crew()

        result = crew.kickoff(
            inputs={
                "message": message,
                "customer_id": customer_id,
                "order_id": order_id,
            }
        )

    except Exception as exc:
        return _sanitize_payload(
            {
                "handled_by": "unknown",
                "result_type": "order_status",
                "summary": (
                    "There was a technical issue while processing "
                    "the support request. Please retry shortly. "
                    f"Internal error: {type(exc).__name__}."
                ),
            },
            order_id,
        )

    # Preferred path: CrewAI already parsed output against
    # SupportCrewOutput because output_pydantic was configured.
    pydantic_result = getattr(
        result,
        "pydantic",
        None,
    )

    if pydantic_result is not None:
        try:
            payload = pydantic_result.model_dump()
            return _sanitize_payload(
                payload,
                order_id,
            )
        except Exception:
            pass

    # Compatibility fallback for CrewAI versions that only populate raw.
    raw = getattr(result, "raw", None)

    if isinstance(raw, str) and raw.strip():
        try:
            payload = json.loads(raw)
            return _sanitize_payload(
                payload,
                order_id,
            )
        except json.JSONDecodeError:
            pass

    return _sanitize_payload(
        {
            "handled_by": "unknown",
            "result_type": "order_status",
            "summary": (
                "The support request completed, but its structured "
                "result could not be interpreted. Please retry."
            ),
        },
        order_id,
    )