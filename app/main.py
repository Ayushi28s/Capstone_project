"""
CommerceOps AI FastAPI backend. Thin by design — the real work happens
in app.worker (the background pipeline) and app.agents.graph (the
resumable Supervisor StateGraph).
"""
import asyncio
import json
import os

import redis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from sse_starlette.sse import EventSourceResponse

from app.agents.graph import resume_after_approval
from app.config import settings
from app.db import (
    create_job, get_job, init_db, list_guardrail_events, list_jobs, record_approval,
)
from app.schemas import (
    ApprovalDecision, ChatJobStatus, ChatRequest, GuardrailEventOut,
    ToneTestRequest, ToneTestResponse,
)
from app.observability.tracing import init_observability

app = FastAPI(title="CommerceOps AI Capstone API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
app.mount("/metrics", make_asgi_app())


@app.on_event("startup")
def on_startup():
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    init_db()
    init_observability()


@app.get("/health")
def health():
    return {"status": "ok", "env": settings.APP_ENV, "model": settings.MODEL}


@app.post("/chat")
def submit_chat(req: ChatRequest):
    create_job(req.session_id, req.message)
    payload = json.dumps({
        "session_id": req.session_id, "message": req.message,
        "customer_id": req.customer_id, "order_id": req.order_id,
    })
    _redis.rpush(settings.JOB_QUEUE_KEY, payload)
    return {"session_id": req.session_id, "status": "queued"}


@app.get("/chat/{session_id}/status", response_model=ChatJobStatus)
def get_status(session_id: str):
    row = get_job(session_id)
    if row is None:
        raise HTTPException(404, "Unknown session_id")
    return ChatJobStatus(
        session_id=row["session_id"], status=row["status"], current_node=row["current_node"],
        progress_pct=row["progress_pct"] or 0, error=row["error"],
    )


@app.get("/chat/{session_id}/stream")
async def stream_status(session_id: str):
    async def event_generator():
        last_payload = None
        while True:
            row = get_job(session_id)
            if row is None:
                yield {"event": "error", "data": "unknown session_id"}
                return
            payload = json.dumps({
                "status": row["status"], "current_node": row["current_node"],
                "progress_pct": row["progress_pct"] or 0, "error": row["error"],
            })
            if payload != last_payload:
                yield {"event": "update", "data": payload}
                last_payload = payload
            if row["status"] in ("completed", "failed", "rejected", "awaiting_approval"):
                return
            await asyncio.sleep(1.0)

    return EventSourceResponse(event_generator())


@app.get("/chat/{session_id}/response")
def get_response(session_id: str):
    from app.agents.graph import get_graph
    graph = get_graph()
    config = {"configurable": {"thread_id": session_id}}
    snapshot = graph.get_state(config)
    if not snapshot or not snapshot.values:
        raise HTTPException(404, "No response available yet.")
    return {
        "session_id": session_id,
        "final_response_text": snapshot.values.get("final_response_text", ""),
        "intent": snapshot.values.get("intent"),
        "requires_human_approval": snapshot.values.get("requires_human_approval", False),
    }


@app.get("/chat/sessions", response_model=list[ChatJobStatus])
def list_sessions():
    return [
        ChatJobStatus(
            session_id=row["session_id"], status=row["status"], current_node=row["current_node"],
            progress_pct=row["progress_pct"] or 0, error=row["error"],
        )
        for row in list_jobs()
    ]


@app.post("/chat/{session_id}/approve")
def approve_chat(session_id: str, decision: ApprovalDecision):
    row = get_job(session_id)
    if row is None:
        raise HTTPException(404, "Unknown session_id")
    if row["status"] != "awaiting_approval":
        raise HTTPException(409, f"Session is in status '{row['status']}', not awaiting approval.")

    record_approval(session_id, decision.approved, decision.reviewer, decision.comments)
    resume_after_approval(session_id, decision.approved, decision.reviewer, decision.comments)

    from app.db import update_job
    from app.observability.metrics import record_hitl_decision
    final_status = "completed" if decision.approved else "rejected"
    update_job(session_id, status=final_status, progress_pct=100)
    record_hitl_decision(decision.approved)
    return {"session_id": session_id, "status": final_status}


@app.get("/guardrails/events", response_model=list[GuardrailEventOut])
def guardrail_events(limit: int = 100, session_id: str | None = None):
    return [
        GuardrailEventOut(
            id=r["id"], session_id=r["session_id"], rail_type=r["rail_type"],
            action=r["action"], detail=r["detail"], occurred_at=r["occurred_at"],
        )
        for r in list_guardrail_events(limit, session_id=session_id)
    ]


@app.post("/guardrails/test-output-tone", response_model=ToneTestResponse)
def test_output_tone(req: ToneTestRequest):
    """Exercises the Guardrails AI professional-tone validator directly,
    in isolation from a full agent run — this is what the Security
    Red-Team Console's dedicated output-guard test calls, since
    provoking an LLM into producing genuinely unprofessional text on
    its own isn't a reliable way to test this specific layer."""
    from app.guardrails.output_guard import check_tone
    fixed_text, flagged = check_tone(req.text, session_id=req.session_id)
    return ToneTestResponse(original_text=req.text, result_text=fixed_text, flagged=flagged)
