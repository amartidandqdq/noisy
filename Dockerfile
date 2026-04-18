# Multi-stage build pour noisy + dashboard
FROM python:3.12-slim AS builder
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Trim venv
RUN find /app/venv -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; \
    find /app/venv -name "*.pyc" -delete; \
    find /app/venv -type d -name "tests" -exec rm -rf {} + 2>/dev/null; \
    true

# -------------------------
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libffi8 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r noisy && useradd -r -g noisy -d /app noisy

COPY --from=builder /app/venv /app/venv
COPY noisy.py /app/
COPY noisy_lib /app/noisy_lib

RUN chown -R noisy:noisy /app
USER noisy

ENV PATH="/app/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

ENTRYPOINT ["python", "/app/noisy.py"]
CMD ["--dashboard", "--dashboard-host", "0.0.0.0"]
