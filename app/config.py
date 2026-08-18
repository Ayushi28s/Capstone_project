"""
Central configuration for CommerceOps AI.

All tunables live here so nodes/agents/tests import one source of truth
instead of scattering os.environ.get() calls across the codebase.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # --- LLM (OpenRouter exclusively) ---
    OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")
    MODEL: str = os.environ.get("MODEL", "anthropic/claude-sonnet-4.6")
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # Per-role token ceilings — never leave max_tokens unset (OpenRouter
    # reserves the full output window against credit balance otherwise).
    MAX_TOKENS_ROUTER: int = int(os.environ.get("MAX_TOKENS_ROUTER", 200))
    MAX_TOKENS_SUPERVISOR: int = int(os.environ.get("MAX_TOKENS_SUPERVISOR", 400))
    MAX_TOKENS_AGENT: int = int(os.environ.get("MAX_TOKENS_AGENT", 1200))
    MAX_TOKENS_CREW_AGENT: int = int(os.environ.get("MAX_TOKENS_CREW_AGENT", 1200))
    MAX_TOKENS_DEEP_AGENT: int = int(os.environ.get("MAX_TOKENS_DEEP_AGENT", 1500))
    MAX_TOKENS_SUMMARY: int = int(os.environ.get("MAX_TOKENS_SUMMARY", 900))

    # --- Storage paths ---
    DATA_DIR: str = os.environ.get("DATA_DIR", "./data")
    POLICY_DOCS_DIR: str = os.path.join(DATA_DIR, "policy_docs")
    SQLITE_DB_PATH: str = os.environ.get("SQLITE_DB_PATH", "./data/commerceops.db")
    CHECKPOINT_DB_PATH: str = os.environ.get("CHECKPOINT_DB_PATH", "./data/checkpoints.db")
    CHROMA_DIR: str = os.environ.get("CHROMA_DIR", "./data/chroma")
    KNOWLEDGE_GRAPH_PATH: str = os.environ.get("KNOWLEDGE_GRAPH_PATH", "./data/knowledge_graph.json")
    INTENT_ROUTER_MODEL_PATH: str = os.environ.get("INTENT_ROUTER_MODEL_PATH", "./data/intent_router.joblib")
    MCP_SQLITE_DB_PATH: str = os.environ.get("MCP_SQLITE_DB_PATH", "./data/commerceops.db")

    # --- Redis (job queue, cache, LangGraph checkpointer in prod mode) ---
    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    JOB_QUEUE_KEY: str = "commerceops:jobs:queue"
    USE_REDIS_CHECKPOINTER: bool = os.environ.get("USE_REDIS_CHECKPOINTER", "false").lower() == "true"

    # --- RAG ---
    EMBEDDING_MODEL: str = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    POLICY_COLLECTION: str = "policy_docs"
    RETRIEVER_TOP_K: int = int(os.environ.get("RETRIEVER_TOP_K", 5))
    CHUNK_SIZE: int = int(os.environ.get("CHUNK_SIZE", 700))
    CHUNK_OVERLAP: int = int(os.environ.get("CHUNK_OVERLAP", 100))
    RAGAS_FAITHFULNESS_THRESHOLD: float = float(os.environ.get("RAGAS_FAITHFULNESS_THRESHOLD", 0.90))

    # --- Guardrails ---
    NEMO_CONFIG_DIR: str = os.environ.get("NEMO_CONFIG_DIR", "./app/guardrails/nemo_config")
    PII_ENTITIES_TO_REDACT = [
        "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "US_SSN",
        "CREDIT_CARD", "IBAN_CODE", "US_BANK_NUMBER", "LOCATION",
    ]
    # Internal cost/wholesale data isn't PII, but leaking it is exactly what
    # triggered this project — flagged and blocked separately, not lumped
    # in with the PII entity list above.
    COST_DATA_PATTERNS = [
        r"wholesale\s+cost", r"cost\s+basis", r"unit\s+cost",
        r"margin\s+percent", r"supplier\s+price",
    ]

    # --- HITL / risk thresholds ---
    REFUND_APPROVAL_THRESHOLD_USD: float = float(os.environ.get("REFUND_APPROVAL_THRESHOLD_USD", 250.0))

    # --- MCP servers (launched as local stdio subprocesses) ---
    MCP_ORDER_DB_ROOT: str = os.environ.get("MCP_ORDER_DB_ROOT", "./data")
    GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")

    # --- Observability ---
    LANGCHAIN_TRACING_V2: str = os.environ.get("LANGCHAIN_TRACING_V2", "false")
    LANGCHAIN_PROJECT: str = os.environ.get("LANGCHAIN_PROJECT", "commerceops-ai")
    PHOENIX_ENABLED: bool = os.environ.get("PHOENIX_ENABLED", "false").lower() == "true"
    PHOENIX_COLLECTOR_ENDPOINT: str = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces")
    OTEL_EXPORTER_PROMETHEUS_PORT: int = int(os.environ.get("OTEL_EXPORTER_PROMETHEUS_PORT", 9464))

    # --- n8n workflow automation (Module 15) ---
    N8N_GUARDRAIL_ALERT_WEBHOOK_URL: str = os.environ.get("N8N_GUARDRAIL_ALERT_WEBHOOK_URL", "")

    # --- App ---
    APP_ENV: str = os.environ.get("APP_ENV", "development")
    API_HOST: str = os.environ.get("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.environ.get("API_PORT", 8000))
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")


settings = Settings()

if os.environ.get("LANGSMITH_API_KEY"):
    os.environ.setdefault("LANGCHAIN_TRACING_V2", settings.LANGCHAIN_TRACING_V2)
    os.environ.setdefault("LANGCHAIN_PROJECT", settings.LANGCHAIN_PROJECT)
