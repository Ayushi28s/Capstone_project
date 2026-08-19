"""
CommerceOps AI — Market Intelligence.

Internal tool for on-demand competitive/trend reports, replacing the
old weekly manual analyst report. Under the hood this is the same Deep
Agent (plan -> research -> reflect) reachable via the Chat Console.
"""
import streamlit as st

from api_client import get_response, get_status, new_session_id, stream_status_events, submit_chat
from style import header, inject

st.set_page_config(page_title="CommerceOps AI | Market Intelligence", page_icon="🌐", layout="wide")
inject()
header(" Market Intelligence", "On-demand competitive & trend reports — plan → research → reflect.")

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
        placeholder="e.g. Priya Shah", key="market_employee_name",
    )
    st.session_state["coa_employee_name"] = employee_name
    st.divider()
    st.markdown("### Try asking")
    st.code("Summarize competitor pricing trends in outdoor jackets this quarter.", language="text")
    st.code("How does our hiking boot pricing compare to competitors?", language="text")

active_role = st.session_state.get("user_role", "Operations Manager (Full Access)")
if active_role == "Tier 1 Support Specialist":
    st.warning("⚠️ **Notice**: You are viewing Market Intelligence under a **Tier 1 Support Specialist** persona (Read-Only Mode).")

st.caption(
    "Researches against the synthetic competitor dataset shipped with this demo — no live web "
    "search dependency, so the report is reproducible and doesn't need an external API key."
)

query = st.chat_input("Ask for a market or competitive research report...")

if query and not employee_name:
    st.error("Enter your name in the sidebar before submitting a request.")
elif query:
    with st.chat_message("user"):
        st.markdown(query)

    session_id = new_session_id()
    submit_chat(query, session_id, employee_name, customer_id="STAFF-MARKETING")

    with st.chat_message("assistant"):
        with st.spinner("Planning research → gathering findings → reflecting on confidence..."):
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