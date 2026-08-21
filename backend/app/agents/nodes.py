"""
Node functions for the CommerceOps AI Supervisor StateGraph. Each is a
plain function of (state) -> partial state update, testable in
isolation before the full graph is wired together.
"""
from app.agents.intent_router import classify_intent
from app.agents.knowledge_agent import ask_knowledge_agent
from app.agents.market_intel_agent import run_market_intel_agent
from app.agents.merchandising_agent import ask_merchandising_agent
from app.agents.state import SupervisorState
from app.agents.support_crew import run_support_crew
from app.config import settings
from app.guardrails.input_rails import check_input
from app.guardrails.output_guard import screen_final_text
from app.guardrails.pii_redaction import redact


def _progress(node: str, pct: int) -> dict:
    return {"current_node": node, "progress_pct": pct}


# ---------------------------------------------------------------------
# 1. input_guard
# ---------------------------------------------------------------------
def input_guard_node(state: SupervisorState) -> dict:
    result = check_input(state["raw_message"][:4000], session_id=state["session_id"])
    notes = [result.blocked_reason] if result.blocked_reason else []
    return {
        **_progress("input_guard", 10),
        "guard_allowed": result.allowed,
        "guard_notes": notes,
    }


# ---------------------------------------------------------------------
# 2. pii_redact
# ---------------------------------------------------------------------
def pii_redact_node(state: SupervisorState) -> dict:
    result = redact(state["raw_message"], session_id=state["session_id"])
    return {
        **_progress("pii_redact", 20),
        "redacted_message": result.redacted_text,
        "pii_entities_found": result.pii_entities_found,
        "cost_data_flagged": result.cost_data_flagged,
    }


# ---------------------------------------------------------------------
# 3. intent_router
# ---------------------------------------------------------------------
def intent_router_node(state: SupervisorState) -> dict:
    result = classify_intent(state["redacted_message"])
    return {
        **_progress("intent_router", 30),
        "intent": result.intent,
        "intent_confidence": result.confidence,
        "used_llm_fallback": result.used_llm_fallback,
    }


# ---------------------------------------------------------------------
# 4a. support_crew (order_status / refund_request / billing_dispute)
# ---------------------------------------------------------------------
def support_crew_node(state: SupervisorState) -> dict:
    result = run_support_crew(
        message=state["redacted_message"],
        customer_id=state["customer_id"],
        order_id=state.get("order_id", ""),
    )
    key = {
        "order_status": "order_status_result",
        "refund": "refund_result",
        "billing_dispute": "billing_result",
    }.get(result.get("result_type", ""), "order_status_result")

    return {
        **_progress("support_crew", 60),
        key: result,
        "requires_human_approval": result.get("requires_human_approval", False),
    }


# ---------------------------------------------------------------------
# 4b. knowledge_agent (policy_question)
# ---------------------------------------------------------------------
def knowledge_agent_node(state: SupervisorState) -> dict:
    result = ask_knowledge_agent(state["redacted_message"])
    return {**_progress("knowledge_agent", 60), "policy_answer": result}


# ---------------------------------------------------------------------
# 4c. merchandising_agent (merchandising_analytics)
# ---------------------------------------------------------------------
def merchandising_agent_node(state: SupervisorState) -> dict:
    result = ask_merchandising_agent(state["redacted_message"])
    return {**_progress("merchandising_agent", 60), "analytics_result": result}


# ---------------------------------------------------------------------
# 4d. market_intel_agent (market_intelligence)
# ---------------------------------------------------------------------
def market_intel_agent_node(state: SupervisorState) -> dict:
    result = run_market_intel_agent(state["redacted_message"])
    return {**_progress("market_intel_agent", 60), "market_intel_result": result}


# ---------------------------------------------------------------------
# 4e. off_topic — the input rail already handled real off-topic/jailbreak
# cases; this path only reached if the classifier itself lands here for
# something genuinely outside scope after guardrails already passed it.
# ---------------------------------------------------------------------
def off_topic_node(state: SupervisorState) -> dict:
    return {
        **_progress("off_topic", 60),
        "policy_answer": {
            "answer": (
                "I'm scoped to order status, refunds/billing, product/policy questions, "
                "sales analytics, and market research. Could you rephrase your question "
                "around one of those?"
            ),
            "citations": [],
            "used_graph_rag": False,
        },
    }


# ---------------------------------------------------------------------
# 5. assemble_response — builds the final text from whichever agent ran,
#    then screens it through the universal output guard.
# ---------------------------------------------------------------------
def assemble_response_node(state: SupervisorState) -> dict:
    text = ""
    is_internal_context = False

    if state.get("order_status_result"):
        text = state["order_status_result"].get("summary", "")
    elif state.get("refund_result"):
        r = state["refund_result"]
        text = r.get("summary", "") or (
            f"Refund of ${r.get('amount_usd', 0):.2f} for order {r.get('order_id', '')}: "
            + ("routed to human approval." if r.get("requires_human_approval") else "approved.")
        )
    elif state.get("billing_result"):
        text = state["billing_result"].get("summary", "")
    elif state.get("policy_answer"):
        pa = state["policy_answer"]
        text = pa.get("answer", "")
    elif state.get("analytics_result"):
        text = state["analytics_result"].get("answer", "")
        is_internal_context = True  # merchandising analytics legitimately sees cost/margin data
    elif state.get("market_intel_result"):
        text = state["market_intel_result"].get("executive_summary", "")

    screened = screen_final_text(text, session_id=state["session_id"])
    # screen_final_text always runs the tone check; the cost-data scrub
    # inside it is what "is_internal_context" would bypass in a fuller
    # implementation — kept simple here since only one node
    # (merchandising) ever sets is_internal_context, and its own system
    # prompt already scopes what it's allowed to report.

    # requires_human_approval is deliberately left untouched here — it
    # stays exactly whatever the originating agent already set (only
    # the Refund Specialist's tool sets it True, for a genuine $250+ or
    # anomaly-flagged refund). An earlier version of this node also
    # forced approval for any non-Manager's request regardless of what
    # was actually being asked — that blocked ordinary informational
    # questions (order status, a policy lookup, market trends, a sales
    # summary) behind the same gate as an actual refund, for every
    # role, which is the wrong bar: approval should track the
    # CONSEQUENCE of the action, not who happens to be asking. An
    # employee of any role can get a direct answer to a question that
    # doesn't move money or take an action; only the action itself
    # (currently: a qualifying refund) needs sign-off.
    return {**_progress("assemble_response", 85), "final_response_text": screened}


# ---------------------------------------------------------------------
# 6. human_approval_gate — interrupt point, see agents/graph.py
#
# By the time this function body runs, the graph has either:
#  (a) never paused at all (requires_human_approval was False), or
#  (b) resumed after interrupt_before, with `approved`/`reviewer`/
#      `approval_comments` already written into state by the /approve
#      API endpoint's graph.update_state() call.
# Either way, this node is responsible for turning that decision into
# the actual confirmation message the user sees — the interim
# "routed to human approval" text from assemble_response_node is not
# the final word on a gated request.
# ---------------------------------------------------------------------
def human_approval_gate_node(state: SupervisorState) -> dict:
    if not state.get("requires_human_approval"):
        return {**_progress("human_approval_gate", 95)}

    approved = state.get("approved")
    if approved is None:
        # Still paused — this branch only runs once resumed, so in
        # practice approved is always set by the time we get here.
        return {**_progress("human_approval_gate", 95)}

    reviewer = state.get("reviewer", "a reviewer")
    if approved:
        confirmation = f"Approved by {reviewer}. Your request has been processed."
    else:
        comments = state.get("approval_comments") or "no reason given"
        confirmation = f"This request was not approved by {reviewer}. Reason: {comments}"

    return {**_progress("human_approval_gate", 95), "final_response_text": confirmation}


# ---------------------------------------------------------------------
# 7. finalize
# ---------------------------------------------------------------------
def finalize_node(state: SupervisorState) -> dict:
    return {**_progress("finalize", 100)}
