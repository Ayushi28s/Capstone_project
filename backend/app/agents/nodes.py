from app.agents.intent_router import classify_intent
from app.agents.knowledge_agent import ask_knowledge_agent
from app.agents.market_intel_agent import run_market_intel_agent
from app.agents.merchandising_agent import ask_merchandising_agent
from app.agents.state import SupervisorState
from app.agents.support_crew import run_support_crew

from app.db import (
    get_existing_approved_refund,
    update_latest_refund_decision,
)

from app.guardrails.input_rails import check_input
from app.guardrails.output_guard import screen_final_text
from app.guardrails.pii_redaction import redact


def _progress(
    node: str,
    pct: int,
) -> dict:
    return {
        "current_node": node,
        "progress_pct": pct,
    }


def input_guard_node(
    state: SupervisorState,
) -> dict:
    result = check_input(
        state["raw_message"][:4000],
        session_id=state["session_id"],
    )

    notes = (
        [result.blocked_reason]
        if result.blocked_reason
        else []
    )

    return {
        **_progress(
            "input_guard",
            10,
        ),
        "guard_allowed": result.allowed,
        "guard_notes": notes,
    }


def pii_redact_node(
    state: SupervisorState,
) -> dict:
    result = redact(
        state["raw_message"],
        session_id=state["session_id"],
    )

    return {
        **_progress(
            "pii_redact",
            20,
        ),
        "redacted_message": result.redacted_text,
        "pii_entities_found": result.pii_entities_found,
        "cost_data_flagged": result.cost_data_flagged,
    }


def intent_router_node(
    state: SupervisorState,
) -> dict:
    result = classify_intent(
        state["redacted_message"]
    )

    return {
        **_progress(
            "intent_router",
            30,
        ),
        "intent": result.intent,
        "intent_confidence": result.confidence,
        "used_llm_fallback": result.used_llm_fallback,
    }


def support_crew_node(
    state: SupervisorState,
) -> dict:
    result = run_support_crew(
        message=state["redacted_message"],
        customer_id=state["customer_id"],
        order_id=state.get(
            "order_id",
            "",
        ),
    )

    result_type = result.get(
        "result_type",
        "",
    )

    key = {
        "order_status": "order_status_result",
        "refund": "refund_result",
        "billing_dispute": "billing_result",
    }.get(
        result_type,
        "order_status_result",
    )

    requires_approval = result.get(
        "requires_human_approval",
        False,
    )

    # ---------------------------------------------------------------
    # Reuse a previous approval for an identical refund request.
    # ---------------------------------------------------------------

    if (
        result_type == "refund"
        and requires_approval
    ):
        order_id = result.get(
            "order_id",
            state.get(
                "order_id",
                "",
            ),
        )

        customer_id = state.get(
            "customer_id",
            "",
        )

        amount_usd = float(
            result.get(
                "amount_usd",
                0,
            )
            or 0
        )

        if (
            order_id
            and customer_id
            and amount_usd > 0
        ):
            previous_approval = (
                get_existing_approved_refund(
                    order_id=order_id,
                    customer_id=customer_id,
                    amount_usd=amount_usd,
                )
            )

            if previous_approval:
                requires_approval = False

                result[
                    "requires_human_approval"
                ] = False

                result[
                    "previously_approved"
                ] = True

                result["summary"] = (
                    f"The ${amount_usd:.2f} refund "
                    f"for order {order_id} was "
                    "previously approved. "
                    "No additional human approval "
                    "is required."
                )

    return {
        **_progress(
            "support_crew",
            60,
        ),
        key: result,
        "requires_human_approval": requires_approval,
    }


def knowledge_agent_node(
    state: SupervisorState,
) -> dict:
    result = ask_knowledge_agent(
        state["redacted_message"]
    )

    return {
        **_progress(
            "knowledge_agent",
            60,
        ),
        "policy_answer": result,
    }


def merchandising_agent_node(
    state: SupervisorState,
) -> dict:
    result = ask_merchandising_agent(
        state["redacted_message"]
    )

    return {
        **_progress(
            "merchandising_agent",
            60,
        ),
        "analytics_result": result,
    }


def market_intel_agent_node(
    state: SupervisorState,
) -> dict:
    result = run_market_intel_agent(
        state["redacted_message"]
    )

    return {
        **_progress(
            "market_intel_agent",
            60,
        ),
        "market_intel_result": result,
    }


def off_topic_node(
    state: SupervisorState,
) -> dict:
    return {
        **_progress(
            "off_topic",
            60,
        ),
        "policy_answer": {
            "answer": (
                "I'm scoped to order status, "
                "refunds/billing, product/policy "
                "questions, sales analytics, and "
                "market research. Could you rephrase "
                "your question around one of those?"
            ),
            "citations": [],
            "used_graph_rag": False,
        },
    }


def assemble_response_node(
    state: SupervisorState,
) -> dict:
    text = ""

    if state.get("order_status_result"):
        text = state[
            "order_status_result"
        ].get(
            "summary",
            "",
        )

    elif state.get("refund_result"):
        result = state["refund_result"]

        text = (
            result.get(
                "summary",
                "",
            )
            or (
                f"Refund of "
                f"${result.get('amount_usd', 0):.2f} "
                f"for order "
                f"{result.get('order_id', '')}: "
                + (
                    "routed to human approval."
                    if result.get(
                        "requires_human_approval"
                    )
                    else "approved."
                )
            )
        )

    elif state.get("billing_result"):
        text = state[
            "billing_result"
        ].get(
            "summary",
            "",
        )

    elif state.get("policy_answer"):
        policy_answer = state[
            "policy_answer"
        ]

        text = policy_answer.get(
            "answer",
            "",
        )

    elif state.get("analytics_result"):
        text = state[
            "analytics_result"
        ].get(
            "answer",
            "",
        )

    elif state.get("market_intel_result"):
        text = state[
            "market_intel_result"
        ].get(
            "executive_summary",
            "",
        )

    screened = screen_final_text(
        text,
        session_id=state["session_id"],
    )

    return {
        **_progress(
            "assemble_response",
            85,
        ),
        "final_response_text": screened,
    }


def human_approval_gate_node(
    state: SupervisorState,
) -> dict:
    if not state.get(
        "requires_human_approval"
    ):
        return {
            **_progress(
                "human_approval_gate",
                95,
            )
        }

    approved = state.get(
        "approved"
    )

    if approved is None:
        return {
            **_progress(
                "human_approval_gate",
                95,
            )
        }

    # ---------------------------------------------------------------
    # Persist the decision against the matching business refund.
    # ---------------------------------------------------------------

    refund_result = state.get(
        "refund_result"
    )

    if refund_result:
        order_id = refund_result.get(
            "order_id",
            state.get(
                "order_id",
                "",
            ),
        )

        customer_id = state.get(
            "customer_id",
            "",
        )

        amount_usd = float(
            refund_result.get(
                "amount_usd",
                0,
            )
            or 0
        )

        if (
            order_id
            and customer_id
            and amount_usd > 0
        ):
            update_latest_refund_decision(
                order_id=order_id,
                customer_id=customer_id,
                amount_usd=amount_usd,
                approved=bool(
                    approved
                ),
            )

    reviewer = state.get(
        "reviewer",
        "a reviewer",
    )

    if approved:
        confirmation = (
            f"Approved by {reviewer}. "
            "Your request has been processed."
        )

    else:
        comments = (
            state.get(
                "approval_comments"
            )
            or "no reason given"
        )

        confirmation = (
            f"This request was not approved "
            f"by {reviewer}. "
            f"Reason: {comments}"
        )

    return {
        **_progress(
            "human_approval_gate",
            95,
        ),
        "final_response_text": confirmation,
    }


def finalize_node(
    state: SupervisorState,
) -> dict:
    return {
        **_progress(
            "finalize",
            100,
        )
    }