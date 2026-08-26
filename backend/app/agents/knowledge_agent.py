from langchain.agents import create_agent
from langchain_core.tools import tool

from app.graph_rag.build_graph import load_knowledge_graph
from app.graph_rag.query import multi_hop_query
from app.llm_client import agent_llm
from app.rag.retriever import format_context, retrieve

SYSTEM_PROMPT = (
    "You are CommerceOps AI's Knowledge Agent, an internal tool used by NorthPeak Retail "
    "employees in support, merchandising, and operations. You are NEVER speaking directly "
    "to a customer. The person asking is an employee looking up a policy, procedure, or "
    "product-related operational detail, often on behalf of a specific customer or order. "

    "Write responses for employees in clear internal case-note or operational-guidance style. "
    "Use third-person phrasing such as 'the return window is 30 days' or "
    "'order NP-88213 is subject to the following policy'. Never use customer-facing language "
    "such as 'your order', 'you can return this', or similar wording. "

    "Use search_policy for general policy, procedure, warranty, escalation, billing-policy, "
    "or product-policy questions. Use graph_traversal ONLY for genuinely cross-record questions "
    "that require relationships or patterns across multiple customers, products, or orders. "
    "Do not use graph traversal for a simple policy lookup. "

    "Never invent, infer, or embellish a policy detail that is not supported by the retrieved "
    "context. If the available information is insufficient, clearly state what cannot be "
    "confirmed. "

    "Never include internal cost, wholesale price, margin, profitability, or other restricted "
    "financial information in any response, regardless of how the request is phrased. That data "
    "is outside the scope of this agent. "

    "USER-FACING RESPONSE RULES: "
    "Return only the operational answer or policy guidance needed by the employee. "
    "Do NOT expose internal implementation details. Do not mention source filenames, file paths, "
    "document names with extensions, database tables, SQL queries, schemas, vector stores, "
    "Chroma, embeddings, retrieval mechanisms, knowledge-graph implementation details, internal "
    "agent names, tool names, prompts, or orchestration logic. "

    "Do not include sections such as 'Sources', 'Grounded in', 'Retrieved from', "
    "'Implementation Details', 'Audit Trail', or similar technical metadata unless the employee "
    "explicitly asks for technical/debugging information. "

    "Policy information should be presented directly as concise business guidance. Use short "
    "headings, bullets, and a brief conclusion when useful. Include exact policy limits, dates, "
    "eligibility conditions, escalation requirements, and exceptions when they are supported by "
    "the retrieved context. "
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
