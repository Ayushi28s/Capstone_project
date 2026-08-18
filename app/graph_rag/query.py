"""
Multi-hop traversal over the customer/order/product/ticket knowledge
graph. This answers the class of question flat vector RAG structurally
cannot: "which customers have a return pattern on this SKU" needs to
walk Product -> Order (RETURNED) -> Customer across every matching
order, not find one similar text chunk.

Kept intentionally simple (breadth-first neighborhood + LLM synthesis)
rather than a general-purpose graph query language — the graph is small
enough that ego-graph traversal is both sufficient and easy to audit.
"""
import networkx as nx
from langchain_core.messages import HumanMessage, SystemMessage

from app.llm_client import summary_llm


def find_return_pattern(graph: nx.MultiDiGraph, sku: str, min_returns: int = 2) -> dict:
    """Cross-order return-pattern lookup: which customers have returned
    this SKU more than once, or how many total returns has it had."""
    product_node = f"product:{sku}"
    if product_node not in graph:
        return {"sku": sku, "customers_with_returns": [], "total_returns": 0}

    total_returns = 0
    customers_seen = {}
    for u, v, data in graph.edges(data=True):
        if v == product_node and data.get("relation") == "RETURNED":
            order_node = u
            total_returns += 1
            for cust, order, edge_data in graph.in_edges(order_node, data=True):
                if edge_data.get("relation") == "PLACED":
                    customers_seen[cust] = customers_seen.get(cust, 0) + 1

    flagged = [
        {"customer": cust, "return_count": count}
        for cust, count in customers_seen.items()
        if count >= min_returns
    ]
    return {"sku": sku, "customers_with_returns": flagged, "total_returns": total_returns}


def customer_history(graph: nx.MultiDiGraph, customer_id: str, max_hops: int = 2) -> dict:
    """Full order + ticket history for a customer, traversed rather than
    queried flat — surfaces tickets connected to orders that a simple
    'select * from tickets where customer_id=?' would show, but without
    the cross-reference to which product each ticket's order contained."""
    customer_node = f"customer:{customer_id}"
    if customer_node not in graph:
        return {"customer_id": customer_id, "orders": [], "tickets": []}

    neighborhood = nx.ego_graph(graph, customer_node, radius=max_hops, undirected=True)
    orders, tickets, products = [], [], set()

    for node, data in neighborhood.nodes(data=True):
        if data.get("node_type") == "Order":
            orders.append({"order": node, "status": data.get("status")})
        elif data.get("node_type") == "Ticket":
            tickets.append({"ticket": node, "category": data.get("category"), "status": data.get("status")})
        elif data.get("node_type") == "Product":
            products.append(node)

    return {"customer_id": customer_id, "orders": orders, "tickets": tickets, "products_involved": list(products)}


def multi_hop_query(graph: nx.MultiDiGraph, question: str, seed_type: str, seed_id: str) -> dict:
    """General entry point: runs the appropriate traversal based on
    seed_type, then asks the LLM to synthesize a plain-English answer
    grounded in the traversed subgraph — not asked to reason freely."""
    if seed_type == "product":
        raw = find_return_pattern(graph, seed_id)
    elif seed_type == "customer":
        raw = customer_history(graph, seed_id)
    else:
        raw = {}

    llm = summary_llm()
    resp = llm.invoke([
        SystemMessage(content=(
            "Answer the question using ONLY the structured graph-traversal data provided. "
            "Do not speculate beyond what the data shows."
        )),
        HumanMessage(content=f"Question: {question}\n\nGraph traversal result: {raw}"),
    ])

    return {"answer": resp.content, "raw_traversal": raw}
