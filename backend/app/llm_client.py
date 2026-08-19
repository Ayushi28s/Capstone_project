"""
Shared LLM client factory. Every node, tool, and CrewAI agent in
CommerceOps AI pulls its model from here. OpenRouter is the only
provider — no native OpenAI or Anthropic SDK is used anywhere in this
project (langchain-openai's ChatOpenAI pointed at OpenRouter's
OpenAI-compatible endpoint).

max_tokens is ALWAYS set explicitly and tuned per role. Leaving it unset
causes OpenRouter to reserve the model's full output window against the
account's credit balance, which surfaces as a 402 error on smaller keys.
"""
from crewai import LLM as CrewAILLM
from langchain_openai import ChatOpenAI

from app.config import settings


def get_llm(temperature: float = 0.0, max_tokens: int = 1000) -> ChatOpenAI:
    if not settings.OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Copy .env.example to .env and "
            "add your OpenRouter key before running any live-model demo."
        )
    return ChatOpenAI(
        model=settings.MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
        default_headers={
            "HTTP-Referer": "https://edureka.co/commerceops-ai-capstone",
            "X-Title": "CommerceOps AI Capstone",
        },
    )


# Role-scoped factories — each pins the max_tokens ceiling appropriate to
# that node so no call path can silently inherit a huge default.
def router_llm() -> ChatOpenAI:
    """Fallback LLM router used only when the lightweight intent
    classifier reports low confidence — see agents/intent_router.py."""
    return get_llm(temperature=0.0, max_tokens=settings.MAX_TOKENS_ROUTER)


def supervisor_llm() -> ChatOpenAI:
    return get_llm(temperature=0.0, max_tokens=settings.MAX_TOKENS_SUPERVISOR)


def agent_llm() -> ChatOpenAI:
    return get_llm(temperature=0.1, max_tokens=settings.MAX_TOKENS_AGENT)


def crew_agent_llm() -> CrewAILLM:
    """CrewAI's Agent(llm=...) does NOT accept a LangChain ChatOpenAI
    instance — it validates against str | BaseLLM and rejects anything
    else outright. CrewAI is built on litellm, which has native
    OpenRouter support via an `openrouter/<model>` prefix: litellm
    resolves that prefix to OpenRouter's endpoint internally and reads
    OPENROUTER_API_KEY the same way every other call in this project
    already does, so no separate base_url wiring is needed here."""
    if not settings.OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Copy .env.example to .env and "
            "add your OpenRouter key before running any live-model demo."
        )
    return CrewAILLM(
        model=f"openrouter/{settings.MODEL}",
        api_key=settings.OPENROUTER_API_KEY,
        max_tokens=settings.MAX_TOKENS_CREW_AGENT,
        temperature=0.2,
    )


def deep_agent_llm() -> ChatOpenAI:
    return get_llm(temperature=0.2, max_tokens=settings.MAX_TOKENS_DEEP_AGENT)


def summary_llm() -> ChatOpenAI:
    return get_llm(temperature=0.2, max_tokens=settings.MAX_TOKENS_SUMMARY)
