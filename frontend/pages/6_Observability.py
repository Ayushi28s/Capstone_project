"""
CommerceOps AI — Observability.
Surfaces guardrail audit trails and integrates external monitoring dashboards.
"""
import os
import pandas as pd
import plotly.express as px
import streamlit as st

from api_client import get_guardrail_events
from style import STATUS_COLORS, header, inject

st.set_page_config(
    page_title="Observability",
    page_icon="🔭",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject()

# SUB-PAGE HEADER: Clean title without brand prefix
header(
    "OBSERVABILITY & AUDIT TRAIL",
    "Real-time event logging, rail interventions, and external tracing integrations",
    is_first_page=False,
)

grafana_url = os.environ.get("GRAFANA_URL", "http://localhost:3000/d/commerceops/commerceops-overview")
langsmith_project = os.environ.get("LANGCHAIN_PROJECT", "commerceops-ai")
phoenix_url = os.environ.get("PHOENIX_URL", "http://localhost:6006")

c1, c2, c3 = st.columns(3, gap="medium")

with c1:
    st.markdown(
        f"""
        <div class="coa-card">
            <h4 style="margin:0 0 8px 0;">📈 Grafana Telemetry</h4>
            <p style="font-size:0.85rem; margin-bottom:16px;">
                Latency metrics, request throughput, token consumption, and system health.
            </p>
            <a href="{grafana_url}" target="_blank" style="color:#4A4543; font-weight:600; font-size:0.85rem; text-decoration:none;">
                Open Grafana Dashboard ↗
            </a>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c2:
    st.markdown(
        f"""
        <div class="coa-card">
            <h4 style="margin:0 0 8px 0;">🔍 LangSmith Tracing</h4>
            <p style="font-size:0.85rem; margin-bottom:16px;">
                Detailed execution graphs across supervisor routing and specialized agents.
            </p>
            <a href="https://smith.langchain.com/o/-/projects/p/{langsmith_project}" target="_blank" style="color:#4A4543; font-weight:600; font-size:0.85rem; text-decoration:none;">
                Explore LangSmith Traces ↗
            </a>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c3:
    st.markdown(
        f"""
        <div class="coa-card">
            <h4 style="margin:0 0 8px 0;">🦅 Arize Phoenix Drift</h4>
            <p style="font-size:0.85rem; margin-bottom:16px;">
                RAG retrieval quality, embedding drift, and hallucination evaluations.
            </p>
            <a href="{phoenix_url}" target="_blank" style="color:#4A4543; font-weight:600; font-size:0.85rem; text-decoration:none;">
                Launch Phoenix Console ↗
            </a>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

st.markdown("### Guardrail Audit Log")
events = get_guardrail_events(limit=200)

if events:
    df = pd.DataFrame(events)
    
    col_filter, col_chart = st.columns([1, 1], gap="medium")
    
    with col_filter:
        rail_options = sorted(df["rail_type"].unique()) if "rail_type" in df.columns else []
        rail_filter = st.multiselect(
            "Filter Event Log by Rail Type",
            options=rail_options,
            default=rail_options,
        )
        
        filtered = df[df["rail_type"].isin(rail_filter)] if "rail_type" in df.columns else df
        
        st.dataframe(
            filtered[["occurred_at", "session_id", "rail_type", "action", "detail"]],
            column_config={
                "occurred_at": st.column_config.TextColumn("Timestamp"),
                "session_id": st.column_config.TextColumn("Session ID"),
                "rail_type": st.column_config.TextColumn("Rail Type"),
                "action": st.column_config.TextColumn("Action"),
                "detail": st.column_config.TextColumn("Details", width="large"),
            },
            use_container_width=True,
            hide_index=True,
            height=300,
        )

    with col_chart:
        st.markdown("#### Action Distribution")
        action_counts = df["action"].value_counts().reset_index()
        action_counts.columns = ["action", "count"]
        
        fig = px.bar(
            action_counts,
            x="action",
            y="count",
            color="action",
            color_discrete_map=STATUS_COLORS,
            text="count",
        )
        fig.update_traces(textposition="outside", marker_line_width=0)
        fig.update_layout(
            showlegend=False,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=280,
            margin=dict(l=10, r=10, t=20, b=10),
            xaxis=dict(title="", showgrid=False, tickfont=dict(color="#8C8581")),
            yaxis=dict(title="", showgrid=True, gridcolor="#EBE5DF", tickfont=dict(color="#8C8581")),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
else:
    st.info("No guardrail events logged yet.")