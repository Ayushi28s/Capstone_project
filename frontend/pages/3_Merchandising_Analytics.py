"""
CommerceOps AI — Merchandising Analytics.
"""
import streamlit as st
from api_client import get_response, get_status, new_session_id, stream_status_events, submit_chat
from style import header, inject

st.set_page_config(page_title="Merchandising Analytics", page_icon="📊", layout="wide")
inject()

# SUB-PAGE HEADER: Clean title without brand prefix
header(
    "MERCHANDISING ANALYTICS",
    "Self-serve catalog metrics, sales volume, and margin insights",
    is_first_page=False,
)

with st.sidebar:
    st.markdown("### Example Queries")
    sample_queries = [
        "How many Denali Trail Jackets were sold across fulfillment centers?",
        "What is our total revenue breakdown by fulfillment center?",
    ]
    for q in sample_queries:
        if st.button(q, key=f"m_{hash(q)}", use_container_width=True):
            st.session_state["m_input"] = q

default_query = st.session_state.pop("m_input", "")
question = st.chat_input("Query catalog or revenue metrics...")
active_query = question or default_query

if active_query:
    with st.chat_message("user", avatar="👤"):
        st.markdown(active_query)

    session_id = new_session_id()
    submit_chat(active_query, session_id, customer_id="STAFF-MERCH")

    with st.chat_message("assistant", avatar="📊"):
        progress_bar = st.progress(0)
        for event in stream_status_events(session_id):
            progress_bar.progress(min(event.get("progress_pct", 0), 100) / 100)
            if event.get("status") in ("completed", "failed", "rejected"):
                break
        progress_bar.empty()

        final = get_status(session_id)
        if final["status"] == "completed":
            resp = get_response(session_id)
            st.markdown(resp["final_response_text"] if resp else "(No data returned)")