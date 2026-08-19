"""
CommerceOps AI — Approval Queue.
Paused sessions at human_approval_gate show here.
"""
import streamlit as st

from api_client import approve_chat, list_sessions
from style import header, inject, status_pill

st.set_page_config(
    page_title="Approval Queue",
    page_icon="✅",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject()

# SUB-PAGE HEADER: Clean title without brand prefix
header(
    "HUMAN APPROVAL QUEUE",
    "High-value refunds (≥ $250) and flagged security anomalies pause here for manual sign-off",
    is_first_page=False,
)

sessions = list_sessions()
pending = [s for s in sessions if s.get("status") == "awaiting_approval"] if sessions else []

if not pending:
    st.markdown(
        """
        <div class="coa-card" style="text-align: center; padding: 2.5rem;">
            <h3 style="margin-bottom: 0.5rem; font-weight: 300;">Queue Clear</h3>
            <p style="margin: 0;">No requests are currently awaiting human review.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    st.markdown(f"#### Pending Approvals ({len(pending)})")
    
    for s in pending:
        session_id = s["session_id"]
        
        with st.container():
            st.markdown(
                f"""
                <div class="coa-card">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <h4 style="margin: 0;">Session <code>{session_id}</code></h4>
                        {status_pill('awaiting_approval')}
                    </div>
                    <p style="font-size: 0.88rem; margin-top: 6px;">
                        Triggered threshold guardrail or rapid refund anomaly detection.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            c1, c2 = st.columns([1, 1], gap="medium")
            with c1:
                reviewer = st.text_input(
                    "Reviewer Name",
                    key=f"reviewer_{session_id}",
                    placeholder="e.g. Sarah Jenkins (Ops)",
                )
            with c2:
                comments = st.text_input(
                    "Audit Comments (Optional)",
                    key=f"comments_{session_id}",
                    placeholder="Reason for approval or denial...",
                )

            btn_col1, btn_col2, _ = st.columns([1, 1, 2])
            with btn_col1:
                if st.button("Approve Request", key=f"approve_{session_id}", use_container_width=True):
                    if not reviewer:
                        st.error("Please specify a reviewer name prior to approval.")
                    else:
                        approve_chat(session_id, True, reviewer, comments)
                        st.success(f"Session {session_id} approved successfully.")
                        st.rerun()

            with btn_col2:
                if st.button("Reject Request", key=f"reject_{session_id}", use_container_width=True):
                    if not reviewer:
                        st.error("Please specify a reviewer name prior to rejection.")
                    else:
                        approve_chat(session_id, False, reviewer, comments)
                        st.warning(f"Session {session_id} rejected.")
                        st.rerun()

            st.divider()