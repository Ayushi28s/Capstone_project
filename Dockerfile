FROM python:3.11-slim

# Install system dependencies & Redis server
RUN apt-get update && apt-get install -y --no-install-recommends \
    redis-server \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create shared data volume directory
RUN mkdir -p /app/data && chmod -R 777 /app/data

# Copy and install backend Python dependencies
COPY backend/requirements.txt ./backend_requirements.txt
RUN pip install --no-cache-dir -r backend_requirements.txt

# Copy and install frontend Python dependencies
COPY frontend/requirements.txt ./frontend_requirements.txt
RUN pip install --no-cache-dir -r frontend_requirements.txt

# Copy source code into image
COPY . .

# Copy and grant execution permissions to entrypoint script
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Environment Variables mapping from your docker-compose.yml to local single-container paths
ENV REDIS_URL="redis://127.0.0.1:6379/0"
ENV API_BASE_URL="http://127.0.0.1:8000"
ENV CHROMA_DIR="/app/data/chroma"
ENV SQLITE_DB_PATH="/app/data/commerceops.db"
ENV CHECKPOINT_DB_PATH="/app/data/checkpoints.db"
ENV KNOWLEDGE_GRAPH_PATH="/app/data/knowledge_graph.json"
ENV INTENT_ROUTER_MODEL_PATH="/app/data/intent_router.joblib"
ENV MCP_SQLITE_DB_PATH="/app/data/commerceops.db"
ENV PYTHONUNBUFFERED=1

EXPOSE 8501

CMD ["/app/entrypoint.sh"]