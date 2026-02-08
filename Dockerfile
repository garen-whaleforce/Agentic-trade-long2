# ============================================================
# Goshawk Alpha — Paper Trading Dashboard
# Multi-stage: Node build → Python+Node runtime + supervisord
# ============================================================

# Stage 1: Build Next.js frontend
FROM node:20-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ARG BACKEND_PORT=8400
ENV BACKEND_PORT=${BACKEND_PORT}
RUN npm run build && npm prune --production

# Stage 2: Runtime
FROM python:3.11-slim

# Install Node.js 20 + supervisord
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl supervisor && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Minimal Python deps (only what paper_trading_server.py needs)
RUN pip install --no-cache-dir fastapi uvicorn pyyaml

WORKDIR /app

# Copy backend server
COPY scripts/paper_trading_server.py scripts/paper_trading_server.py

# Copy frontend build + production deps
COPY --from=frontend-build /app/frontend/.next frontend/.next
COPY --from=frontend-build /app/frontend/node_modules frontend/node_modules
COPY --from=frontend-build /app/frontend/package.json frontend/package.json
COPY --from=frontend-build /app/frontend/next.config.js frontend/next.config.js

# Supervisord config
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Default ports (overridden by docker-compose environment)
ENV BACKEND_PORT=8400
ENV FRONTEND_PORT=3400

# Data directories are volume-mounted at runtime:
# signals/, configs/, logs/

CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
