import argparse
import asyncio
import sys
import types
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent),
)

# Compatibility stub required by the installed RAGAS/LangChain stack.
_stub = types.ModuleType(
    "langchain_community.chat_models.vertexai"
)
_stub.ChatVertexAI = object

sys.modules[
    "langchain_community.chat_models.vertexai"
] = _stub


from openai import AsyncOpenAI

from ragas.llms import llm_factory
from ragas.metrics.collections import Faithfulness

from app.config import settings
from app.rag.retriever import (
    format_context,
    retrieve,
)


EVAL_QUESTIONS = [
    "What's the return window for a standard item?",
    "How long is the manufacturing defect warranty?",
    "What's the refund approval threshold that requires manager sign-off?",
    "How long does a standard domestic shipment take?",
    "Can support agents see a customer's full card number?",
]


def _generate_answer(
    question: str,
) -> tuple[str, list[str]]:
    from app.llm_client import agent_llm

    from langchain_core.messages import (
        HumanMessage,
        SystemMessage,
    )

    chunks = retrieve(
        question,
        top_k=4,
    )

    context = format_context(
        chunks
    )

    llm = agent_llm()

    response = llm.invoke(
        [
            SystemMessage(
                content=(
                    "Answer the question using ONLY "
                    "the provided context."
                )
            ),
            HumanMessage(
                content=(
                    f"Context:\n{context}\n\n"
                    f"Question: {question}"
                )
            ),
        ]
    )

    return (
        response.content,
        [
            chunk["text"]
            for chunk in chunks
        ],
    )


async def run_eval(
    fail_under: float,
) -> bool:
    client = AsyncOpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
    )

    llm = llm_factory(
        settings.MODEL,
        client=client,
    )

    faithfulness = Faithfulness(
        llm=llm
    )

    scores = []

    for question in EVAL_QUESTIONS:
        answer, contexts = _generate_answer(
            question
        )

        result = await faithfulness.ascore(
            user_input=question,
            response=answer,
            retrieved_contexts=contexts,
        )

        score = float(
            result.value
        )

        scores.append(
            score
        )

        print(
            f"  [{score:.2f}] "
            f"{question}"
        )

    avg = (
        sum(scores) / len(scores)
        if scores
        else 0.0
    )

    print(
        f"\nAverage faithfulness: "
        f"{avg:.3f} "
        f"(threshold: {fail_under})"
    )

    return avg >= fail_under


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--fail-under",
        type=float,
        default=(
            settings
            .RAGAS_FAITHFULNESS_THRESHOLD
        ),
    )

    args = parser.parse_args()

    passed = asyncio.run(
        run_eval(
            args.fail_under
        )
    )

    if not passed:
        print(
            "RAGAS gate FAILED — "
            "faithfulness below threshold."
        )

        sys.exit(1)

    print(
        "RAGAS gate PASSED."
    )