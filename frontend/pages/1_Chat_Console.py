"""
CommerceOps AI — Chat Console.

Internal NorthPeak employee tool.

Support, merchandising, and operations staff describe what they need
in natural language. The Supervisor Orchestrator classifies the request
and routes it to the appropriate workflow automatically.

Customer and order identifiers are extracted from the current request
when present. Employees do not need to duplicate request context in
separate sidebar fields.
"""

import re

import streamlit as st

from api_client import (
    get_response,
    get_status,
    new_session_id,
    stream_status_events,
    submit_chat,
)
from style import (
    get_identity,
    header,
    inject,
    safe_markdown,
    status_pill,
)


st.set_page_config(
    page_title="CommerceOps AI | Chat Console",
    page_icon="💬",
    layout="wide",
)

inject()

header(
    "Chat Console — NorthPeak Employee Tool",
    "Describe the operational task in natural language. "
    "The Supervisor identifies the request context and routes it "
    "to the appropriate specialist automatically.",
)


NODE_LABELS = {
    "input_guard": "Screening input (NeMo Guardrails)",
    "pii_redact": "Redacting sensitive information (Presidio)",
    "intent_router": "Classifying intent (lightweight classifier)",
    "support_crew": "Support Triage Crew working (CrewAI)",
    "knowledge_agent": (
        "Knowledge Agent searching policy docs / knowledge graph"
    ),
    "merchandising_agent": (
        "Merchandising Analytics Agent querying operational data"
    ),
    "market_intel_agent": (
        "Market Intelligence Agent researching "
        "(plan → research → reflect)"
    ),
    "off_topic": "Off-topic — declining politely",
    "assemble_response": "Validating output (Guardrails AI)",
    "human_approval_gate": "Awaiting human approval",
    "finalize": "Finalizing response",
}


CUSTOMER_PATTERN = re.compile(
    r"\bCUST-\d+\b",
    re.IGNORECASE,
)

ORDER_PATTERN = re.compile(
    r"\bNP-\d+\b",
    re.IGNORECASE,
)


def extract_context(message: str) -> tuple[str, str]:
    """
    Extract explicit NorthPeak customer and order identifiers from the
    current employee request.

    Empty strings are returned when an identifier is not present.
    """

    customer_match = CUSTOMER_PATTERN.search(message)
    order_match = ORDER_PATTERN.search(message)

    customer_id = (
        customer_match.group(0).upper()
        if customer_match
        else ""
    )

    order_id = (
        order_match.group(0).upper()
        if order_match
        else ""
    )

    return customer_id, order_id


# ---------------------------------------------------------
# Sidebar
# ---------------------------------------------------------

with st.sidebar:
    employee_name, employee_role, role_label = get_identity()

    if not employee_name or not role_label:
        st.warning(
            "Set your name and role on the main Portal page first."
        )

        if st.button("← Go to Portal"):
            st.switch_page("app.py")

        st.stop()

    st.markdown(
        f"### Signed in as\n"
        f"**{employee_name}**  ·  {role_label}"
    )

    st.divider()

    st.markdown("### Example Requests")

    st.code(
        "Where is order NP-88213 for customer CUST-001?",
        language="text",
    )

    st.code(
        "What orders belong to customer CUST-002?",
        language="text",
    )

    st.code(
        "Process a $310 refund for order NP-77410 "
        "(CUST-002) — arrived damaged.",
        language="text",
    )

    st.code(
        "What's our return policy on worn hiking boots?",
        language="text",
    )

    st.code(
        "Which customers have returned SKU-88213 "
        "more than once?",
        language="text",
    )

    st.code(
        "What's our escalation procedure for a customer "
        "threatening a chargeback?",
        language="text",
    )

    st.caption(
        "Include an Order ID or Customer ID directly in the "
        "request whenever the question relates to a specific record."
    )


# ---------------------------------------------------------
# Chat history
# ---------------------------------------------------------

if "coa_chat_history" not in st.session_state:
    st.session_state.coa_chat_history = []


for turn in st.session_state.coa_chat_history:
    with st.chat_message(turn["role"]):
        st.markdown(turn["content"])


message = st.chat_input(
    "Ask about an order, refund, billing, policy, "
    "analytics, or market trends..."
)


# ---------------------------------------------------------
# Submit request
# ---------------------------------------------------------

if message:
    st.session_state.coa_chat_history.append(
        {
            "role": "user",
            "content": message,
        }
    )

    with st.chat_message("user"):
        st.markdown(message)

    customer_id, order_id = extract_context(message)

    session_id = new_session_id()

    submit_chat(
        message,
        session_id,
        employee_name,
        employee_role,
        customer_id,
        order_id,
    )

    with st.chat_message("assistant"):
        progress_bar = st.progress(0)
        status_line = st.empty()
        node_log = st.container()

        seen_nodes = []

        for event in stream_status_events(session_id):
            pct = event.get("progress_pct", 0)
            node = event.get("current_node")
            status = event.get("status")

            progress_bar.progress(
                min(pct, 100) / 100
            )

            status_line.markdown(
                f"{status_pill(status)}  ·  "
                f"`{node or '—'}`",
                unsafe_allow_html=True,
            )

            if node and node not in seen_nodes:
                seen_nodes.append(node)

                with node_log:
                    st.caption(
                        f"✅ {NODE_LABELS.get(node, node)}"
                    )

            if status in (
                "completed",
                "failed",
                "rejected",
            ):
                break

            if status == "awaiting_approval":
                st.warning(
                    "⚠️ This request requires manager approval "
                    "and has been routed to the "
                    "**Approval Queue**. Processing will resume "
                    "automatically after a decision."
                )
                break

        final = get_status(session_id)

        if final["status"] == "completed":
            resp = get_response(session_id)

            answer = (
                resp["final_response_text"]
                if resp
                else "(no response text)"
            )

            st.markdown("---")

            safe_markdown(answer)

            st.session_state.coa_chat_history.append(
                {
                    "role": "assistant",
                    "content": answer,
                }
            )

        elif final["status"] == "rejected":
            error = final.get(
                "error",
                "guardrail rejection",
            )

            st.error(
                f"Request blocked: {error}"
            )

            st.session_state.coa_chat_history.append(
                {
                    "role": "assistant",
                    "content": f"🚫 Blocked: {error}",
                }
            )

        elif final["status"] == "failed":
            st.error(
                "Something went wrong: "
                f"{final.get('error', 'unknown error')}"
            )

        elif final["status"] == "awaiting_approval":
            st.session_state.coa_chat_history.append(
                {
                    "role": "assistant",
                    "content": (
                        "⏳ Routed to the Approval Queue — "
                        "awaiting manager sign-off."
                    ),
                }
            )

    st.session_state["last_session_id"] = session_id


if "last_session_id" in st.session_state:
    st.caption(
        f"Last session ID: "
        f"`{st.session_state['last_session_id']}`"
        f"  ·  Logged under: "
        f"`{employee_name}` ({employee_role})"
    )