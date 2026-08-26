"""
CommerceOps AI — Market Intelligence.

Internal NorthPeak research workspace.

Employees request competitive and market analysis while the Market
Intelligence Agent executes the plan → research → reflect workflow
through the same Supervisor pipeline used elsewhere in CommerceOps AI.
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
    page_title="CommerceOps AI | Market Intelligence",
    page_icon="🌐",
    layout="wide",
)

inject()

header(
    "Market Intelligence",
    "Generate on-demand competitive and market reports "
    "using a plan → research → reflect workflow.",
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

    st.markdown("### Example Research")

    st.code(
        "Summarize competitor pricing trends in "
        "outdoor jackets this quarter.",
        language="text",
    )

    st.code(
        "How does our hiking boot pricing compare "
        "with competitors?",
        language="text",
    )

    st.code(
        "What product trends are emerging in "
        "outdoor apparel?",
        language="text",
    )


query = st.chat_input(
    "Ask for a market or competitive research report..."
)


if query:
    with st.chat_message("user"):
        st.markdown(query)

    session_id = new_session_id()

    submit_chat(
        query,
        session_id,
        employee_name,
        employee_role,
        customer_id="STAFF-MARKETING",
        order_id="",
    )

    with st.chat_message("assistant"):
        with st.spinner(
            "Planning research → gathering findings "
            "→ reflecting on confidence..."
        ):
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