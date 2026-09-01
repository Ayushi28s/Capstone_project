#!/bin/bash
set -e

echo "=== Starting CommerceOps Single-Container Architecture ==="

# 1. Start Redis in background
echo "-> Starting Redis..."
redis-server --daemonize yes

# 2. Ensure data directory permissions & execute DB seeding
echo "-> Checking data directory & running seed..."
mkdir -p /app/data
chmod -R 777 /app/data

# Run seed script if present in backend directory
if [ -f "./backend/scripts/seed_db.py" ]; then
    python ./backend/scripts/seed_db.py || echo "Warning: Seed script exited with non-zero status, continuing startup..."
elif [ -f "./scripts/seed_db.py" ]; then
    python ./scripts/seed_db.py || echo "Warning: Seed script exited with non-zero status, continuing startup..."
fi

# 3. Start Background Worker process
echo "-> Starting Background Worker..."
python -m backend.app.worker &

# 4. Start FastAPI Backend on port 8000
echo "-> Starting FastAPI Backend on port 8000..."
cd /app/backend && uvicorn app.main:app --host 127.0.0.1 --port 8000 &

# 5. Start Streamlit UI on port 8501 (Foreground)
echo "-> Starting Streamlit Frontend on port 8501..."
cd /app/frontend && exec streamlit run app/main_ui.py \
  --server.port=8501 \
  --server.address=0.0.0.0 \
  --server.headless=true