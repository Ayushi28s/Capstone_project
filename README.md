# CommerceOps AI — Multi-Agent Retail Operations Platform

**Modules 19–20 Capstone · Advanced Certification in Agentic AI Engineering**

A Supervisor Orchestrator, fronted by a lightweight trained intent classifier, routes
every request to one of five purpose-built agents — a CrewAI Support Triage Crew, a
RAG+GraphRAG Knowledge Agent, a SQL-backed Merchandising Analytics Agent, and a
plan→research→reflect Market Intelligence Agent — with a three-layer guardrail stack,
a genuine human-approval gate, and full observability wrapped around all of it.

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
| Market Intelligence Agent | Hand-built plan→execute→reflect sub-graph | Module 12 |
| MCP servers | 3 custom + `mcp-server-sqlite` + `github-mcp-server` | Modules 10–11 |
| Guardrails | NeMo Guardrails, Presidio, Guardrails AI | Module 16 |
| Workflow automation | n8n (guardrail alert + scheduled report trigger) | Module 15 |
| Observability | LangSmith, OpenTelemetry, Prometheus/Grafana, Arize Phoenix (own container), RAGAS | Modules 9, 14, 17 |
| Deployment | Docker, Docker Compose, GitHub Actions, GCP Cloud Run | Module 18 |

## Repository layout

```
commerceops-ai/
├── backend/            FastAPI + Supervisor graph + 5 agents + guardrails + MCP
├── frontend/            Streamlit console — 6 pages incl. live Security Red-Team Console
├── monitoring/          Prometheus + Grafana provisioning
├── docker-compose.yml   Full 6-service stack
└── .github/workflows/   CI/CD, gated on RAGAS + guardrail regression
```

## Live security demo

Open the **Security Red-Team Console** page and run the 8-prompt adversarial suite
live against the real pipeline — including the wholesale-cost-leak prompt that is the
direct proof this project fixes the incident that started it.

## n8n workflow automation

Two workflows ship in `n8n/`, both real, importable n8n exports:

- `guardrail_alert_flow.json` — triggered by a webhook the backend calls on every
  `blocked`/`flagged` guardrail event (see `app/db.py`'s `log_guardrail_event`), posts to
  Slack via an incoming webhook.
- `scheduled_market_intel_flow.json` — fires every Monday, calls the Market Intelligence
  Agent, and posts the resulting report to Slack once it's ready.

`docker compose up` starts n8n at http://localhost:5678 automatically. To wire the flows in:

```bash
# 1. Open http://localhost:5678, import both files from n8n/ via the UI (Import from File)
# 2. Open the Guardrail Event Webhook node, copy its Production URL, then:
echo "N8N_GUARDRAIL_ALERT_WEBHOOK_URL=<paste the URL>" >> backend/.env
docker compose restart backend
# 3. (Optional) set SLACK_INCOMING_WEBHOOK_URL in the project-root .env for real Slack posts
# 4. Activate both workflows in the n8n UI
```

## Arize Phoenix (opt-in drift monitoring)

Phoenix runs as its own Docker service (`arizephoenix/phoenix`, official image), the same
pattern as Grafana — the backend only ever sends it OTLP traces via the lightweight
`arize-phoenix-otel` package, never embeds the full Phoenix platform in-process. This
matters on Windows specifically: the full `arize-phoenix` package hard-depends on
`sqlean-py`, which has no Windows wheels at all and fails to build without the MSVC C++
Build Tools installed. `docker compose up` starts Phoenix automatically at
http://localhost:6006; set `PHOENIX_ENABLED=true` in `backend/.env` to have the backend
actually send it traces.
