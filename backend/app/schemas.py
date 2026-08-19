"""
Pydantic models shared across the API layer, the LangGraph nodes, and the
CrewAI output_pydantic contracts.

IMPORTANT: fields consumed as an output_pydantic target for an
Anthropic-family model NEVER carry ge=/le= constraints — those render as
minimum/maximum in the generated JSON Schema, which Anthropic's tool-use
schema validator rejects. Numeric bounds are enforced in Python with the
_clamp() helper instead.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


def _clamp(value: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, value))


IntentLabel = Literal[
    "order_status",
    "refund_request",
    "billing_dispute",
    "policy_question",
    "merchandising_analytics",
    "market_intelligence",
    "off_topic",
]

RiskLevel = Literal["low", "medium", "high", "critical"]


class IntentClassification(BaseModel):
    intent: IntentLabel
    confidence: float = Field(description="0-1 confidence from the lightweight classifier")
    used_llm_fallback: bool = Field(
        default=False, description="True if confidence was too low and an LLM call was used instead"
    )


class OrderStatusResult(BaseModel):
    order_id: str
    status: str
    carrier: Optional[str] = None
    estimated_delivery: Optional[str] = None
    summary: str


class RefundDecision(BaseModel):
    order_id: str
    amount_usd: float
    reason: str
    requires_human_approval: bool
    auto_flagged_anomaly: bool = Field(
        default=False, description="True if this looks like a just-under-threshold pattern"
    )
    summary: str


class BillingDisputeResult(BaseModel):
    order_id: str
    dispute_summary: str
    resolution: str
    requires_human_approval: bool = False


class PolicyCitation(BaseModel):
    source_document: str
    excerpt: str


class PolicyAnswer(BaseModel):
    answer: str
    citations: list[PolicyCitation] = Field(default_factory=list)
    used_graph_rag: bool = Field(default=False, description="Module 14: multi-hop traversal was used")


class AnalyticsQueryResult(BaseModel):
    question: str
    sql_query: str
    result_summary: str
    row_count: int


class MarketIntelFinding(BaseModel):
    topic: str
    finding: str
    source: str


class MarketIntelReport(BaseModel):
    query: str
    plan_steps: list[str]
    findings: list[MarketIntelFinding]
    executive_summary: str
    confidence: float = Field(description="0-100 self-assessed confidence, clamped in Python")

    def clamped(self) -> "MarketIntelReport":
        self.confidence = _clamp(self.confidence)
        return self


# --- API request/response models ---

class ChatRequest(BaseModel):
    message: str
    session_id: str = Field(description="Groups a multi-turn conversation for checkpointing")
    customer_id: str = Field(description="Synthetic customer ID this request is on behalf of")
    order_id: str = Field(default="", description="Optional — order ID if the message already references one")


class ChatJobStatus(BaseModel):
    session_id: str
    status: Literal["queued", "running", "awaiting_approval", "completed", "failed", "rejected"]
    current_node: Optional[str] = None
    progress_pct: int = 0
    error: Optional[str] = None


class ApprovalDecision(BaseModel):
    session_id: str
    approved: bool
    reviewer: str
    comments: Optional[str] = None


class GuardrailEventOut(BaseModel):
    id: int
    session_id: Optional[str]
    rail_type: str
    action: str
    detail: str
    occurred_at: datetime


class ToneTestRequest(BaseModel):
    text: str
    session_id: str = Field(default="redteam-tone-test")


class ToneTestResponse(BaseModel):
    original_text: str
    result_text: str
    flagged: bool
