# syntax=docker/dockerfile:1

# ---- Stage 1: build the React dashboard ----
FROM node:20-slim AS web-build
WORKDIR /app/react-dashboard
COPY react-dashboard/package*.json ./
RUN npm ci
COPY react-dashboard/ ./
RUN npm run build

# ---- Stage 2: Python runtime ----
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app

# pandoc: markdown -> document conversion used by the generator
RUN apt-get update \
    && apt-get install -y --no-install-recommends pandoc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

# Chromium + its system libraries for Playwright PDF rendering.
# Installs to PLAYWRIGHT_BROWSERS_PATH; same env at runtime resolves it.
RUN playwright install --with-deps chromium

# Application code (build context minus .dockerignore entries)
COPY . .
# Overlay the compiled SPA from stage 1 (local dist is .dockerignored)
COPY --from=web-build /app/react-dashboard/dist ./react-dashboard/dist

EXPOSE 8080
# Shell form so ${PORT} (provided by Railway) expands; defaults to 8080 locally.
# --proxy-headers + --forwarded-allow-ips=* make uvicorn trust Railway's
# X-Forwarded-Proto, so request.url_for() builds https:// callback URLs (else the
# OAuth redirect_uri is http:// and Google/GitHub reject it as a mismatch).
CMD uvicorn web.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips="*"
