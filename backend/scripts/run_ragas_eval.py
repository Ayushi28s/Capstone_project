"""
RAGAS faithfulness evaluation for the Knowledge Agent's RAG pipeline —
the CI gate that fails the build if answer quality regresses below the
0.90 faithfulness bar the capstone brief requires.

COMPATIBILITY NOTE: ragas hard-imports
langchain_community.chat_models.vertexai at module load time, even
though this project never uses VertexAI (OpenRouter-only). That import
path was removed from langchain-community in the 0.4.x line this
project needs for SQLDatabaseToolkit under langchain 1.3.x. Since the
VertexAI integration is genuinely unused here, the fix is a harmless
sys.modules stub — not a downgrade that would break the SQL agent, and
not a fork of ragas itself. This is applied once, at the top of this
script, before ragas is imported anywhere.

    python scripts/run_ragas_eval.py --fail-under 0.90
"""
import argparse
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# --- compatibility shim, must run before any ragas import ---
_stub = types.ModuleType("langchain_community.chat_models.vertexai")
_stub.ChatVertexAI = object
sys.modules["langchain_community.chat_models.vertexai"] = _stub

from openai import OpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import Faithfulness

from app.config import settings
from app.rag.retriever import format_context, retrieve

# A small golden set of policy questions with known-correct answers,
# generated fresh each run from the live retriever + LLM rather than
# hardcoded — this is evaluating the actual current pipeline, not a
# frozen snapshot.
EVAL_QUESTIONS = [
    "What's the return window for a standard item?",
    "How long is the manufacturing defect warranty?",
    "What's the refund approval threshold that requires manager sign-off?",
    "How long does a standard domestic shipment take?",
    "Can support agents see a customer's full card number?",
]


def _generate_answer(question: str) -> tuple[str, list[str]]:
    from app.llm_client import agent_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    chunks = retrieve(question, top_k=4)
    context = format_context(chunks)
    llm = agent_llm()
    resp = llm.invoke([
        SystemMessage(content="Answer the question using ONLY the provided context."),
        HumanMessage(content=f"Context:\n{context}\n\nQuestion: {question}"),
    ])
    return resp.content, [c["text"] for c in chunks]


def run_eval(fail_under: float) -> bool:
    client = OpenAI(api_key=settings.OPENROUTER_API_KEY, base_url=settings.OPENROUTER_BASE_URL)
    llm = llm_factory(settings.MODEL, client=client)
    faithfulness = Faithfulness(llm=llm)

    scores = []
    for question in EVAL_QUESTIONS:
        answer, contexts = _generate_answer(question)
        result = faithfulness.score(user_input=question, response=answer, retrieved_contexts=contexts)
        score = float(result.value)
        scores.append(score)
        print(f"  [{score:.2f}] {question}")

    avg = sum(scores) / len(scores) if scores else 0.0
    print(f"\nAverage faithfulness: {avg:.3f} (threshold: {fail_under})")
    return avg >= fail_under


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-under", type=float, default=settings.RAGAS_FAITHFULNESS_THRESHOLD)
    args = parser.parse_args()

    passed = run_eval(args.fail_under)
    if not passed:
        print("RAGAS gate FAILED — faithfulness below threshold.")
        sys.exit(1)
    print("RAGAS gate PASSED.")
