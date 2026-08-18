"""
One-time setup: seeds synthetic customers, products, orders, sales, and
tickets into SQLite, then trains the intent classifier, builds the
ChromaDB policy index, and builds the knowledge graph — everything the
system needs before it can handle its first real request.

    python scripts/seed_db.py
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_conn, init_db

CUSTOMERS = [
    ("CUST-001", "Jamie Rivera", "jamie.rivera@example.com", "2024-02-10"),
    ("CUST-002", "Alex Chen", "alex.chen@example.com", "2023-11-05"),
    ("CUST-003", "Morgan Ellis", "morgan.ellis@example.com", "2025-01-20"),
    ("CUST-004", "Sam Patel", "sam.patel@example.com", "2024-06-15"),
    ("CUST-005", "Taylor Brooks", "taylor.brooks@example.com", "2024-09-01"),
    ("CUST-006", "Casey Kim", "casey.kim@example.com", "2025-03-12"),
]

PRODUCTS = [
    ("SKU-88213", "Denali Trail Jacket", "outerwear", 189.00, 62.00, "Waterproof shell jacket for trail use"),
    ("SKU-77410", "Ridgeline Parka", "outerwear", 310.00, 118.00, "Insulated winter parka"),
    ("SKU-55210", "Alpine Hiking Boot", "footwear", 140.00, 48.00, "Mid-height waterproof hiking boot"),
    ("SKU-90210", "Summit Base Layer", "base_layers", 55.00, 16.00, "Merino wool base layer top"),
    ("SKU-33100", "Trailhead Daypack 22L", "accessories", 79.00, 24.00, "22-liter daypack with hydration sleeve"),
    ("SKU-44201", "Cascade Rain Shell", "outerwear", 129.00, 41.00, "Lightweight packable rain shell"),
]

# Orders deliberately include a return pattern on SKU-88213 (two
# different customers returning it) so the GraphRAG cross-order
# return-pattern demo has real data to traverse.
ORDERS = [
    ("NP-88213", "CUST-001", "SKU-88213", 1, "2026-06-01", "returned", "UPS", "2026-06-05", 189.00, "US-East"),
    ("NP-77410", "CUST-002", "SKU-77410", 1, "2026-06-10", "delivered", "FedEx", "2026-06-14", 310.00, "US-West"),
    ("NP-55210", "CUST-003", "SKU-55210", 1, "2026-06-12", "shipped", "UPS", "2026-06-17", 140.00, "US-East"),
    ("NP-90210", "CUST-001", "SKU-88213", 1, "2026-05-20", "returned", "UPS", "2026-05-24", 189.00, "US-East"),
    ("NP-11220", "CUST-004", "SKU-90210", 2, "2026-06-15", "delivered", "DPD", "2026-06-19", 110.00, "EU"),
    ("NP-22330", "CUST-005", "SKU-33100", 1, "2026-06-18", "placed", "FedEx", "2026-06-23", 79.00, "US-West"),
    ("NP-33440", "CUST-002", "SKU-88213", 1, "2026-06-20", "returned", "FedEx", "2026-06-24", 189.00, "US-West"),
    ("NP-44550", "CUST-006", "SKU-44201", 1, "2026-06-21", "delivered", "DPD", "2026-06-25", 129.00, "EU"),
    ("NP-55660", "CUST-003", "SKU-55210", 2, "2026-06-22", "delivered", "UPS", "2026-06-27", 280.00, "US-East"),
]

# Sales rows are separate from orders — they represent broader
# aggregate sell-through the Merchandising Analytics Agent queries,
# not tied 1:1 to the individual order records above.
SALES = [
    ("SKU-88213", "2026-06-01", 12, 2268.00, "US-East"),
    ("SKU-88213", "2026-06-08", 15, 2835.00, "US-East"),
    ("SKU-88213", "2026-06-15", 9, 1701.00, "US-West"),
    ("SKU-77410", "2026-06-01", 6, 1860.00, "US-West"),
    ("SKU-77410", "2026-06-08", 8, 2480.00, "US-West"),
    ("SKU-55210", "2026-06-01", 20, 2800.00, "US-East"),
    ("SKU-55210", "2026-06-08", 18, 2520.00, "US-East"),
    ("SKU-90210", "2026-06-01", 30, 1650.00, "EU"),
    ("SKU-33100", "2026-06-01", 14, 1106.00, "US-West"),
    ("SKU-44201", "2026-06-01", 10, 1290.00, "EU"),
]

TICKETS = [
    ("TCK-A1B2C3D4", "CUST-001", "NP-88213", "refund_request", "Jacket arrived with broken zipper", "resolved", "2026-06-06"),
    ("TCK-B2C3D4E5", "CUST-002", "NP-77410", "order_status", "Where is my parka?", "resolved", "2026-06-12"),
    ("TCK-C3D4E5F6", "CUST-003", None, "policy_question", "Return policy for worn boots", "resolved", "2026-06-13"),
    ("TCK-D4E5F6G7", "CUST-002", "NP-33440", "refund_request", "Second jacket also defective", "open", "2026-06-25"),
]


def seed_data() -> None:
    with get_conn() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO customers (customer_id, name, email, signup_date) VALUES (?, ?, ?, ?)",
            CUSTOMERS,
        )
        conn.executemany(
            "INSERT OR REPLACE INTO products (sku, name, category, price_usd, wholesale_cost_usd, description) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            PRODUCTS,
        )
        conn.executemany(
            "INSERT OR REPLACE INTO orders (order_id, customer_id, sku, quantity, order_date, status, "
            "carrier, estimated_delivery, total_amount_usd, fulfillment_center) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ORDERS,
        )
        conn.executemany(
            "INSERT INTO sales (sku, sale_date, quantity, revenue_usd, fulfillment_center) VALUES (?, ?, ?, ?, ?)",
            SALES,
        )
        conn.executemany(
            "INSERT OR REPLACE INTO tickets (ticket_id, customer_id, order_id, category, subject, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            TICKETS,
        )
    print(f"Seeded {len(CUSTOMERS)} customers, {len(PRODUCTS)} products, {len(ORDERS)} orders, "
          f"{len(SALES)} sales rows, {len(TICKETS)} tickets.")


def main() -> None:
    init_db()
    seed_data()

    from app.rag.ingest import build_policy_index
    n_chunks = build_policy_index(reset=True)
    print(f"Indexed {n_chunks} policy chunks into Chroma.")

    from app.graph_rag.build_graph import build_knowledge_graph, save_graph
    graph = build_knowledge_graph()
    save_graph(graph)
    print(f"Built knowledge graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges.")

    import subprocess
    subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "train_intent_router.py")], check=True)


if __name__ == "__main__":
    main()
