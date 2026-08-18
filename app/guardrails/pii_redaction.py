"""
PII and internal-cost-data redaction.

Two distinct concerns, checked separately:
1. Customer PII (names, emails, phones, cards) via Presidio — standard
   privacy protection.
2. Internal cost/wholesale-pricing data — NOT personal information, but
   leaking it is the exact failure mode that triggered this project (the
   old FAQ bot leaked SKU cost data through a crafted prompt). Checked
   with a dedicated pattern match, not folded into the PII entity list,
   because it's a different risk category with a different owner
   (Finance/Merchandising, not Security/Privacy) even though both route
   through the same redaction step.
"""
import re
from dataclasses import dataclass

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from app.config import settings
from app.db import log_guardrail_event

_analyzer: AnalyzerEngine | None = None
_anonymizer: AnonymizerEngine | None = None

# Presidio's default config expects en_core_web_lg (~560MB). The small
# spaCy model trades some named-entity recall for a Docker image that
# doesn't require a 560MB model download on every build.
_NLP_CONFIG = {
    "nlp_engine_name": "spacy",
    "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
}

_COST_DATA_REGEX = re.compile("|".join(settings.COST_DATA_PATTERNS), re.IGNORECASE)


@dataclass
class RedactionResult:
    redacted_text: str
    pii_entities_found: int
    cost_data_flagged: bool


def _get_engines():
    global _analyzer, _anonymizer
    if _analyzer is None:
        nlp_engine = NlpEngineProvider(nlp_configuration=_NLP_CONFIG).create_engine()
        _analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
        _anonymizer = AnonymizerEngine()
    return _analyzer, _anonymizer


def redact(text: str, session_id: str | None = None) -> RedactionResult:
    analyzer, anonymizer = _get_engines()

    results = analyzer.analyze(text=text, entities=settings.PII_ENTITIES_TO_REDACT, language="en")
    redacted_text = text
    pii_count = 0

    if results:
        operators = {
            entity: OperatorConfig("replace", {"new_value": f"[REDACTED_{entity}]"})
            for entity in settings.PII_ENTITIES_TO_REDACT
        }
        anonymized = anonymizer.anonymize(text=text, analyzer_results=results, operators=operators)
        redacted_text = anonymized.text
        pii_count = len(results)
        entity_types = sorted({r.entity_type for r in results})
        log_guardrail_event(session_id, "pii_redaction", "redacted", f"{pii_count} entities: {', '.join(entity_types)}")

    cost_match = _COST_DATA_REGEX.search(redacted_text)
    cost_flagged = bool(cost_match)
    if cost_flagged:
        log_guardrail_event(
            session_id, "cost_data_redaction", "flagged",
            f"Internal cost-data query pattern detected: '{cost_match.group(0)}'",
        )

    return RedactionResult(
        redacted_text=redacted_text,
        pii_entities_found=pii_count,
        cost_data_flagged=cost_flagged,
    )


def scrub_cost_data_from_output(text: str, session_id: str | None = None) -> tuple[str, bool]:
    """Applied to OUTGOING responses, not just incoming messages — this is
    what actually stops a wholesale-cost number from reaching a customer,
    even if the request that produced it didn't trip the input rail."""
    match = _COST_DATA_REGEX.search(text)
    if not match:
        return text, False
    log_guardrail_event(
        session_id, "cost_data_redaction", "blocked",
        f"Response withheld: internal cost-data pattern '{match.group(0)}' detected in output",
    )
    return (
        "I can't share internal cost or pricing data — that's outside what I'm able to provide. "
        "I can help with the customer-facing price or general product info instead."
    ), True
