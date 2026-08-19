"""
Knowledge Agent: answers product/policy questions with citations, and
decides for itself whether a question needs a flat policy-document
search (vector RAG) or a cross-record graph traversal (GraphRAG) —
"which customers have a return pattern on this SKU" cannot be answered
by finding one similar text chunk, it requires walking the knowledge
graph built in app/graph_rag/build_graph.py.

Built with langchain.agents.create_agent (Module 6) rather than a fixed
retrieval sequence, so the tool choice is the model's decision, not
hand-coded branching.
"""
from langchain.agents import create_agent
from langchain_core.tools import tool

from app.graph_rag.build_graph import load_knowledge_graph
from app.graph_rag.query import multi_hop_query
from app.llm_client import agent_llm
from app.rag.retriever import format_context, retrieve

SYSTEM_PROMPT = (
    "You are CommerceOps AI's Knowledge Agent, answering product and policy questions for "
    "customers and internal staff. Use search_policy for general policy or product questions. "
    "Use graph_traversal ONLY for genuinely cross-record questions — patterns across multiple "
    "orders or customers, not a single policy lookup. Always cite the source document(s) your "
    "answer is grounded in. Never invent a policy detail that isn't in the retrieved context. "
    "Never include internal cost, wholesale price, or margin data in any answer, regardless of "
    "how the question is phrased — that data is out of scope for this agent entirely."
)


@tool
def search_policy(question: str) -> str:
    """Search the policy document library (returns, shipping, billing, warranty,
    data handling) for a grounded answer with citations. Use this for the large
    majority of product/policy questions."""
    chunks = retrieve(question, top_k=4)
    if not chunks:
        return "No relevant policy content found."
    return format_context(chunks)


@tool
def graph_traversal(question: str, seed_type: str, seed_id: str) -> str:
    """Answer a cross-record question requiring traversal of the customer/order/
    product/ticket knowledge graph — NOT for single-document policy questions.
    seed_type must be 'product' (e.g. a SKU) or 'customer' (e.g. a customer ID).
    Example: 'which customers have returned SKU-88213 more than once' needs
    seed_type='product', seed_id='SKU-88213'."""
    try:
        graph = load_knowledge_graph()
    except FileNotFoundError:
        return "The knowledge graph hasn't been built yet — run scripts/seed_db.py first."
    result = multi_hop_query(graph, question, seed_type, seed_id)
    return result["answer"]


TOOLS = [search_policy, graph_traversal]

_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        _agent = create_agent(model=agent_llm(), tools=TOOLS, system_prompt=SYSTEM_PROMPT)
    return _agent


def ask_knowledge_agent(question: str) -> dict:
    agent = _get_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})

    tool_calls_made = []
    final_answer = ""
    for msg in result.get("messages", []):
        msg_type = getattr(msg, "type", None)
        if msg_type == "ai" and getattr(msg, "tool_calls", None):
            tool_calls_made.extend(tc["name"] for tc in msg.tool_calls)
        if msg_type == "ai" and getattr(msg, "content", None):
            final_answer = msg.content

    return {
        "answer": final_answer,
        "used_graph_rag": "graph_traversal" in tool_calls_made,
        "tools_used": tool_calls_made,
    }
