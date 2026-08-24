FROM node:22-bookworm-slim AS frontend
WORKDIR /web
ENV NEXT_TELEMETRY_DISABLED=1
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV STATIC_EXPORT=true
RUN npm run build

FROM python:3.13-slim AS aplicacion
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FRONTEND_DIR=/app/frontend
WORKDIR /app
COPY backend/ /app/backend/
RUN pip install --no-cache-dir /app/backend
COPY --from=frontend /web/out/ /app/frontend/
WORKDIR /app/backend
CMD ["sh", "-c", "python -m alembic upgrade head && python -m app.cli inicializar-admin && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
