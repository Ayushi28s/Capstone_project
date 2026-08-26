import asyncio
import json
import re

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
from app.mcp_tools import (
    order_db_client,
    ticketing_client,
)


# ---------------------------------------------------------
# Result types
# ---------------------------------------------------------

_VALID_RESULT_TYPES = {
    "order_status",
    "refund",
    "billing_dispute",
}


# ---------------------------------------------------------
# Structured output
# ---------------------------------------------------------

class SupportCrewOutput(BaseModel):
    handled_by: str = Field(
        description="Which support specialist handled this request"
    )

    result_type: str = Field(
        description="order_status | refund | billing_dispute"
    )

    summary: str

    requires_human_approval: bool = False

    anomaly_flagged: bool = False

    order_id: str = ""

    amount_usd: float = 0.0


# ---------------------------------------------------------
# Async helper
# ---------------------------------------------------------

def _run_async(coro):
    """
    CrewAI tools are synchronous while MCP clients are async.

    A fresh asyncio loop is used for every MCP call so the CrewAI tool
    remains synchronous and does not depend on a persistent event loop.
    """
    return asyncio.run(coro)


# ---------------------------------------------------------
# MCP-backed CrewAI tools
# ---------------------------------------------------------

@crewai_tool("Look up order status")
def lookup_order_tool(order_id: str) -> str:
    """
    Look up a single order.

    Returns verified order information including status, carrier,
    delivery estimate, customer, and recorded total.
    """
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
def lookup_customer_orders_tool(
    customer_id: str,
) -> str:
    """
    List all orders belonging to a customer.
    """
    try:
        result = _run_async(
            order_db_client.get_customer_orders(
                customer_id
            )
        )

        return json.dumps(result)

    except Exception as exc:
        return json.dumps({
            "error": (
                f"Customer-order lookup failed for "
                f"{customer_id}: "
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
    Validate a refund request.

    This tool does NOT issue money.

    It verifies:
    - order exists
    - order belongs to customer
    - refund amount is valid
    - refund amount does not exceed order value
    - approval threshold
    - rapid-request anomaly rules
    """

    order = get_order(order_id)

    if order is None:
        return json.dumps({
            "error": (
                f"No order found with ID {order_id}"
            )
        })

    if order["customer_id"] != customer_id:
        return json.dumps({
            "error": (
                f"Order {order_id} does not belong "
                f"to customer {customer_id}."
            )
        })

    if amount_usd <= 0:
        return json.dumps({
            "error": (
                "Refund amount must be greater than zero."
            )
        })

    order_total = float(
        order["total_amount_usd"]
    )

    if amount_usd > order_total:
        return json.dumps({
            "error": (
                f"Requested refund "
                f"${amount_usd:.2f} exceeds the "
                f"recorded order total of "
                f"${order_total:.2f}."
            )
        })

    # -----------------------------------------------------
    # Record request for anomaly detection
    # -----------------------------------------------------

    record_refund_request(
        order_id,
        customer_id,
        amount_usd,
    )

    recent_count = recent_refund_request_count(
        customer_id,
        window_minutes=60,
    )

    # -----------------------------------------------------
    # Approval threshold
    # -----------------------------------------------------

    requires_approval = (
        amount_usd
        >= settings.REFUND_APPROVAL_THRESHOLD_USD
    )

    anomaly = False

    # -----------------------------------------------------
    # Rapid-request anomaly
    # -----------------------------------------------------

    if (
        not requires_approval
        and recent_count >= 3
    ):
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
        "requires_human_approval":
            requires_approval,
        "anomaly_flagged":
            anomaly,
    })


@crewai_tool("Create or escalate a support ticket")
def ticket_tool(
    customer_id: str,
    category: str,
    subject: str,
    order_id: str = "",
    escalate: bool = False,
) -> str:
    """
    Create a support ticket and optionally escalate it.
    """

    try:
        ticket = _run_async(
            ticketing_client.create_ticket(
                customer_id,
                category,
                subject,
                order_id,
            )
        )

        if (
            escalate
            and "ticket_id" in ticket
        ):
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
                "Ticketing operation failed: "
                f"{type(exc).__name__}: {exc}"
            )
        })


# ---------------------------------------------------------
# Deterministic support sub-router
# ---------------------------------------------------------

_REFUND_PATTERNS = (
    r"\brefund\b",
    r"\brefunds\b",
    r"\brefunded\b",
    r"\breturn\b",
    r"\breturned\b",
    r"\breturning\b",
    r"\beligible for a refund\b",
    r"\brefund eligibility\b",
    r"\bmoney back\b",
    r"\breimburse\b",
    r"\breimbursement\b",
)

_BILLING_PATTERNS = (
    r"\bbilling\b",
    r"\bcharged twice\b",
    r"\bduplicate charge\b",
    r"\bdouble charged\b",
    r"\bpayment dispute\b",
    r"\bchargeback\b",
    r"\bauthorization hold\b",
    r"\bcard charge\b",
    r"\bincorrect charge\b",
)


def _contains_pattern(
    message: str,
    patterns: tuple[str, ...],
) -> bool:
    """
    Return True when any support-routing pattern matches.
    """

    lowered = message.lower()

    return any(
        re.search(pattern, lowered)
        for pattern in patterns
    )


def _support_route(message: str) -> str:
    """
    Select the support specialist deterministically.

    Refund language takes priority over billing/order-status because
    refund requests can also mention order status or payment language.
    """

    if _contains_pattern(
        message,
        _REFUND_PATTERNS,
    ):
        return "refund"

    if _contains_pattern(
        message,
        _BILLING_PATTERNS,
    ):
        return "billing_dispute"

    return "order_status"


# ---------------------------------------------------------
# Agents
# ---------------------------------------------------------

def _build_order_agent(llm) -> Agent:
    return Agent(
        role="Order Status Specialist",
        goal=(
            "Answer order-status, shipping, delivery, "
            "and customer-order-history questions using "
            "verified operational data. Never guess."
        ),
        backstory=(
            "A NorthPeak support specialist who verifies "
            "every order against the operational database "
            "before writing an internal employee case note."
        ),
        llm=llm,
        tools=[
            lookup_order_tool,
            lookup_customer_orders_tool,
        ],
        allow_delegation=False,
        verbose=False,
    )


def _build_refund_agent(llm) -> Agent:
    return Agent(
        role="Refund Specialist",
        goal=(
            "Handle refund eligibility and refund-processing "
            "requests. Verify the order and customer first. "
            "For every actual refund-processing request, use "
            "the refund decision tool and never bypass it."
        ),
        backstory=(
            "A NorthPeak refund specialist responsible for "
            "validating refunds against order data, order "
            "value, approval thresholds, and anomaly rules."
        ),
        llm=llm,
        tools=[
            lookup_order_tool,
            lookup_customer_orders_tool,
            process_refund_tool,
        ],
        allow_delegation=False,
        verbose=False,
    )


def _build_billing_agent(llm) -> Agent:
    return Agent(
        role="Billing Dispute Specialist",
        goal=(
            "Handle billing disputes, duplicate charges, "
            "authorization holds, and payment issues. "
            "Verify operational evidence before escalating."
        ),
        backstory=(
            "A NorthPeak billing specialist who validates "
            "order and payment context before opening or "
            "escalating a support case."
        ),
        llm=llm,
        tools=[
            lookup_order_tool,
            lookup_customer_orders_tool,
            ticket_tool,
        ],
        allow_delegation=False,
        verbose=False,
    )


# ---------------------------------------------------------
# Specialist tasks
# ---------------------------------------------------------

def _build_order_task(
    agent: Agent,
) -> Task:
    return Task(
        description=(
            "Handle this NorthPeak internal employee request "
            "as an ORDER STATUS / SHIPPING / ORDER HISTORY "
            "request.\n\n"

            "Message: {message}\n"
            "Customer ID: {customer_id}\n"
            "Order ID: {order_id}\n\n"

            "RULES:\n"
            "1. Use the order tools whenever a specific order "
            "or customer is referenced.\n"
            "2. Never invent status, carrier, dates, customer "
            "associations, or order details.\n"
            "3. If an order does not exist, say so clearly.\n"
            "4. If Customer ID and Order ID conflict, report "
            "the mismatch.\n"
            "5. Write the final summary as an internal "
            "NorthPeak employee case note.\n"
            "6. result_type must be 'order_status'.\n"
            "7. requires_human_approval=False.\n"
            "8. anomaly_flagged=False.\n"
        ),
        expected_output=(
            "A SupportCrewOutput object containing "
            "verified order information."
        ),
        agent=agent,
        output_pydantic=SupportCrewOutput,
    )


def _build_refund_task(
    agent: Agent,
) -> Task:
    return Task(
        description=(
            "Handle this NorthPeak internal employee request "
            "as a REFUND request.\n\n"

            "Message: {message}\n"
            "Customer ID: {customer_id}\n"
            "Order ID: {order_id}\n\n"

            "RULES:\n"
            "1. Verify the order and customer using the "
            "available order tools.\n"

            "2. If the request asks whether an order is "
            "eligible for a refund, verify the order state "
            "and explain the available eligibility context. "
            "Do NOT claim that money was refunded.\n"

            "3. If the employee asks to PROCESS, ISSUE, "
            "APPROVE, or SUBMIT a refund, you MUST call "
            "'Process a refund decision'.\n"

            "4. Never state that the refund decision tool "
            "is unavailable. It is available to this "
            "specialist.\n"

            "5. requires_human_approval may be True only "
            "when 'Process a refund decision' returns True.\n"

            "6. anomaly_flagged may be True only when "
            "'Process a refund decision' returns True.\n"

            "7. Preserve the actual amount returned by the "
            "refund decision tool in amount_usd.\n"

            "8. Never invent an amount, approval result, "
            "customer association, or refund outcome.\n"

            "9. If the amount is missing from an actual "
            "refund-processing request, state that the "
            "amount must be provided rather than inventing it.\n"

            "10. result_type must be 'refund'.\n"

            "11. Write the final summary as an internal "
            "NorthPeak employee case note.\n"
        ),
        expected_output=(
            "A SupportCrewOutput object containing the "
            "verified refund eligibility or refund decision."
        ),
        agent=agent,
        output_pydantic=SupportCrewOutput,
    )


def _build_billing_task(
    agent: Agent,
) -> Task:
    return Task(
        description=(
            "Handle this NorthPeak internal employee request "
            "as a BILLING DISPUTE request.\n\n"

            "Message: {message}\n"
            "Customer ID: {customer_id}\n"
            "Order ID: {order_id}\n\n"

            "RULES:\n"
            "1. Verify any referenced order first.\n"
            "2. Do not invent payment or order evidence.\n"
            "3. Use the support ticket tool when a genuine "
            "billing dispute requires escalation.\n"
            "4. result_type must be 'billing_dispute'.\n"
            "5. requires_human_approval=False.\n"
            "6. anomaly_flagged=False.\n"
            "7. Write the result as an internal NorthPeak "
            "employee case note.\n"
        ),
        expected_output=(
            "A SupportCrewOutput object describing the "
            "verified billing-dispute result."
        ),
        agent=agent,
        output_pydantic=SupportCrewOutput,
    )


# ---------------------------------------------------------
# Specialist Crew
# ---------------------------------------------------------

def _build_specialist_crew(
    route: str,
) -> Crew:
    """
    Create only the specialist needed for the current request.

    This prevents a specialist from seeing tools that do not belong to
    its role and prevents refund requests from landing on Order Status.
    """

    llm = crew_agent_llm()

    if route == "refund":
        agent = _build_refund_agent(llm)
        task = _build_refund_task(agent)

    elif route == "billing_dispute":
        agent = _build_billing_agent(llm)
        task = _build_billing_task(agent)

    else:
        agent = _build_order_agent(llm)
        task = _build_order_task(agent)

    return Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=False,
    )


# ---------------------------------------------------------
# Output normalization
# ---------------------------------------------------------

def _looks_like_raw_object_dump(
    text: str,
) -> bool:
    """
    Detect a Pydantic/CrewAI object repr accidentally copied into the
    summary field.
    """

    return (
        "handled_by=" in text
        and "result_type=" in text
    )


def _sanitize_payload(
    payload: dict,
    fallback_order_id: str,
    expected_result_type: str,
) -> dict:
    """
    Normalize all CrewAI results before sending them back to LangGraph.
    """

    result_type = payload.get(
        "result_type",
        expected_result_type,
    )

    # The deterministic route is authoritative.
    if result_type != expected_result_type:
        result_type = expected_result_type

    if result_type not in _VALID_RESULT_TYPES:
        result_type = "order_status"

    summary = (
        payload.get("summary", "")
        or ""
    )

    if _looks_like_raw_object_dump(summary):
        summary = (
            "The support request was processed, but "
            "the generated summary was malformed. "
            "Please retry the request."
        )

    requires_human_approval = bool(
        payload.get(
            "requires_human_approval",
            False,
        )
    )

    anomaly_flagged = bool(
        payload.get(
            "anomaly_flagged",
            False,
        )
    )

    # Approval flags are valid only for refunds.
    if result_type != "refund":
        requires_human_approval = False
        anomaly_flagged = False

    try:
        amount_usd = float(
            payload.get(
                "amount_usd",
                0.0,
            )
            or 0.0
        )

    except (TypeError, ValueError):
        amount_usd = 0.0

    resolved_order_id = (
        payload.get("order_id")
        or fallback_order_id
        or ""
    )

    return {
        "handled_by": payload.get(
            "handled_by",
            "unknown",
        ),
        "result_type": result_type,
        "summary": summary,
        "requires_human_approval":
            requires_human_approval,
        "anomaly_flagged":
            anomaly_flagged,
        "order_id":
            resolved_order_id,
        "amount_usd":
            amount_usd,
    }


# ---------------------------------------------------------
# Public entry point
# ---------------------------------------------------------

def run_support_crew(
    message: str,
    customer_id: str,
    order_id: str = "",
) -> dict:
    """
    Route and execute a support request.

    Flow:

        Support domain
             ↓
        Deterministic sub-route
             ↓
        ┌───────────┬─────────┬─────────────┐
        │           │         │             │
        Order     Refund    Billing
        │           │         │
        CrewAI    CrewAI    CrewAI
        │           │         │
        Tools      Tools      Tools
             ↓
        Structured SupportCrewOutput
    """

    route = _support_route(message)

    try:
        crew = _build_specialist_crew(
            route
        )

        result = crew.kickoff(
            inputs={
                "message": message,
                "customer_id":
                    customer_id or "",
                "order_id":
                    order_id or "",
            }
        )

    except Exception as exc:
        return _sanitize_payload(
            {
                "handled_by": "unknown",
                "result_type": route,
                "summary": (
                    "There was a technical issue while "
                    "processing the support request. "
                    "Please retry shortly. "
                    f"Internal error: "
                    f"{type(exc).__name__}."
                ),
                "requires_human_approval": False,
                "anomaly_flagged": False,
                "order_id": order_id,
                "amount_usd": 0.0,
            },
            order_id,
            route,
        )

    # -----------------------------------------------------
    # Preferred structured output
    # -----------------------------------------------------

    pydantic_result = getattr(
        result,
        "pydantic",
        None,
    )

    if pydantic_result is not None:
        try:
            payload = (
                pydantic_result.model_dump()
            )

            return _sanitize_payload(
                payload,
                order_id,
                route,
            )

        except Exception:
            pass

    # -----------------------------------------------------
    # Raw JSON fallback
    # -----------------------------------------------------

    raw = getattr(
        result,
        "raw",
        None,
    )

    if (
        isinstance(raw, str)
        and raw.strip()
    ):
        try:
            payload = json.loads(raw)

            return _sanitize_payload(
                payload,
                order_id,
                route,
            )

        except json.JSONDecodeError:
            pass

    # -----------------------------------------------------
    # Final fallback
    # -----------------------------------------------------

    return _sanitize_payload(
        {
            "handled_by": "unknown",
            "result_type": route,
            "summary": (
                "The support request completed, "
                "but its structured result could "
                "not be interpreted. Please retry."
            ),
            "requires_human_approval": False,
            "anomaly_flagged": False,
            "order_id": order_id,
            "amount_usd": 0.0,
        },
        order_id,
        route,
    )