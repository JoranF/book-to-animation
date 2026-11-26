# Studio: the shared review and posting dashboard. Build from the repository root:
#   docker build -f studio/Dockerfile .
FROM python:3.13-slim

WORKDIR /app
COPY studio/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY studio ./studio

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "studio.app:app", "--host", "0.0.0.0", "--port", "8000"]
