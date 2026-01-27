# syntax=docker/dockerfile:1.6

############################
# Build frontend (Svelte/Vite)
############################
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --ignore-scripts --include=dev

COPY frontend/ ./
RUN npm run build

############################
# Runtime (Flask API + static SPA)
############################
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000

WORKDIR /app

COPY server/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY server/ .
COPY --from=frontend-build /app/frontend/dist ./frontend_dist

EXPOSE 5000

CMD ["gunicorn", "-b", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "0", "--preload", "app:app"]
