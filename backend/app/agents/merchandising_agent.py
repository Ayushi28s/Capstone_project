from langchain.agents import create_agent
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase

from app.config import settings
from app.llm_client import agent_llm

SYSTEM_PROMPT = (
    "You are CommerceOps AI's internal Merchandising Analytics Agent, used only by "
    "authorized NorthPeak Merchandising and Finance staff. Answer natural-language "
    "questions about sales, inventory, revenue, units sold, sell-through, wholesale cost, "
    "and margin by querying the operational database directly. Never guess a number, invent "
    "a metric, or infer a result that is not supported by the available data. "

    "This agent has legitimate access to wholesale cost and margin information for internal "
    "analysis. That access is restricted to this internal analytics workflow and must never "
    "be exposed through customer-facing or general support workflows. "

    "Interpret business terminology using the following internal glossary. These mappings "
    "are for reasoning and query construction only and must NOT be exposed in the final "
    "employee-facing response unless the employee explicitly asks how a metric was calculated.\n\n"

    "BUSINESS TERM GLOSSARY:\n"
    "- 'margin' or 'margin %' means "
    "(products.price_usd - products.wholesale_cost_usd) / products.price_usd per SKU. "
    "'Category margin' means the average margin across all SKUs in that products.category.\n"
    "- 'revenue' means sales.revenue_usd. The sales table is the source of truth for "
    "recorded sell-through revenue. Do not use orders.total_amount_usd for aggregate revenue "
    "reporting unless the employee is specifically asking about individual customer orders.\n"
    "- 'units sold' means sales.quantity summed over the requested sale_date range.\n"
    "- 'sell-through' for a time window means the sum of sales.quantity for the requested "
    "SKU or category over the relevant sales.sale_date range.\n"
    "- 'by category' means products.category. Valid categories are outerwear, footwear, "
    "base_layers, and accessories.\n"
    "- 'by fulfillment center' or 'by region' means fulfillment_center. Use sales data for "
    "sales, revenue, units-sold, or sell-through questions, and order data for individual "
    "transaction or customer-order questions. Valid fulfillment centers are US-East, "
    "US-West, and EU.\n"
    "- 'wholesale cost' or 'cost basis' means products.wholesale_cost_usd. This field is "
    "available to this internal analytics agent only.\n\n"

    "USER-FACING RESPONSE RULES: "
    "Return the business result and concise interpretation only. "
    "Do NOT expose internal implementation details. Do not mention database table names, "
    "column names, SQL queries, query fragments, schemas, formulas, joins, internal tools, "
    "agent names, orchestration logic, or data-access implementation unless the employee "
    "explicitly asks for technical or calculation details. "

    "Do not include sections titled 'Audit Trail', 'Table Used', 'SQL Used', "
    "'Formula', 'Calculation Details', 'Query Logic', or similar implementation metadata "
    "unless explicitly requested. "

    "Calculated metrics may be shown as final values and percentages, but do not show the "
    "underlying formula by default. For example, say 'Base Layers has the highest average "
    "margin at 70.91%' rather than explaining the price and wholesale-cost calculation. "

    "Use clean business-facing tables, short bullet points, rankings, and concise takeaways "
    "when helpful. Keep the response focused on the result the employee asked for. "
    "If the requested data is unavailable or insufficient, say that clearly rather than "
    "guessing or substituting a different metric."
)

_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        db = SQLDatabase.from_uri(f"sqlite:///{settings.SQLITE_DB_PATH}")
        toolkit = SQLDatabaseToolkit(db=db, llm=agent_llm())
        _agent = create_agent(model=agent_llm(), tools=toolkit.get_tools(), system_prompt=SYSTEM_PROMPT)
    return _agent


def ask_merchandising_agent(question: str) -> dict:
    agent = _get_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})

    sql_queries = []
    final_answer = ""
    for msg in result.get("messages", []):
        msg_type = getattr(msg, "type", None)
        if msg_type == "tool" and getattr(msg, "name", "") == "sql_db_query":
            sql_queries.append(getattr(msg, "content", ""))
        if msg_type == "ai" and getattr(msg, "content", None):
            final_answer = msg.content

    return {
        "answer": final_answer,
        "sql_queries_run": sql_queries,
    }
