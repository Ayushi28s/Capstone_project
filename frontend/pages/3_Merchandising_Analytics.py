"""
CommerceOps AI — Merchandising Analytics.

Internal-only tool. Routes through the same Supervisor pipeline as the
Chat Console (so guardrails and tracing still apply uniformly), but
framed for staff self-serve analytics instead of customer support.
"""
import streamlit as st

from api_client import get_response, get_status, new_session_id, stream_status_events, submit_chat
from style import get_identity, header, inject, safe_markdown

st.set_page_config(page_title="CommerceOps AI | Merchandising Analytics", page_icon="📊", layout="wide")
inject()
header("📊 Merchandising Analytics", "Self-serve sales & inventory questions — replaces the weekly manual report.")

st.info(
    "Internal tool. This agent has legitimate access to wholesale cost and margin data for "
    "analysis — that access is scoped to this agent only and never reaches customer-facing flows."
)

with st.sidebar:
    employee_name, employee_role, role_label = get_identity()
    if not employee_name or not role_label:
        st.warning("Set your name and role on the main Portal page first.")
        if st.button("← Go to Portal"):
            st.switch_page("app.py")
        st.stop()
    st.markdown(f"### Signed in as\n**{employee_name}**  ·  {role_label}")
    st.divider()
    st.markdown("### Try asking")
    st.code("How many Denali Trail Jackets did we sell in the first week of June?", language="text")
    st.code("What's our total revenue by fulfillment center?", language="text")
    st.code("Which category has the highest margin?", language="text")

question = st.chat_input("Ask a sales, inventory, or margin question...")

if question:
    with st.chat_message("user"):
        st.markdown(question)

    session_id = new_session_id()
    submit_chat(question, session_id, employee_name, employee_role, customer_id="STAFF-MERCH")

    with st.chat_message("assistant"):
        progress_bar = st.progress(0)
        for event in stream_status_events(session_id):
            progress_bar.progress(min(event.get("progress_pct", 0), 100) / 100)
            if event.get("status") in ("completed", "failed", "rejected", "awaiting_approval"):
                break

        final = get_status(session_id)
        if final["status"] == "completed":
            resp = get_response(session_id)
            safe_markdown(resp["final_response_text"] if resp else "(no response)")
        elif final["status"] == "awaiting_approval":
            st.warning(
                "⚠️ This request needs a Manager's sign-off before it's finalized — routed to "
                "the **Approval Queue**. It will resume automatically once decided."
            )
        else:
            st.error(f"Status: {final['status']}" + (f" — {final['error']}" if final.get("error") else ""))
