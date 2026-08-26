"""
CommerceOps AI — Merchandising Analytics.

Internal NorthPeak analytics workspace.

This page sends merchandising questions through the same Supervisor
pipeline used by the Chat Console, preserving guardrails, observability,
and centralized routing while giving authorized employees a focused
analytics workspace.
"""

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
    page_title="CommerceOps AI | Merchandising Analytics",
    page_icon="📊",
    layout="wide",
)

inject()

header(
    "Merchandising Analytics",
    "Ask sales, inventory, revenue, and margin questions "
    "using NorthPeak's internal operational data.",
)


st.info(
    "Internal workspace. The Merchandising Analytics Agent "
    "has authorized access to wholesale cost and margin data. "
    "That information is isolated from customer-facing workflows."
)


# ---------------------------------------------------------
# Identity
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

    st.markdown("### Example Questions")

    st.code(
        "How many Denali Trail Jackets did we sell "
        "in the first week of June?",
        language="text",
    )

    st.code(
        "What's our total revenue by fulfillment center?",
        language="text",
    )

    st.code(
        "Which product category has the highest margin?",
        language="text",
    )

    st.code(
        "Which SKU generated the most revenue this month?",
        language="text",
    )


question = st.chat_input(
    "Ask a sales, inventory, revenue, or margin question..."
)


if question:
    with st.chat_message("user"):
        st.markdown(question)

    session_id = new_session_id()

    submit_chat(
        question,
        session_id,
        employee_name,
        employee_role,
        customer_id="STAFF-MERCH",
        order_id="",
    )

    with st.chat_message("assistant"):
        progress_bar = st.progress(0)
        status_line = st.empty()

        for event in stream_status_events(session_id):
            progress = min(
                event.get("progress_pct", 0),
                100,
            )

            progress_bar.progress(
                progress / 100
            )

            status = event.get("status")
            node = event.get("current_node")

            status_line.markdown(
                f"{status_pill(status)}  ·  "
                f"`{node or '—'}`",
                unsafe_allow_html=True,
            )

            if status in (
                "completed",
                "failed",
                "rejected",
                "awaiting_approval",
            ):
                break

        final = get_status(session_id)

        if final["status"] == "completed":
            resp = get_response(session_id)

            safe_markdown(
                resp["final_response_text"]
                if resp
                else "(no response)"
            )

        elif final["status"] == "awaiting_approval":
            st.warning(
                "⚠️ This operation requires Manager approval "
                "and has been routed to the Approval Queue."
            )

        elif final["status"] == "rejected":
            st.error(
                "Request blocked by operational guardrails."
            )

        else:
            error = final.get("error")

            st.error(
                f"Status: {final['status']}"
                + (
                    f" — {error}"
                    if error
                    else ""
                )
            )