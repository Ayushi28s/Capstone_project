"""
Merchandising Analytics Agent: self-serve natural-language questions
over the internal sales/inventory database, using LangChain's
SQLDatabaseToolkit (Module 6) wired into create_agent the same way
every other agent in this project is built.

NOTE: langchain-community (SQLDatabaseToolkit's current home) is
upstream-deprecated in favor of standalone integration packages, but
the toolkit itself is fully functional in the pinned version — this
project uses it because it's the exact tool this curriculum names, and
because there is no standalone `langchain-sql` package to replace it
with yet.

THIS AGENT IS INTERNAL-ONLY. Unlike the Knowledge Agent, it has full
database access including products.wholesale_cost_usd — legitimate here
because margin analysis is exactly what Merchandising needs this agent
for (see the stakeholder table in the Problem Statement). It is never
exposed to a customer-facing flow, and its output still passes through
the universal output guard's tone check — just not the cost-data scrub,
which is deliberately skipped for this one agent. See
app/guardrails/output_guard.py and the Solution Guide's Guardrails
phase for the full scoping rationale.
"""
from langchain.agents import create_agent
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase

from app.config import settings
from app.llm_client import agent_llm

SYSTEM_PROMPT = (
    "You are CommerceOps AI's internal Merchandising Analytics Agent, used only by "
    "Merchandising and Finance staff. Answer natural-language questions about sales, "
    "inventory, and margin by querying the database directly — never guess a number. "
    "Always show which table(s) and rough query logic you used so results are auditable. "
    "This agent has legitimate access to wholesale cost and margin data for internal "
    "analysis — that access does not extend to any customer-facing agent in this system."
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
