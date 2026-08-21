"""
CommerceOps AI — Market Intelligence.

Internal tool for on-demand competitive/trend reports, replacing the
old weekly manual analyst report. Under the hood this is the same Deep
Agent (plan -> research -> reflect) reachable via the Chat Console.
"""
import streamlit as st

from api_client import get_response, get_status, new_session_id, stream_status_events, submit_chat
from style import get_identity, header, inject

st.set_page_config(page_title="CommerceOps AI | Market Intelligence", page_icon="🌐", layout="wide")
inject()
header("🌐 Market Intelligence", "On-demand competitive & trend reports — plan → research → reflect.")

st.caption(
    "Researches against the synthetic competitor dataset shipped with this demo — no live web "
    "search dependency, so the report is reproducible and doesn't need an external API key."
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
    st.code("Summarize competitor pricing trends in outdoor jackets this quarter.", language="text")
    st.code("How does our hiking boot pricing compare to competitors?", language="text")

query = st.chat_input("Ask for a market or competitive research report...")

if query:
    with st.chat_message("user"):
        st.markdown(query)

    session_id = new_session_id()
    submit_chat(query, session_id, employee_name, employee_role, customer_id="STAFF-MARKETING")

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
