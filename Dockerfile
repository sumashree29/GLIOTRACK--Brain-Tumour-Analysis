FROM python:3.11-slim
WORKDIR /app

# Install dependencies first (layer cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Fix R3 — run as non-root user; reduces container escape impact
RUN useradd -m -u 1000 appuser

# Copy source code but NOT .env
COPY app/ ./app/
COPY rag/ ./rag/
COPY scripts/ ./scripts/

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
