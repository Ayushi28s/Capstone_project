"""
Runtime intent router. Loads the lightweight classifier trained by
scripts/train_intent_router.py and classifies each incoming message in
milliseconds — no LLM call, no network round-trip. If confidence is
below CONFIDENCE_THRESHOLD, falls back to a single cheap LLM call
instead of trusting a low-confidence guess, since a wrong route sends
the request to the wrong agent entirely.

See scripts/train_intent_router.py for why this is a TF-IDF + Logistic
Regression classifier rather than a true LoRA-fine-tuned model.
"""
import json
import os

import joblib
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.llm_client import router_llm
from app.schemas import IntentClassification, IntentLabel

CONFIDENCE_THRESHOLD = 0.45

INTENT_LABELS: list[IntentLabel] = [
    "order_status", "refund_request", "billing_dispute",
    "policy_question", "merchandising_analytics", "market_intelligence", "off_topic",
]

_classifier = None


def _get_classifier():
    global _classifier
    if _classifier is None:
        if not os.path.exists(settings.INTENT_ROUTER_MODEL_PATH):
            raise FileNotFoundError(
                f"No trained intent classifier at {settings.INTENT_ROUTER_MODEL_PATH}. "
                "Run `python scripts/train_intent_router.py` first."
            )
        _classifier = joblib.load(settings.INTENT_ROUTER_MODEL_PATH)
    return _classifier


def _llm_fallback_classify(message: str) -> IntentLabel:
    llm = router_llm()
    resp = llm.invoke([
        SystemMessage(content=(
            "Classify this customer/internal message into exactly one intent from: "
            f"{INTENT_LABELS}. Reply with ONLY the label string, nothing else."
        )),
        HumanMessage(content=message),
    ])
    label = resp.content.strip().strip('"').lower()
    return label if label in INTENT_LABELS else "off_topic"


def classify_intent(message: str) -> IntentClassification:
    classifier = _get_classifier()
    predicted = classifier.predict([message])[0]
    confidence = float(max(classifier.predict_proba([message])[0]))

    if confidence < CONFIDENCE_THRESHOLD:
        label = _llm_fallback_classify(message)
        return IntentClassification(intent=label, confidence=confidence, used_llm_fallback=True)

    return IntentClassification(intent=predicted, confidence=confidence, used_llm_fallback=False)
