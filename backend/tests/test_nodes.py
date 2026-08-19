"""
Unit tests for pure-logic pieces that don't require a live LLM call.

    pytest tests/test_nodes.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings


def test_refund_threshold_is_250():
    assert settings.REFUND_APPROVAL_THRESHOLD_USD == 250.0


def test_cost_data_patterns_cover_wholesale_and_margin():
    patterns_text = " ".join(settings.COST_DATA_PATTERNS)
    assert "cost" in patterns_text
    assert "margin" in patterns_text


def test_pii_entities_cover_expected_types():
    expected = {"PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD"}
    assert expected.issubset(set(settings.PII_ENTITIES_TO_REDACT))


def test_intent_router_confidence_threshold_is_reasonable():
    from app.agents.intent_router import CONFIDENCE_THRESHOLD
    # Too low and the LLM fallback (the safety net for uncertain
    # classifications) almost never fires; too high and it fires on
    # nearly everything, defeating the point of having a cheap
    # first-pass classifier at all.
    assert 0.3 <= CONFIDENCE_THRESHOLD <= 0.7


def test_market_intel_cost_ceiling_is_bounded():
    from app.agents.market_intel_agent import MAX_REFLECT_CYCLES, MAX_TOTAL_STEPS
    assert 1 <= MAX_REFLECT_CYCLES <= 5
    assert 1 <= MAX_TOTAL_STEPS <= 10
