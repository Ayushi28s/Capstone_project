#!/bin/bash
set -e

echo "=== Starting CommerceOps All-in-One Container ==="

# 1. Start Redis Server in background
echo "-> Starting Redis Server..."
redis-server --daemonize yes

# 2. Fix database directory permissions & run database seed script
echo "-> Setting volume permissions and running seed script..."
mkdir -p /app/data
chmod -R 777 /app/data

python scripts/seed_db.py || echo "Warning: Seed script exited with non-zero status, continuing startup..."

# 3. Start Background Worker in background
echo "-> Starting Asynchronous Worker..."
python -m app.worker &

# 4. Start FastAPI Backend in background
echo "-> Starting FastAPI Backend on port 8000..."
uvicorn app.main:app --host 127.0.0.1 --port 8000 &

# 5. Start Streamlit UI in foreground (Keeps container alive & routes public traffic)
echo "-> Starting Streamlit UI on port 8501..."
exec streamlit run app/main_ui.py \
  --server.port=8501 \
  --server.address=0.0.0.0 \
  --server.headless=true