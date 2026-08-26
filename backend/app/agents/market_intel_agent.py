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

# Episodic memory tuning: how similar a past query must be
# (lower distance = more similar) and how recent it must be
# to count as relevant prior context.
EPISODIC_DISTANCE_THRESHOLD = 0.35
EPISODIC_RECENCY_DAYS = 30
EPISODIC_COLLECTION = "market_intel_episodic_memory"

_COMPETITOR_DATA_PATH = (
    "data/sample_data/competitor_market_data.md"
)

# Generic words that show up in almost every research topic
# phrasing but do not help match useful dataset lines.
_SEARCH_STOPWORDS = {
    "the",
    "a",
    "an",
    "of",
    "for",
    "in",
    "on",
    "and",
    "or",
    "to",
    "vs",
    "versus",
    "pricing",
    "price",
    "prices",
    "trend",
    "trends",
    "comparison",
    "compare",
    "comparing",
    "across",
    "major",
    "outdoor",
    "brand",
    "brands",
    "market",
    "data",
    "this",
    "quarter",
    "update",
    "updates",
    "lately",
    "doing",
    "what",
    "how",
    "does",
    "with",
    "against",
    "recent",
    "current",
}


_episodic_collection = None


class MarketIntelState(
    TypedDict,
    total=False,
):
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
        client = chromadb.PersistentClient(
            path=settings.CHROMA_DIR
        )

        embed_fn = (
            embedding_functions
            .SentenceTransformerEmbeddingFunction(
                model_name=settings.EMBEDDING_MODEL
            )
        )

        _episodic_collection = (
            client.get_or_create_collection(
                name=EPISODIC_COLLECTION,
                embedding_function=embed_fn,
                metadata={
                    "hnsw:space": "cosine"
                },
            )
        )

    return _episodic_collection


def _load_competitor_data() -> str:
    try:
        with open(
            _COMPETITOR_DATA_PATH,
            "r",
            encoding="utf-8",
        ) as file:
            return file.read()

    except FileNotFoundError:
        return (
            "No competitor data file found."
        )


def _search_competitor_data(
    topic: str,
) -> str:
    """
    Search the synthetic competitor dataset using
    keyword matching.

    The project intentionally does not depend on live
    web search so the demo remains self-contained.
    """

    data = _load_competitor_data()
    lines = data.split("\n")

    words = re.findall(
        r"[a-z]+",
        topic.lower(),
    )

    keywords = [
        word
        for word in words
        if (
            word not in _SEARCH_STOPWORDS
            and len(word) > 2
        )
    ]

    if not keywords:
        relevant = [
            line
            for line in lines
            if (
                line.startswith("##")
                or line.startswith("**")
            )
        ]

        return (
            "\n".join(relevant)
            if relevant
            else (
                "No matching competitor data "
                "found for that topic."
            )
        )

    keyword_variants = set()

    for keyword in keywords:
        keyword_variants.add(keyword)

        if (
            keyword.endswith("s")
            and len(keyword) > 3
        ):
            keyword_variants.add(
                keyword[:-1]
            )

    relevant = []

    for line in lines:
        line_lower = line.lower()

        if (
            line.startswith("##")
            or line.startswith("**")
        ):
            relevant.append(line)

        elif any(
            keyword in line_lower
            for keyword in keyword_variants
        ):
            relevant.append(line)

    return (
        "\n".join(relevant)
        if relevant
        else (
            "No matching competitor data "
            "found for that topic."
        )
    )


def recall_episodic_memory_node(
    state: MarketIntelState,
) -> dict:
    """
    Recall a recent similar market-intelligence
    query if one exists.
    """

    collection = _get_episodic_collection()

    try:
        results = collection.query(
            query_texts=[
                state["query"]
            ],
            n_results=3,
        )

    except Exception:
        return {
            "prior_context": "",
            "episodic_recall_used": False,
        }

    ids = results.get(
        "ids",
        [[]],
    )[0]

    if not ids:
        return {
            "prior_context": "",
            "episodic_recall_used": False,
        }

    metadatas = results.get(
        "metadatas",
        [[]],
    )[0]

    distances = results.get(
        "distances",
        [[]],
    )[0]

    cutoff = (
        datetime.utcnow()
        - timedelta(
            days=EPISODIC_RECENCY_DAYS
        )
    )

    for metadata, distance in zip(
        metadatas,
        distances,
    ):
        if (
            distance
            > EPISODIC_DISTANCE_THRESHOLD
        ):
            continue

        try:
            stored_at = datetime.fromisoformat(
                metadata.get(
                    "stored_at",
                    "",
                )
            )

        except ValueError:
            continue

        if stored_at < cutoff:
            continue

        prior_context = (
            "A similar query was researched "
            f"on {stored_at.date().isoformat()} "
            f'(query: "{metadata.get("query", "")}"). '
            "Prior executive summary: "
            f'{metadata.get("executive_summary", "")}'
        )

        return {
            "prior_context":
                prior_context,
            "episodic_recall_used":
                True,
        }

    return {
        "prior_context": "",
        "episodic_recall_used": False,
    }


def plan_research_node(
    state: MarketIntelState,
) -> dict:
    llm = deep_agent_llm()

    prior_context = state.get(
        "prior_context",
        "",
    )

    planning_instruction = (
        "You plan a market intelligence research task. "
        "Given the query, propose up to 3 research steps, "
        "each as a SHORT topic string of 2-4 words that "
        "matches how a product category would be labeled, "
        "for example 'hiking boots' or 'outdoor jackets'. "
        "Prefer short category-style phrases over full "
        "natural-language questions because the search "
        "matches keywords against short dataset lines. "
        "Return ONLY a JSON array of strings, for example "
        '["hiking boots", "outdoor jackets"]. '
        "Do not include a preamble."
    )

    if prior_context:
        planning_instruction += (
            " A similar query was researched recently. "
            "Use the prior context to check what may have "
            "changed or fill gaps rather than simply "
            "repeating the same research topics."
        )

    human_content = state["query"]

    if prior_context:
        human_content += (
            "\n\nPrior research context:\n"
            f"{prior_context}"
        )

    resp = llm.invoke(
        [
            SystemMessage(
                content=planning_instruction
            ),
            HumanMessage(
                content=human_content
            ),
        ]
    )

    try:
        matched = re.search(
            r"\[.*\]",
            resp.content,
            re.DOTALL,
        )

        topics = json.loads(
            matched.group(0)
        )

        plan = [
            {
                "topic": topic
            }
            for topic in topics
        ][:3]

    except Exception:
        plan = [
            {
                "topic":
                    state["query"]
            }
        ]

    return {
        "plan": plan,
        "findings": [],
        "total_steps_executed": 0,
        "reflect_cycles": 0,
    }


def execute_step_node(
    state: MarketIntelState,
) -> dict:
    plan = list(
        state.get(
            "plan",
            [],
        )
    )

    if not plan:
        return {}

    step = plan.pop(0)

    result_text = (
        _search_competitor_data(
            step["topic"]
        )
    )

    findings = list(
        state.get(
            "findings",
            [],
        )
    )

    findings.append(
        {
            "topic":
                step["topic"],
            "result":
                result_text,
        }
    )

    return {
        "plan": plan,
        "findings": findings,
        "total_steps_executed":
            state.get(
                "total_steps_executed",
                0,
            )
            + 1,
    }


def reflect_node(
    state: MarketIntelState,
) -> dict:
    llm = deep_agent_llm()

    findings_text = json.dumps(
        state.get(
            "findings",
            [],
        )
    )

    resp = llm.invoke(
        [
            SystemMessage(
                content=(
                    "Given the research findings so far, "
                    "assess whether there is enough evidence "
                    "to answer the original query well. "
                    "Reply with ONLY JSON in this format: "
                    '{"confidence": <0-100>, '
                    '"additional_topics": ["...", ...]}. '
                    "Return an empty additional_topics list "
                    "when confidence is already high."
                )
            ),
            HumanMessage(
                content=(
                    f"Query: {state['query']}\n\n"
                    f"Findings: {findings_text}"
                )
            ),
        ]
    )

    try:
        matched = re.search(
            r"\{.*\}",
            resp.content,
            re.DOTALL,
        )

        parsed = json.loads(
            matched.group(0)
        )

        confidence = int(
            parsed.get(
                "confidence",
                50,
            )
        )

        additional = [
            {
                "topic": topic
            }
            for topic in parsed.get(
                "additional_topics",
                [],
            )
        ][:2]

    except Exception:
        confidence = 50
        additional = []

    return {
        "confidence":
            confidence,
        "reflect_cycles":
            state.get(
                "reflect_cycles",
                0,
            )
            + 1,
        "plan":
            additional,
    }


def _route_after_execute(
    state: MarketIntelState,
) -> str:
    if (
        state.get("plan")
        and state.get(
            "total_steps_executed",
            0,
        )
        < MAX_TOTAL_STEPS
    ):
        return "execute_step"

    return "reflect"


def _route_after_reflect(
    state: MarketIntelState,
) -> str:
    sufficient = (
        state.get(
            "confidence",
            0,
        )
        >= CONFIDENCE_THRESHOLD
    )

    exhausted = (
        state.get(
            "reflect_cycles",
            0,
        )
        >= MAX_REFLECT_CYCLES
        or state.get(
            "total_steps_executed",
            0,
        )
        >= MAX_TOTAL_STEPS
    )

    if (
        sufficient
        or exhausted
        or not state.get("plan")
    ):
        return "finalize_report"

    return "execute_step"


def finalize_report_node(
    state: MarketIntelState,
) -> dict:
    """
    Build the final employee-facing report.

    Internal research evidence is retained for reasoning,
    but implementation details are not exposed in the UI.
    """

    llm = deep_agent_llm()

    findings_text = json.dumps(
        state.get(
            "findings",
            [],
        )
    )

    resp = llm.invoke(
        [
            SystemMessage(
                content=(
                    "Synthesize a concise internal market "
                    "intelligence report from the research "
                    "findings.\n\n"

                    "Return ONLY JSON in this format:\n"
                    "{"
                    '"executive_summary": "...", '
                    '"findings": ['
                    "{"
                    '"topic": "...", '
                    '"finding": "...", '
                    '"source": ""'
                    "}"
                    "]"
                    "}.\n\n"

                    "RESPONSE RULES:\n"

                    "1. Present only business-relevant market "
                    "findings and useful interpretation.\n"

                    "2. Use specific prices, ranges, competitor "
                    "observations, and trends only when they are "
                    "supported by the research evidence.\n"

                    "3. Do not mention internal filenames, file "
                    "paths, dataset names, Chroma, embeddings, "
                    "vector stores, episodic-memory implementation, "
                    "graph nodes, prompts, tools, or orchestration "
                    "details.\n"

                    "4. Do not include sections such as "
                    "'Source File', 'Research Tool', "
                    "'Audit Trail', 'Implementation Details', "
                    "or similar technical metadata.\n"

                    "5. Keep the source field as an empty string. "
                    "It exists only for schema compatibility and "
                    "must not contain internal filenames or paths.\n"

                    "6. Do not claim live-web, real-time, or "
                    "external research. Base the report only on "
                    "the provided research findings.\n"

                    "7. If the available evidence is limited, "
                    "state that confidence is limited rather than "
                    "inventing additional market information.\n"

                    "8. Keep the response professional and useful "
                    "for NorthPeak employees. Do not expose how the "
                    "research system itself works.\n"
                )
            ),
            HumanMessage(
                content=(
                    f"Original query: "
                    f"{state['query']}\n\n"
                    f"Research findings: "
                    f"{findings_text}"
                )
            ),
        ]
    )

    try:
        matched = re.search(
            r"\{.*\}",
            resp.content,
            re.DOTALL,
        )

        parsed = json.loads(
            matched.group(0)
        )

        findings = []

        for item in parsed.get(
            "findings",
            [],
        ):
            findings.append(
                MarketIntelFinding(
                    topic=item.get(
                        "topic",
                        "",
                    ),
                    finding=item.get(
                        "finding",
                        "",
                    ),
                    source="",
                )
            )

        report = MarketIntelReport(
            query=state["query"],
            plan_steps=[
                finding["topic"]
                for finding in state.get(
                    "findings",
                    [],
                )
            ],
            findings=findings,
            executive_summary=parsed.get(
                "executive_summary",
                "",
            ),
            confidence=state.get(
                "confidence",
                50,
            ),
        ).clamped()

    except Exception:
        report = MarketIntelReport(
            query=state["query"],
            plan_steps=[
                finding["topic"]
                for finding in state.get(
                    "findings",
                    [],
                )
            ],
            findings=[],
            executive_summary=(
                "The market intelligence report "
                "could not be formatted correctly. "
                "Please retry the request."
            ),
            confidence=0,
        )

    report_dict = json.loads(
        report.model_dump_json()
    )

    report_dict[
        "used_episodic_memory"
    ] = state.get(
        "episodic_recall_used",
        False,
    )

    return {
        "final_report":
            report_dict
    }


def store_episodic_memory_node(
    state: MarketIntelState,
) -> dict:
    """
    Persist the completed report so future similar
    queries can use it as prior context.

    Failure to store memory never blocks the report.
    """

    report = state.get(
        "final_report",
        {},
    )

    if not report.get(
        "executive_summary"
    ):
        return {}

    try:
        collection = (
            _get_episodic_collection()
        )

        collection.upsert(
            ids=[
                str(
                    uuid.uuid4()
                )
            ],
            documents=[
                state["query"]
            ],
            metadatas=[
                {
                    "query":
                        state["query"],
                    "executive_summary":
                        report[
                            "executive_summary"
                        ][:500],
                    "confidence":
                        report.get(
                            "confidence",
                            0,
                        ),
                    "stored_at":
                        datetime.utcnow()
                        .isoformat(),
                }
            ],
        )

    except Exception:
        # Episodic memory is best-effort.
        # Never fail the user-facing report because
        # the memory write failed.
        pass

    return {}


_compiled_graph = None


def build_market_intel_graph():
    graph = StateGraph(
        MarketIntelState
    )

    graph.add_node(
        "recall_episodic_memory",
        recall_episodic_memory_node,
    )

    graph.add_node(
        "plan_research",
        plan_research_node,
    )

    graph.add_node(
        "execute_step",
        execute_step_node,
    )

    graph.add_node(
        "reflect",
        reflect_node,
    )

    graph.add_node(
        "finalize_report",
        finalize_report_node,
    )

    graph.add_node(
        "store_episodic_memory",
        store_episodic_memory_node,
    )

    graph.add_edge(
        START,
        "recall_episodic_memory",
    )

    graph.add_edge(
        "recall_episodic_memory",
        "plan_research",
    )

    graph.add_edge(
        "plan_research",
        "execute_step",
    )

    graph.add_conditional_edges(
        "execute_step",
        _route_after_execute,
        {
            "execute_step":
                "execute_step",
            "reflect":
                "reflect",
        },
    )

    graph.add_conditional_edges(
        "reflect",
        _route_after_reflect,
        {
            "execute_step":
                "execute_step",
            "finalize_report":
                "finalize_report",
        },
    )

    graph.add_edge(
        "finalize_report",
        "store_episodic_memory",
    )

    graph.add_edge(
        "store_episodic_memory",
        END,
    )

    return graph.compile()


def run_market_intel_agent(
    query: str,
) -> dict:
    global _compiled_graph

    if _compiled_graph is None:
        _compiled_graph = (
            build_market_intel_graph()
        )

    result = _compiled_graph.invoke(
        {
            "query": query
        }
    )

    return result.get(
        "final_report",
        {},
    )