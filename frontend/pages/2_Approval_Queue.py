"""
CommerceOps AI — Approval Queue.

Every session paused at the human_approval_gate interrupt shows here,
including which NorthPeak employee submitted it, on behalf of which
customer, and the original request text — a manager reviewing this
queue needs that context, not just a session ID. Approving or rejecting
resumes the LangGraph thread from its checkpoint — survives a worker
restart, not just a log line.
"""
import streamlit as st

from api_client import approve_chat, list_sessions
from style import header, inject

st.set_page_config(page_title="CommerceOps AI | Approval Queue", page_icon="✅", layout="wide")
inject()

with st.sidebar:
    st.markdown("### 👤 Active Persona")
    st.selectbox(
        "Select Demo Role:",
        [
            "Operations Manager (Full Access)",
            "Tier 1 Support Specialist",
            "Merchandising Analyst",
        ],
        key="user_role",
    )
    st.divider()

active_role = st.session_state.get("user_role", "Operations Manager (Full Access)")

header(" Human Approval Queue", "Refunds ≥ $250 and flagged anomalies pause here until a manager decides.")

# Role-Based Access Control Gate: ONLY Operations Manager is allowed
if active_role != "Operations Manager (Full Access)":
    st.error(f"🔒 **Access Restricted**: `{active_role}` does not have manager approval privileges.")
    st.stop()

sessions = list_sessions()
pending = [s for s in sessions if s["status"] == "awaiting_approval"]

if not pending:
    st.success("Nothing waiting on review right now.")
else:
    st.caption(f"{len(pending)} request(s) awaiting a decision.")
    for s in pending:
        session_id = s["session_id"]
        with st.container():
            st.markdown(f"#### Session `{session_id}`")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Submitted by:** {s.get('employee_name') or '_(not recorded)_'}")
            with col2:
                st.markdown(f"**Customer:** {s.get('customer_id') or '_(not recorded)_'}")
            if s.get("last_message"):
                st.markdown("**Original request:**")
                st.info(s["last_message"])
            st.caption("This request exceeded the auto-approval threshold or triggered the rapid-request anomaly check.")

            reviewer = st.text_input("Your name (reviewer)", key=f"reviewer_{session_id}")
            comments = st.text_area("Comments (optional)", key=f"comments_{session_id}")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ Approve", key=f"approve_{session_id}", use_container_width=True):
                    if not reviewer:
                        st.error("Enter your name before deciding.")
                    else:
                        approve_chat(session_id, True, reviewer, comments)
                        st.success(f"Session {session_id} approved.")
                        st.rerun()
            with c2:
                if st.button("❌ Reject", key=f"reject_{session_id}", use_container_width=True):
                    if not reviewer:
                        st.error("Enter your name before deciding.")
                    else:
                        approve_chat(session_id, False, reviewer, comments)
                        st.warning(f"Session {session_id} rejected.")
                        st.rerun()
            st.divider()