import streamlit as st

from api_client import (
    approve_chat,
    list_sessions,
)
from style import (
    get_identity,
    header,
    inject,
)


st.set_page_config(
    page_title="CommerceOps AI | Approval Queue",
    page_icon="✅",
    layout="wide",
)

inject()

header(
    "Human Approval Queue",
    "Review high-value refunds and requests flagged for "
    "manual operational approval.",
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

    st.caption(
        "Only Operations Managers can make approval decisions."
    )


# ---------------------------------------------------------
# Authorization
# ---------------------------------------------------------

if employee_role != "manager":
    st.error(
        "🔒 The Approval Queue is Manager-only. "
        "Support and Analyst roles can submit requests "
        "for approval but cannot approve them."
    )

    st.stop()


# ---------------------------------------------------------
# Pending sessions
# ---------------------------------------------------------

sessions = list_sessions()

pending = [
    session
    for session in sessions
    if session["status"] == "awaiting_approval"
]


if not pending:
    st.success(
        "Nothing is waiting for review right now."
    )

else:
    st.caption(
        f"{len(pending)} request(s) awaiting a decision."
    )

    for session in pending:
        session_id = session["session_id"]

        with st.container():
            st.markdown(
                f"#### Request `{session_id}`"
            )

            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown(
                    "**Submitted by**"
                )

                st.write(
                    session.get("employee_name")
                    or "Not recorded"
                )

            with col2:
                st.markdown(
                    "**Customer**"
                )

                st.write(
                    session.get("customer_id")
                    or "Not specified"
                )

            with col3:
                st.markdown(
                    "**Reviewer**"
                )

                st.write(employee_name)

            if session.get("last_message"):
                st.markdown(
                    "**Original employee request**"
                )

                st.info(
                    session["last_message"]
                )

            st.caption(
                "This workflow paused because it exceeded "
                "the configured approval threshold or "
                "triggered an operational anomaly."
            )

            comments = st.text_area(
                "Decision notes (optional)",
                key=f"comments_{session_id}",
            )

            approve_col, reject_col = st.columns(2)

            with approve_col:
                if st.button(
                    "✅ Approve",
                    key=f"approve_{session_id}",
                    use_container_width=True,
                ):
                    approve_chat(
                        session_id,
                        True,
                        employee_name,
                        comments,
                    )

                    st.success(
                        f"Session {session_id} approved."
                    )

                    st.rerun()

            with reject_col:
                if st.button(
                    "❌ Reject",
                    key=f"reject_{session_id}",
                    use_container_width=True,
                ):
                    approve_chat(
                        session_id,
                        False,
                        employee_name,
                        comments,
                    )

                    st.warning(
                        f"Session {session_id} rejected."
                    )

                    st.rerun()

            st.divider()