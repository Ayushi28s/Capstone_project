"""
Shared state schema for the CommerceOps AI supervisor graph. One
TypedDict flows through every node — each node reads only what it needs
and writes only what it owns, the discipline that keeps an 11-node
graph debuggable instead of turning into a shared mutable blob.
"""
from typing import Optional, TypedDict


class SupervisorState(TypedDict, total=False):
    # --- identity & input ---
    session_id: str
    raw_message: str
    employee_name: str
    employee_role: str
    customer_id: str
    order_id: str

    # --- input_guard node ---
    guard_allowed: bool
    guard_notes: list[str]

    # --- pii_redact node ---
    redacted_message: str
    pii_entities_found: int
    cost_data_flagged: bool

    # --- intent_router node ---
    intent: str
    intent_confidence: float
    used_llm_fallback: bool

    # --- agent nodes (exactly one of these populates per run) ---
    order_status_result: Optional[dict]
    refund_result: Optional[dict]
    billing_result: Optional[dict]
    policy_answer: Optional[dict]
    analytics_result: Optional[dict]
    market_intel_result: Optional[dict]

    # --- final response ---
    final_response_text: str

    # --- human_approval_gate node ---
    requires_human_approval: bool
    approved: Optional[bool]
    reviewer: Optional[str]
    approval_comments: Optional[str]

    # --- bookkeeping ---
    current_node: str
    progress_pct: int
    error: Optional[str]
