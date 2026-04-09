FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY chromelens /app/chromelens

RUN pip install --no-cache-dir .
RUN playwright install --with-deps chromium

RUN useradd --create-home --shell /bin/bash chromelens && \
    mkdir -p /work /reports && \
    chown -R chromelens:chromelens /app /work /reports /ms-playwright

USER chromelens
WORKDIR /work

VOLUME ["/reports"]

ENTRYPOINT ["chromelens"]
