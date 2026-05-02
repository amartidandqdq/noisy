# Multi-stage build pour noisy + dashboard
# Base sur python:3.13-slim-trixie (Debian 13) — patches openssl/tar plus recents
FROM python:3.13-slim-trixie AS builder
WORKDIR /app

RUN apt-get update \
    && apt-get -y upgrade \
    && apt-get install -y --no-install-recommends gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# Pip >=25.3 corrige CVE-2025-8869 + CVE-2026-1703
RUN pip install --no-cache-dir --upgrade "pip>=25.3" setuptools wheel

COPY requirements.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Trim venv
RUN find /app/venv -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; \
    find /app/venv -name "*.pyc" -delete; \
    find /app/venv -type d -name "tests" -exec rm -rf {} + 2>/dev/null; \
    true

# -------------------------
FROM python:3.13-slim-trixie
WORKDIR /app

RUN apt-get update \
    && apt-get -y upgrade \
    && apt-get install -y --no-install-recommends ca-certificates \
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
