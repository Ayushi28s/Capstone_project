"""
Output guard: the last checkpoint before ANY response reaches a user.

Two layers, both applied to every response regardless of which agent
produced it:

1. Schema validation — whichever Pydantic model matches the intent
   (OrderStatusResult, RefundDecision, PolicyAnswer, ...) must actually
   validate via Guard.for_pydantic. A malformed agent output fails
   loudly here instead of shipping something broken to the console.
2. A universal text screen on the final rendered response: a custom
   professional-tone validator (no Guardrails Hub account needed — see
   below) PLUS a second pass of cost-data scrubbing, since an LLM can
   restate a wholesale cost number in its own words even after the
   input-side check already ran once.

The tone check is a CUSTOM validator, not Guardrails Hub's
ToxicLanguage. Hub validators aren't bundled with the pip package —
they're fetched via `guardrails hub install hub://...`, which needs a
separate Guardrails AI account, an API token, and a HuggingFace model
download. A custom @register_validator has none of that and routes
through the same OpenRouter connection every other call in this project
uses.
"""
import json
from typing import Type, TypeVar

from guardrails import Guard
from guardrails.validator_base import FailResult, PassResult, Validator, register_validator
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.db import log_guardrail_event
from app.guardrails.pii_redaction import scrub_cost_data_from_output
from app.llm_client import router_llm

T = TypeVar("T", bound=BaseModel)

_schema_guards: dict[type, Guard] = {}
_tone_guard: Guard | None = None


@register_validator(name="commerceops/professional-tone", data_type="string")
class ProfessionalToneCheck(Validator):
    """Screens outgoing text for toxic or unprofessional language using
    this project's own OpenRouter-routed LLM."""

    def validate(self, value, metadata):
        if not value or not value.strip():
            return PassResult()
        llm = router_llm()
        resp = llm.invoke([
            SystemMessage(content=(
                "You screen text for toxic, unprofessional, or inappropriate language in a "
                "customer-support / internal-ops context. Reply with ONLY the word PASS if "
                "professional, or FAIL: <rewritten professional version> if not. No other text."
            )),
            HumanMessage(content=value),
        ])
        content = resp.content.strip()
        if content.upper().startswith("FAIL"):
            fixed = content.split(":", 1)[1].strip() if ":" in content else value
            return FailResult(error_message="Unprofessional language detected", fix_value=fixed)
        return PassResult()


def _get_schema_guard(output_model: Type[T]) -> Guard:
    if output_model not in _schema_guards:
        _schema_guards[output_model] = Guard.for_pydantic(output_class=output_model)
    return _schema_guards[output_model]


def _get_tone_guard() -> Guard:
    global _tone_guard
    if _tone_guard is None:
        _tone_guard = Guard().use(ProfessionalToneCheck(on_fail="fix"))
    return _tone_guard


def validate_output(raw_output: dict, output_model: Type[T], session_id: str | None) -> T:
    """Schema-validate raw_output against output_model. Raises ValueError
    on schema failure — the caller should route that to a failed job
    state, not retry blindly."""
    schema_guard = _get_schema_guard(output_model)
    try:
        validated = schema_guard.parse(llm_output=json.dumps(raw_output, default=str))
        result = output_model.model_validate(validated.validated_output or raw_output)
    except Exception as exc:
        log_guardrail_event(session_id, "output_guard", "schema_fail", str(exc)[:300])
        raise ValueError(f"Output failed schema validation: {exc}") from exc

    log_guardrail_event(session_id, "output_guard", "passed", f"{output_model.__name__} schema OK")
    return result


def screen_final_text(text: str, session_id: str | None) -> str:
    """Universal pass every outgoing response text goes through,
    regardless of which agent produced it: tone check, then a second
    cost-data scrub (the LLM can restate a number in its own words even
    if the input-side pattern check already ran once on the raw text)."""
    text, _ = check_tone(text, session_id=session_id)
    text, was_blocked = scrub_cost_data_from_output(text, session_id=session_id)
    return text


def check_tone(text: str, session_id: str | None = None) -> tuple[str, bool]:
    """Runs ONLY the professional-tone validator, in isolation from the
    cost-data scrub and from any agent's response pipeline. Exposed as
    its own function specifically so this one guardrail layer can be
    exercised directly and deterministically — e.g. by the Security
    Red-Team Console — rather than only ever being tested indirectly by
    hoping a live agent happens to produce unprofessional text on its
    own. Returns (possibly-rewritten text, was_flagged).

    NOTE: with on_fail="fix", Guard.parse()'s own validation_passed
    field is True even when the validator failed and had to apply a
    fix — it reflects whether the overall parse succeeded AFTER
    fixing, not whether the original text was clean. The real signal
    for "was this flagged" is whether validation_summaries is
    non-empty (verified against a real failing and a real passing
    call before relying on this)."""
    tone_guard = _get_tone_guard()
    try:
        result = tone_guard.parse(llm_output=text)
        flagged = bool(result.validation_summaries)
        fixed_text = result.validated_output or text
        log_guardrail_event(
            session_id, "output_guard:tone",
            "flagged" if flagged else "passed",
            f"original: {text[:150]!r}" if flagged else "tone OK",
        )
        return fixed_text, flagged
    except Exception as exc:
        log_guardrail_event(session_id, "output_guard:tone", "error", str(exc)[:300])
        return text, False
