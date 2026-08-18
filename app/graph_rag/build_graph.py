"""
Builds the customer <-> order <-> product <-> ticket knowledge graph
that GraphRAG traverses for cross-record questions like "which
customers have a return pattern on this SKU" or "show this customer's
full order and ticket history across products" — the kind of question a
flat vector search over policy text structurally cannot answer, because
the answer lives in the relationships between real data rows, not in
any single document.

Unlike a document-derived graph, this one is built directly from the
structured SQLite tables (orders, products, tickets, customers) via
NetworkX — no LLM extraction step needed, since the relationships are
already explicit as foreign keys. This is deliberately simpler and more
reliable than LLM-based relationship extraction would be here.

Run standalone:
    python -m app.graph_rag.build_graph
"""
import json

import networkx as nx

from app.config import settings
from app.db import get_conn


def build_knowledge_graph() -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()

    with get_conn() as conn:
        customers = conn.execute("SELECT * FROM customers").fetchall()
        products = conn.execute("SELECT * FROM products").fetchall()
        orders = conn.execute("SELECT * FROM orders").fetchall()
        tickets = conn.execute("SELECT * FROM tickets").fetchall()

    for c in customers:
        g.add_node(f"customer:{c['customer_id']}", node_type="Customer", name=c["name"])

    for p in products:
        g.add_node(f"product:{p['sku']}", node_type="Product", name=p["name"], category=p["category"])

    for o in orders:
        order_node = f"order:{o['order_id']}"
        g.add_node(order_node, node_type="Order", status=o["status"], date=o["order_date"])
        g.add_edge(f"customer:{o['customer_id']}", order_node, relation="PLACED")
        g.add_edge(order_node, f"product:{o['sku']}", relation="CONTAINS")
        if o["status"] == "returned":
            g.add_edge(order_node, f"product:{o['sku']}", relation="RETURNED")

    for t in tickets:
        ticket_node = f"ticket:{t['ticket_id']}"
        g.add_node(ticket_node, node_type="Ticket", category=t["category"], status=t["status"])
        g.add_edge(f"customer:{t['customer_id']}", ticket_node, relation="FILED")
        if t["order_id"]:
            g.add_edge(ticket_node, f"order:{t['order_id']}", relation="ABOUT")

    return g


def save_graph(g: nx.MultiDiGraph, path: str = None) -> None:
    path = path or settings.KNOWLEDGE_GRAPH_PATH
    data = nx.node_link_data(g, edges="edges")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def load_knowledge_graph(path: str = None) -> nx.MultiDiGraph:
    path = path or settings.KNOWLEDGE_GRAPH_PATH
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return nx.node_link_graph(data, edges="edges", multigraph=True, directed=True)


if __name__ == "__main__":
    graph = build_knowledge_graph()
    save_graph(graph)
    print(f"Built knowledge graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges.")
