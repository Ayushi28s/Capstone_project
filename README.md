# CommerceOps AI — NorthPeak Retail Employee Console

**Modules 19–20 Capstone · Advanced Certification in Agentic AI Engineering**

An internal tool for NorthPeak Retail's support, merchandising, and operations staff. An
employee looks up an order, processes a refund, checks a policy, or asks an internal
analytics/market-research question — one Chat Console, routed automatically by a Supervisor
Orchestrator to one of five purpose-built agents, with a three-layer guardrail stack and a
genuine human-approval gate underneath all of it. This is not a customer-facing bot; every
action is logged against the employee who performed it.

## Why this exists

During a routine security exercise, NorthPeak Retail's old FAQ bot was manipulated into
leaking internal SKU cost data through a crafted prompt. Security froze all further GenAI
rollout until a governed, auditable platform could prove it wouldn't happen again. Every
design decision in this system traces back to closing that exact gap.

## Quick start

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
cp .env.example .env   # add OPENROUTER_API_KEY
python scripts/seed_db.py
python preflight_check.py
uvicorn app.main:app --reload &
python -m app.worker &

cd ../frontend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

Or the full containerized stack:

```bash
cp backend/.env.example backend/.env      # add OPENROUTER_API_KEY
cp frontend/.env.example frontend/.env
docker compose up --build
docker compose exec backend python scripts/seed_db.py
```

Optional — populate the Approval Queue with a few realistic pending items (needs a working
API key, since it submits real requests through the live pipeline):

```bash
docker compose exec backend python scripts/seed_demo_approvals.py
```

Full step-by-step instructions, a UI walkthrough, and troubleshooting: see
**CommerceOps_AI_Solution_Guide.docx**.

## What's inside

| Component | Tech | Curriculum module |
|---|---|---|
| Backend API + async worker | FastAPI, Redis job queue | Module 2 |
| Intent Router | Trained TF-IDF/LogReg classifier + LLM fallback | Module 17 |
| Supervisor Orchestrator | LangGraph StateGraph + checkpointer | Modules 7–8 |
| Support Triage Crew | CrewAI, hierarchical process | Module 13 |
| Knowledge Agent | Vector RAG + GraphRAG (NetworkX) | Modules 4–5, 14 |
| Merchandising Analytics Agent | SQLDatabaseToolkit SQL agent | Module 6 |
| Market Intelligence Agent | Hand-built plan→execute→reflect sub-graph, with episodic memory | Module 12 |
| MCP servers | 3 custom + `mcp-server-sqlite` + `github-mcp-server` | Modules 10–11 |
| Guardrails | NeMo Guardrails, Presidio, Guardrails AI | Module 16 |
| Observability | LangSmith, OpenTelemetry, Prometheus/Grafana, Arize Phoenix, RAGAS — all terminal/backend-only | Modules 9, 14, 17 |
| Deployment | Docker, Docker Compose, GitHub Actions, GCP Cloud Run | Module 18 |

## Repository layout

```
commerceops-ai/
├── backend/            FastAPI + Supervisor graph + 5 agents + guardrails + MCP
├── frontend/            Streamlit console — 6 pages
├── monitoring/          Prometheus + Grafana provisioning
├── docker-compose.yml   Full service stack
└── .github/workflows/   CI/CD, gated on RAGAS + guardrail regression
```

## The console's pages

- **Dashboard** — session KPIs and recent activity, by employee and customer.
- **Chat Console** — the primary tool. Enter your name, pick which customer's account
  you're working on, and type the request — order status, refunds, billing, policy
  questions, analytics, or market research all route automatically.
- **Approval Queue** — refunds ≥ $250 and flagged anomaly patterns pause here, showing who
  submitted the request, for which customer, and the original message — until a manager
  approves or rejects it.
- **Merchandising Analytics** / **Market Intelligence** — direct access to those two agents
  for staff who don't need the full Chat Console flow.

There is no Observability or Policy Documents page — see the sections below for the
terminal-based equivalents of both.

## Employee identity

Every request requires an employee name, stored alongside the customer ID it's about —
`chat_jobs.employee_name` / `chat_jobs.customer_id` in `app/db.py`. This is a distinct field
from any dropdown-selected customer; the console is answering "which NorthPeak employee is
handling which customer's issue," not asking a customer to identify themselves. There's no
separate login system in this demo — the name field is the only identity check — so treat it
as an audit-trail field, not an access-control boundary.

## Observability — terminal-only, no UI

There is no Observability page in this app; all four tools are checked from a terminal.

```bash
cd backend
python scripts/observability_report.py            # one-shot report
python scripts/observability_report.py --events 50 --watch 10   # live-refreshing tail
```

This single script covers all four:
- **Guardrail events** — read directly from SQLite, printed as a table with an action
  breakdown.
- **Prometheus metrics** — fetched live from the backend's own `/metrics` endpoint over
  plain HTTP and printed to the terminal; no browser or separate `curl` needed.
- **LangSmith** — config status only (enabled/disabled, project name, dashboard URL to
  open manually). It's a hosted SaaS with its own web UI; this script doesn't replace that,
  it just tells you whether tracing is even switched on. Enable via `LANGSMITH_API_KEY` +
  `LANGCHAIN_TRACING_V2=true` in `backend/.env`.
- **Arize Phoenix** — same idea: config status and its OTLP endpoint, not a replacement for
  opening Phoenix's own UI. Enable via `PHOENIX_ENABLED=true` (needs the `phoenix` Docker
  service running: `docker compose up phoenix -d`). Traces go out via the lightweight
  `arize-phoenix-otel` package, never the full embedded `arize-phoenix` platform — that
  package has a hard, broken dependency on Windows, found and fixed during this build.

**Grafana** is the one exception that genuinely needs a browser (it's a dashboard tool by
definition) — `http://localhost:3000`, login `admin` / `commerceops`. It's visualizing the
exact same Prometheus metrics the script above already prints in plain text, so the browser
step is optional, not required to see the numbers.

## Policy documents

Thirteen Markdown documents live in `backend/data/policy_docs/` — the Knowledge Agent's RAG
corpus. There's no editing UI; add or edit a `.md` file directly, then re-run the index:

```bash
cd backend
python scripts/seed_db.py
```

