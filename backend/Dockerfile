# --- Build stage ---
FROM python:3.11-slim AS builder

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download en_core_web_sm

# --- Runtime stage ---
FROM python:3.11-slim AS runtime

RUN useradd --create-home --shell /bin/bash commerceops
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY app ./app
COPY mcp_servers ./mcp_servers
COPY scripts ./scripts
COPY data ./data
COPY preflight_check.py .

RUN mkdir -p /app/data/chroma && chown -R commerceops:commerceops /app
USER commerceops

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
