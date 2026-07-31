# ============================================================
# OphAgent-Pro — ModelScope Studio Docker image
# Multi-stage: build Vite/React frontend, then FastAPI runtime.
# The API serves the built frontend at / (same origin, port 7860).
# ============================================================

# ---------- Stage 1: frontend build ----------
FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: runtime ----------
FROM python:3.11-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Vite-built frontend (served by FastAPI at /)
COPY --from=frontend-build /frontend/dist ./frontend/dist

# Entrypoint probes /mnt/workspace persistence and exports data paths before starting
COPY docker-entrypoint.sh ./

EXPOSE 7860
CMD ["/bin/sh", "docker-entrypoint.sh"]
