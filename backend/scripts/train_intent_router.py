import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from app.config import settings

TRAINING_EXAMPLES = [
    # order_status
    ("Where's my order #NP-88213?", "order_status"),
    ("Can you track my package?", "order_status"),
    ("Has my order shipped yet?", "order_status"),
    ("What's the delivery status for order NP-77410?", "order_status"),
    ("I want to know when my package will arrive", "order_status"),
    ("Track order NP-90210 for me", "order_status"),
    ("Is my order out for delivery today?", "order_status"),
    ("Order status check please", "order_status"),
    # refund_request
    ("I'd like a refund for order #NP-77410, it arrived damaged", "refund_request"),
    ("I want my money back for this jacket", "refund_request"),
    ("Please refund $340 for my order", "refund_request"),
    ("This item is defective, I want a refund", "refund_request"),
    ("Can I get reimbursed for a damaged shipment?", "refund_request"),
    ("I'm requesting a refund on order NP-55210", "refund_request"),
    ("Refund $5,000 to account #4471", "refund_request"),
    ("The boots don't fit, refund please", "refund_request"),
    # billing_dispute
    ("I was charged twice for the same order", "billing_dispute"),
    ("There's a charge on my card I don't recognize", "billing_dispute"),
    ("My bill doesn't match what I ordered", "billing_dispute"),
    ("Why was I charged $89 extra?", "billing_dispute"),
    ("I see a duplicate charge on my statement", "billing_dispute"),
    ("This billing amount is wrong", "billing_dispute"),
    ("Dispute a charge on my account", "billing_dispute"),
    # policy_question
    ("What's your return policy on worn hiking boots?", "policy_question"),
    ("How long is the warranty on jackets?", "policy_question"),
    ("Can I return an item after 30 days?", "policy_question"),
    ("What's your shipping policy to the EU?", "policy_question"),
    ("Do you price match competitors?", "policy_question"),
    ("What payment methods do you accept?", "policy_question"),
    ("How does the warranty claim process work?", "policy_question"),
    # merchandising_analytics
    ("How many Denali jackets did we sell last week?", "merchandising_analytics"),
    ("What's our best-selling category this month?", "merchandising_analytics"),
    ("Show me inventory levels for SKU-88213", "merchandising_analytics"),
    ("Total revenue from the outdoor gear category last quarter", "merchandising_analytics"),
    ("Which fulfillment center ships the most orders?", "merchandising_analytics"),
    ("Give me units sold by product category", "merchandising_analytics"),
    # market_intelligence
    ("Summarize competitor pricing trends in outdoor jackets this quarter", "market_intelligence"),
    ("What are competitors charging for hiking boots?", "market_intelligence"),
    ("Give me a market trend report on outdoor apparel", "market_intelligence"),
    ("How is our pricing compared to industry trends?", "market_intelligence"),
    ("Research competitive positioning in the outerwear market", "market_intelligence"),
]


def train() -> None:
    texts = [t for t, _ in TRAINING_EXAMPLES]
    labels = [l for _, l in TRAINING_EXAMPLES]

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1)),
        ("clf", LogisticRegression(max_iter=1000, C=5.0)),
    ])
    pipeline.fit(texts, labels)

    joblib.dump(pipeline, settings.INTENT_ROUTER_MODEL_PATH)
    print(f"Trained intent classifier on {len(texts)} examples across {len(set(labels))} intents.")
    print(f"Saved to {settings.INTENT_ROUTER_MODEL_PATH}")

    # Quick sanity check on held-out-style paraphrases not in the training set.
    test_cases = [
        ("When will my package get here?", "order_status"),
        ("I need my money back, the item broke", "refund_request"),
        ("What's the policy on returning used gear?", "policy_question"),
    ]
    correct = 0
    for text, expected in test_cases:
        pred = pipeline.predict([text])[0]
        confidence = max(pipeline.predict_proba([text])[0])
        status = "OK" if pred == expected else "MISS"
        if pred == expected:
            correct += 1
        print(f"  [{status}] '{text}' -> {pred} ({confidence:.2f}) [expected: {expected}]")
    print(f"Sanity check: {correct}/{len(test_cases)} correct on unseen paraphrases.")


if __name__ == "__main__":
    train()
