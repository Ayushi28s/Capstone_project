"""
Thin wrapper around the CommerceOps AI FastAPI backend. Every page
imports from here instead of calling `requests` directly.
"""
import json
import os
import uuid

import requests
import sseclient
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


def new_session_id() -> str:
    return f"sess-{uuid.uuid4().hex[:10]}"


def health() -> dict:
    resp = requests.get(f"{API_BASE_URL}/health", timeout=5)
    resp.raise_for_status()
    return resp.json()


def submit_chat(
    message: str, session_id: str, employee_name: str, employee_role: str,
    customer_id: str, order_id: str = "",
) -> dict:
    resp = requests.post(
        f"{API_BASE_URL}/chat",
        json={
            "message": message, "session_id": session_id, "employee_name": employee_name,
            "employee_role": employee_role, "customer_id": customer_id, "order_id": order_id,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_status(session_id: str) -> dict:
    resp = requests.get(f"{API_BASE_URL}/chat/{session_id}/status", timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_response(session_id: str) -> dict | None:
    resp = requests.get(f"{API_BASE_URL}/chat/{session_id}/response", timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def list_sessions() -> list[dict]:
    resp = requests.get(f"{API_BASE_URL}/chat/sessions", timeout=10)
    resp.raise_for_status()
    return resp.json()


def approve_chat(session_id: str, approved: bool, reviewer: str, comments: str = "") -> dict:
    resp = requests.post(
        f"{API_BASE_URL}/chat/{session_id}/approve",
        json={"session_id": session_id, "approved": approved, "reviewer": reviewer, "comments": comments},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_guardrail_events(limit: int = 100, session_id: str | None = None) -> list[dict]:
    params = {"limit": limit}
    if session_id:
        params["session_id"] = session_id
    resp = requests.get(f"{API_BASE_URL}/guardrails/events", params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def test_output_tone(text: str, session_id: str = "redteam-tone-test") -> dict:
    resp = requests.post(
        f"{API_BASE_URL}/guardrails/test-output-tone",
        json={"text": text, "session_id": session_id},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def stream_status_events(session_id: str):
    resp = requests.get(f"{API_BASE_URL}/chat/{session_id}/stream", stream=True, timeout=None)
    client = sseclient.SSEClient(resp)
    for event in client.events():
        if event.event == "update":
            yield json.loads(event.data)
        elif event.event == "error":
            yield {"status": "failed", "error": event.data}
            return
