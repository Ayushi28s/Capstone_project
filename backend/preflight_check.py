"""
Run before starting the API or the worker so a bad or missing setup
surfaces as one clean error instead of failing deep inside a graph node.

    python preflight_check.py
"""
import os
import sys

from app.config import settings


def main() -> int:
    problems = []

    if not settings.OPENROUTER_API_KEY:
        problems.append("OPENROUTER_API_KEY is not set. Copy .env.example to .env and add your key.")
    else:
        try:
            from app.llm_client import get_llm
            llm = get_llm(max_tokens=16)
            llm.invoke("Reply with the single word: ready")
        except Exception as exc:
            problems.append(f"OpenRouter key present but the test call failed: {exc}")

    if not os.path.exists(settings.SQLITE_DB_PATH):
        problems.append(f"No database at {settings.SQLITE_DB_PATH}. Run `python scripts/seed_db.py` first.")

    if not os.path.exists(settings.CHROMA_DIR):
        problems.append(f"No Chroma index at {settings.CHROMA_DIR}. Run `python scripts/seed_db.py` first.")

    if not os.path.exists(settings.KNOWLEDGE_GRAPH_PATH):
        problems.append(f"No knowledge graph at {settings.KNOWLEDGE_GRAPH_PATH}. Run `python scripts/seed_db.py` first.")

    if not os.path.exists(settings.INTENT_ROUTER_MODEL_PATH):
        problems.append(f"No trained intent classifier at {settings.INTENT_ROUTER_MODEL_PATH}. Run `python scripts/seed_db.py` first.")

    if problems:
        print("Preflight check FAILED:\n")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("Preflight check passed. OpenRouter key valid, database seeded, index/graph/classifier all ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
