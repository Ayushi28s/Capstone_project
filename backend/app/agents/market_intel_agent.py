"""
Market Intelligence Agent: a SEPARATE compiled LangGraph sub-graph
implementing the plan -> execute -> reflect pattern from Module 12,
producing on-demand competitive/trend reports, now with genuine
episodic memory across runs.

Why a hand-built sub-graph rather than the `deepagents` package: this
was evaluated for the equivalent module in an earlier related capstone
build and found to be built for open-ended work (a virtual filesystem,
a todo-list tool, sub-agent delegation) that this bounded, single-report
task doesn't need. A dedicated sub-graph gives full control over the
cost ceiling (MAX_REFLECT_CYCLES, MAX_TOTAL_STEPS) and integrates
directly with this project's own synthetic market-data lookup, without
adopting a general-purpose framework's conventions.

EPISODIC MEMORY: each completed report is embedded and stored in its
own ChromaDB collection (separate from the policy-document RAG
collection). Before planning, recall_episodic_memory_node checks
whether a similar query was answered recently and, if so, passes that
prior report to the planner as context — so a second "summarize
competitor pricing trends" request a week later builds on what was
already found instead of researching from a blank slate every time.
This is the piece of Module 12 (long-term memory: episodic, semantic,
cross-session retrieval) that a plan/execute/reflect loop alone doesn't
cover — reflection improves one run's confidence, episodic memory is
what carries knowledge across separate runs.

Flow: recall_episodic_memory -> plan_research
      -> execute_step (loops while steps remain) -> reflect
      -> either execute_step again or finalize_report
      -> store_episodic_memory
"""
import json
import re
import uuid
from datetime import datetime, timedelta
from typing import TypedDict

import chromadb
from chromadb.utils import embedding_functions
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.llm_client import deep_agent_llm
from app.schemas import MarketIntelFinding, MarketIntelReport

MAX_REFLECT_CYCLES = 2
MAX_TOTAL_STEPS = 6
CONFIDENCE_THRESHOLD = 70

# Episodic memory tuning: how similar a past query must be (lower
# distance = more similar) and how recent it must be to count as
# relevant prior context rather than stale, possibly-outdated research.
EPISODIC_DISTANCE_THRESHOLD = 0.35
EPISODIC_RECENCY_DAYS = 30
EPISODIC_COLLECTION = "market_intel_episodic_memory"

_COMPETITOR_DATA_PATH = "data/sample_data/competitor_market_data.md"

# Generic words that show up in almost every research topic phrasing
# but never appear verbatim in a short data-file line — filtered out so
# they don't drown out the words that actually matter (e.g. "hiking",
# "boot", "jacket") when matching a topic against the dataset.
_SEARCH_STOPWORDS = {
    "the", "a", "an", "of", "for", "in", "on", "and", "or", "to", "vs", "versus",
    "pricing", "price", "prices", "trend", "trends", "comparison", "compare",
    "comparing", "across", "major", "outdoor", "brand", "brands", "market",
    "data", "this", "quarter", "update", "updates", "lately", "doing", "what",
    "how", "does", "with", "against", "recent", "current",
}

_episodic_collection = None


class MarketIntelState(TypedDict, total=False):
    query: str
    plan: list[dict]
    findings: list[dict]
    total_steps_executed: int
    reflect_cycles: int
    confidence: int
    prior_context: str
    episodic_recall_used: bool
    final_report: dict


def _get_episodic_collection():
    global _episodic_collection
    if _episodic_collection is None:
        client = chromadb.PersistentClient(path=settings.CHROMA_DIR)
        embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=settings.EMBEDDING_MODEL
        )
        _episodic_collection = client.get_or_create_collection(
            name=EPISODIC_COLLECTION, embedding_function=embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
    return _episodic_collection


def _load_competitor_data() -> str:
    try:
        with open(_COMPETITOR_DATA_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "No competitor data file found."


def _search_competitor_data(topic: str) -> str:
    """The only 'research' tool this agent has — a plain-text search over
    the synthetic competitor dataset. No live web search dependency
    (Tavily/etc.) is wired in, keeping the demo self-contained.

    Matches on individual keywords extracted from the topic, not the
    whole topic phrase as one substring. A real run surfaced this: the
    planner proposed topics like "hiking boots pricing comparison",
    which never appears verbatim anywhere in the data file — only the
    always-included category headers (## Hiking Boots Category) and
    brand-tier lines (**TrailForge Co.** — direct competitor) matched,
    while every actual price line ("- Mid-height hiking boot: $140")
    was silently dropped, because the OLD full-phrase check required
    the entire multi-word topic to appear in a single line verbatim.
    Extracting keywords and matching any of them (with basic singular/
    plural handling) is what a topic phrased in natural language
    actually needs against short data lines."""
    data = _load_competitor_data()
    lines = data.split("\n")

    words = re.findall(r"[a-z]+", topic.lower())
    keywords = [w for w in words if w not in _SEARCH_STOPWORDS and len(w) > 2]

    if not keywords:
        relevant = [l for l in lines if l.startswith("##") or l.startswith("**")]
        return "\n".join(relevant) if relevant else "No matching competitor data found for that topic."

    keyword_variants = set()
    for kw in keywords:
        keyword_variants.add(kw)
        if kw.endswith("s") and len(kw) > 3:
            keyword_variants.add(kw[:-1])  # crude singular, e.g. "boots" -> "boot"

    relevant = []
    for line in lines:
        line_lower = line.lower()
        if line.startswith("##") or line.startswith("**"):
            relevant.append(line)
        elif any(kw in line_lower for kw in keyword_variants):
            relevant.append(line)

    return "\n".join(relevant) if relevant else "No matching competitor data found for that topic."


def recall_episodic_memory_node(state: MarketIntelState) -> dict:
    """Checks whether a similar market-intelligence query was already
    answered recently. If so, surfaces that prior report as context for
    the planner instead of starting research from a blank slate."""
    collection = _get_episodic_collection()
    try:
        results = collection.query(query_texts=[state["query"]], n_results=3)
    except Exception:
        return {"prior_context": "", "episodic_recall_used": False}

    ids = results.get("ids", [[]])[0]
    if not ids:
        return {"prior_context": "", "episodic_recall_used": False}

    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    cutoff = datetime.utcnow() - timedelta(days=EPISODIC_RECENCY_DAYS)

    for meta, distance in zip(metadatas, distances):
        if distance > EPISODIC_DISTANCE_THRESHOLD:
            continue
        try:
            stored_at = datetime.fromisoformat(meta.get("stored_at", ""))
        except ValueError:
            continue
        if stored_at < cutoff:
            continue

        prior_context = (
            f"A similar query was researched on {stored_at.date().isoformat()} "
            f"(query: \"{meta.get('query', '')}\"). Prior executive summary: "
            f"{meta.get('executive_summary', '')}"
        )
        return {"prior_context": prior_context, "episodic_recall_used": True}

    return {"prior_context": "", "episodic_recall_used": False}


def plan_research_node(state: MarketIntelState) -> dict:
    llm = deep_agent_llm()
    prior_context = state.get("prior_context", "")
    planning_instruction = (
        "You plan a market intelligence research task. Given the query, propose up to 3 "
        "research steps, each a SHORT topic string (2-4 words, matching how a product "
        "category would actually be labeled — e.g. 'hiking boots', 'outdoor jackets') to "
        "search in a competitor/market dataset. Prefer short category-style phrases over "
        "full natural-language questions, since the search matches keywords against short "
        "data lines. Return ONLY a JSON array of strings, e.g. [\"...\", \"...\"]. No preamble."
    )
    if prior_context:
        planning_instruction += (
            " A similar query was already researched recently — it's included below. Plan "
            "research that checks what may have changed or fills gaps the prior research "
            "didn't cover, rather than repeating the same topics from scratch."
        )

    human_content = state["query"]
    if prior_context:
        human_content += f"\n\nPrior research context:\n{prior_context}"

    resp = llm.invoke([
        SystemMessage(content=planning_instruction),
        HumanMessage(content=human_content),
    ])
    try:
        topics = json.loads(re.search(r"\[.*\]", resp.content, re.DOTALL).group(0))
        plan = [{"topic": t} for t in topics][:3]
    except Exception:
        plan = [{"topic": state["query"]}]

    return {"plan": plan, "findings": [], "total_steps_executed": 0, "reflect_cycles": 0}


def execute_step_node(state: MarketIntelState) -> dict:
    plan = list(state.get("plan", []))
    if not plan:
        return {}
    step = plan.pop(0)
    result_text = _search_competitor_data(step["topic"])
    findings = list(state.get("findings", []))
    findings.append({"topic": step["topic"], "result": result_text})
    return {
        "plan": plan,
        "findings": findings,
        "total_steps_executed": state.get("total_steps_executed", 0) + 1,
    }


def reflect_node(state: MarketIntelState) -> dict:
    llm = deep_agent_llm()
    findings_text = json.dumps(state.get("findings", []))
    resp = llm.invoke([
        SystemMessage(content=(
            "Given the research findings so far, assess whether there is enough evidence to "
            "answer the original query well. Reply with ONLY JSON: "
            '{"confidence": <0-100>, "additional_topics": ["...", ...]} '
            "(additional_topics empty if confidence is already high)."
        )),
        HumanMessage(content=f"Query: {state['query']}\n\nFindings: {findings_text}"),
    ])
    try:
        parsed = json.loads(re.search(r"\{.*\}", resp.content, re.DOTALL).group(0))
        confidence = int(parsed.get("confidence", 50))
        additional = [{"topic": t} for t in parsed.get("additional_topics", [])][:2]
    except Exception:
        confidence, additional = 50, []

    return {
        "confidence": confidence,
        "reflect_cycles": state.get("reflect_cycles", 0) + 1,
        "plan": additional,
    }


def _route_after_execute(state: MarketIntelState) -> str:
    if state.get("plan") and state.get("total_steps_executed", 0) < MAX_TOTAL_STEPS:
        return "execute_step"
    return "reflect"


def _route_after_reflect(state: MarketIntelState) -> str:
    sufficient = state.get("confidence", 0) >= CONFIDENCE_THRESHOLD
    exhausted = (
        state.get("reflect_cycles", 0) >= MAX_REFLECT_CYCLES
        or state.get("total_steps_executed", 0) >= MAX_TOTAL_STEPS
    )
    if sufficient or exhausted or not state.get("plan"):
        return "finalize_report"
    return "execute_step"


def finalize_report_node(state: MarketIntelState) -> dict:
    llm = deep_agent_llm()
    findings_text = json.dumps(state.get("findings", []))
    resp = llm.invoke([
        SystemMessage(content=(
            "Synthesize a market intelligence report from the research findings. Return ONLY "
            'JSON: {"executive_summary": "...", "findings": [{"topic": "...", "finding": "...", '
            '"source": "..."}]}. Be specific — cite numbers from the findings, don\'t generalize.'
        )),
        HumanMessage(content=f"Original query: {state['query']}\n\nResearch findings: {findings_text}"),
    ])
    try:
        parsed = json.loads(re.search(r"\{.*\}", resp.content, re.DOTALL).group(0))
        report = MarketIntelReport(
            query=state["query"],
            plan_steps=[f["topic"] for f in state.get("findings", [])],
            findings=[MarketIntelFinding(**f) for f in parsed.get("findings", [])],
            executive_summary=parsed.get("executive_summary", ""),
            confidence=state.get("confidence", 50),
        ).clamped()
    except Exception:
        report = MarketIntelReport(
            query=state["query"],
            plan_steps=[f["topic"] for f in state.get("findings", [])],
            findings=[],
            executive_summary="Report synthesis failed to parse; see raw findings in logs.",
            confidence=0,
        )

    report_dict = json.loads(report.model_dump_json())
    report_dict["used_episodic_memory"] = state.get("episodic_recall_used", False)
    return {"final_report": report_dict}


def store_episodic_memory_node(state: MarketIntelState) -> dict:
    """Persists the completed report so a future run on a similar topic
    can recall it. Runs last, after finalize_report — a failed write
    here never blocks the report the user actually asked for."""
    report = state.get("final_report", {})
    if not report.get("executive_summary"):
        return {}
    try:
        collection = _get_episodic_collection()
        collection.upsert(
            ids=[str(uuid.uuid4())],
            documents=[state["query"]],
            metadatas=[{
                "query": state["query"],
                "executive_summary": report["executive_summary"][:500],
                "confidence": report.get("confidence", 0),
                "stored_at": datetime.utcnow().isoformat(),
            }],
        )
    except Exception:
        pass  # storing memory is best-effort; never fail the report over it
    return {}


_compiled_graph = None


def build_market_intel_graph():
    graph = StateGraph(MarketIntelState)
    graph.add_node("recall_episodic_memory", recall_episodic_memory_node)
    graph.add_node("plan_research", plan_research_node)
    graph.add_node("execute_step", execute_step_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("finalize_report", finalize_report_node)
    graph.add_node("store_episodic_memory", store_episodic_memory_node)

    graph.add_edge(START, "recall_episodic_memory")
    graph.add_edge("recall_episodic_memory", "plan_research")
    graph.add_edge("plan_research", "execute_step")
    graph.add_conditional_edges(
        "execute_step", _route_after_execute, {"execute_step": "execute_step", "reflect": "reflect"}
    )
    graph.add_conditional_edges(
        "reflect", _route_after_reflect,
        {"execute_step": "execute_step", "finalize_report": "finalize_report"},
    )
    graph.add_edge("finalize_report", "store_episodic_memory")
    graph.add_edge("store_episodic_memory", END)

    return graph.compile()


def run_market_intel_agent(query: str) -> dict:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_market_intel_graph()
    result = _compiled_graph.invoke({"query": query})
    return result.get("final_report", {})
