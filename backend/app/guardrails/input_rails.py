import os
from dataclasses import dataclass

from nemoguardrails import LLMRails, RailsConfig

from app.config import settings
from app.db import log_guardrail_event

_rails: LLMRails | None = None

# Maps each Colang flow's fixed bot line (see rails.co) to a specific,
# named flow — one entry per `define flow block ...` / `define flow
# flag ...` in the config, kept in the same order they're defined
# there so this list is easy to audit against the .co file directly.
_FLOW_SIGNATURES: list[tuple[str, str, bool]] = [
    # (marker substring in the bot's response, flow name, allowed?)
    ("I'm scoped to order status", "off_topic", False),
    ("can't set aside my operating instructions", "jailbreak_attempt", False),
    ("Claimed authority or environment doesn't change", "authority_bypass_claim", False),
    ("looks like an attempt to override", "prompt_injection_neutralized", True),
]


@dataclass
class InputRailResult:
    allowed: bool
    message: str
    triggered_flow: str | None = None
    blocked_reason: str | None = None  # kept for backward compatibility with existing callers


def _get_rails() -> LLMRails:
    global _rails
    if _rails is None:
        os.environ["OPENAI_API_KEY"] = settings.OPENROUTER_API_KEY
        config = RailsConfig.from_path(settings.NEMO_CONFIG_DIR)
        _rails = LLMRails(config)
    return _rails


def check_input(text: str, session_id: str | None = None) -> InputRailResult:
    """Run the NeMo input rail. Returns allowed=False with a safe bot
    message and a specific triggered_flow if the input is off-topic, a
    jailbreak attempt, an authority-bypass claim, or contains an
    embedded prompt-injection instruction (that last one is allowed
    through — flagged, not blocked — since the instruction is
    neutralized rather than the whole message being unusable)."""
    rails = _get_rails()
    response = rails.generate(messages=[{"role": "user", "content": text}])
    content = response.get("content", "") if isinstance(response, dict) else str(response)

    for marker, flow_name, allowed in _FLOW_SIGNATURES:
        if marker not in content:
            continue
        action = "flagged" if allowed else "blocked"
        # rail_type carries the specific flow name, not a generic
        # "input_rail" bucket — this is what lets the guardrail_events
        # audit log and the Security Red-Team Console distinguish which
        # of the four flows actually fired for a given request.
        log_guardrail_event(session_id, f"input_rail:{flow_name}", action, content[:300])
        return InputRailResult(
            allowed=allowed, message=content, triggered_flow=flow_name,
            blocked_reason=None if allowed else flow_name,
        )

    return InputRailResult(allowed=True, message=text, triggered_flow=None)
