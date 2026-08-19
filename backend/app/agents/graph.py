from langgraph.graph import END, START, StateGraph

from app.agents import nodes
from app.agents.state import SupervisorState
from app.config import settings

_compiled_graph = None


def _route_after_guard(state: SupervisorState) -> str:
    return "pii_redact" if state.get("guard_allowed", True) else END


def _route_by_intent(state: SupervisorState) -> str:
    intent = state.get("intent", "off_topic")

    return {
        "order_status": "support_crew",
        "refund_request": "support_crew",
        "billing_dispute": "support_crew",
        "policy_question": "knowledge_agent",
        "merchandising_analytics": "merchandising_agent",
        "market_intelligence": "market_intel_agent",
        "off_topic": "off_topic",
    }.get(intent, "off_topic")


def _route_after_response(state: SupervisorState) -> str:
    """
    Only requests explicitly marked as requiring human approval
    should enter the HITL approval gate.

    All normal requests bypass the approval node and finalize directly.
    """
    if state.get("requires_human_approval", False):
        return "human_approval_gate"

    return "finalize"


def build_graph():
    graph = StateGraph(SupervisorState)

    # -----------------------------
    # Nodes
    # -----------------------------
    graph.add_node("input_guard", nodes.input_guard_node)
    graph.add_node("pii_redact", nodes.pii_redact_node)
    graph.add_node("intent_router", nodes.intent_router_node)

    graph.add_node("support_crew", nodes.support_crew_node)
    graph.add_node("knowledge_agent", nodes.knowledge_agent_node)
    graph.add_node("merchandising_agent", nodes.merchandising_agent_node)
    graph.add_node("market_intel_agent", nodes.market_intel_agent_node)
    graph.add_node("off_topic", nodes.off_topic_node)

    graph.add_node("assemble_response", nodes.assemble_response_node)
    graph.add_node("human_approval_gate", nodes.human_approval_gate_node)
    graph.add_node("finalize", nodes.finalize_node)

    # -----------------------------
    # Input processing
    # -----------------------------
    graph.add_edge(START, "input_guard")

    graph.add_conditional_edges(
        "input_guard",
        _route_after_guard,
        {
            "pii_redact": "pii_redact",
            END: END,
        },
    )

    graph.add_edge("pii_redact", "intent_router")

    # -----------------------------
    # Intent routing
    # -----------------------------
    graph.add_conditional_edges(
        "intent_router",
        _route_by_intent,
        {
            "support_crew": "support_crew",
            "knowledge_agent": "knowledge_agent",
            "merchandising_agent": "merchandising_agent",
            "market_intel_agent": "market_intel_agent",
            "off_topic": "off_topic",
        },
    )

    # -----------------------------
    # Agent results
    # -----------------------------
    for agent_node in [
        "support_crew",
        "knowledge_agent",
        "merchandising_agent",
        "market_intel_agent",
        "off_topic",
    ]:
        graph.add_edge(agent_node, "assemble_response")

    # -----------------------------
    # HITL routing
    # -----------------------------
    graph.add_conditional_edges(
        "assemble_response",
        _route_after_response,
        {
            "human_approval_gate": "human_approval_gate",
            "finalize": "finalize",
        },
    )

    graph.add_edge("human_approval_gate", "finalize")
    graph.add_edge("finalize", END)

    # -----------------------------
    # Persistence / checkpointing
    # -----------------------------
    checkpointer = _get_checkpointer()

    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_approval_gate"],
    )


def _get_checkpointer():
    if settings.USE_REDIS_CHECKPOINTER:
        from langgraph.checkpoint.redis import RedisSaver

        saver = RedisSaver(settings.REDIS_URL)
        saver.setup()
        return saver

    from langgraph.checkpoint.sqlite import SqliteSaver
    import sqlite3

    conn = sqlite3.connect(
        settings.CHECKPOINT_DB_PATH,
        check_same_thread=False,
    )

    return SqliteSaver(conn)


def get_graph():
    global _compiled_graph

    if _compiled_graph is None:
        _compiled_graph = build_graph()

    return _compiled_graph


def resume_after_approval(
    session_id: str,
    approved: bool,
    reviewer: str,
    comments: str | None,
):
    """
    Resume a paused thread after a human decision.

    Rejecting still runs the thread through finalize so the audit
    trail and UI have a terminal state instead of leaving the graph
    paused indefinitely.
    """

    graph = get_graph()

    config = {
        "configurable": {
            "thread_id": session_id,
        }
    }

    graph.update_state(
        config,
        {
            "approved": approved,
            "reviewer": reviewer,
            "approval_comments": comments,
        },
    )

    return list(
        graph.stream(
            None,
            config,
            stream_mode="values",
        )
    )