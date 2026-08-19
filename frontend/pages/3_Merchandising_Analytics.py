"""
CommerceOps AI — Merchandising Analytics.

Internal-only tool. Routes through the same Supervisor pipeline as the
Chat Console (so guardrails and tracing still apply uniformly), but
framed for staff self-serve analytics instead of customer support.
"""
import streamlit as st

from api_client import get_response, get_status, new_session_id, stream_status_events, submit_chat
from style import header, inject

st.set_page_config(page_title="CommerceOps AI | Merchandising Analytics", page_icon="📊", layout="wide")
inject()
header("📊 Merchandising Analytics", "Self-serve sales & inventory questions — replaces the weekly manual report.")

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
    employee_name = st.text_input(
        "Your name", value=st.session_state.get("coa_employee_name", ""),
        placeholder="e.g. Priya Shah", key="merch_employee_name",
    )
    st.session_state["coa_employee_name"] = employee_name
    st.divider()
    st.markdown("### Try asking")
    st.code("How many Denali Trail Jackets did we sell in the first week of June?", language="text")
    st.code("What's our total revenue by fulfillment center?", language="text")
    st.code("Which category has the highest margin?", language="text")

active_role = st.session_state.get("user_role", "Operations Manager (Full Access)")
if active_role == "Tier 1 Support Specialist":
    st.warning("⚠️ **Notice**: You are viewing Merchandising Analytics under a **Tier 1 Support Specialist** persona (Read-Only Mode).")

st.info(
    "Internal tool. This agent has legitimate access to wholesale cost and margin data for "
    "analysis — that access is scoped to this agent only and never reaches customer-facing flows."
)

question = st.chat_input("Ask a sales, inventory, or margin question...")

if question and not employee_name:
    st.error("Enter your name in the sidebar before submitting a request.")
elif question:
    with st.chat_message("user"):
        st.markdown(question)

    session_id = new_session_id()
    submit_chat(question, session_id, employee_name, customer_id="STAFF-MERCH")

    with st.chat_message("assistant"):
        progress_bar = st.progress(0)
        for event in stream_status_events(session_id):
            progress_bar.progress(min(event.get("progress_pct", 0), 100) / 100)
            if event.get("status") in ("completed", "failed", "rejected"):
                break

        final = get_status(session_id)
        if final["status"] == "completed":
            resp = get_response(session_id)
            st.markdown(resp["final_response_text"] if resp else "(no response)")
        else:
            st.error(f"Status: {final['status']} — {final.get('error', '')}")