"""
Guardrail tests focused on routing/decision logic that doesn't require
a live model or a downloaded spaCy model. Full behavioral tests (does
NeMo actually block a jailbreak, does Presidio actually catch an SSN)
run against a live OpenRouter key via preflight_check.py and the
Security Red-Team Console.

    pytest tests/test_guardrails.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.guardrails.input_rails import InputRailResult


def test_input_rail_result_allowed_default():
    result = InputRailResult(allowed=True, message="hello")
    assert result.allowed is True
    assert result.blocked_reason is None


def test_input_rail_result_blocked_carries_reason():
    result = InputRailResult(allowed=False, message="refused", blocked_reason="off_topic_or_jailbreak_or_bypass")
    assert result.allowed is False
    assert "bypass" in result.blocked_reason
