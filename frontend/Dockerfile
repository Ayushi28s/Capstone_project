FROM python:3.11-slim

RUN useradd --create-home --shell /bin/bash commerceops
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R commerceops:commerceops /app
USER commerceops

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=3).status==200 else 1)"

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
