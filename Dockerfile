# Dockerfile
FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

# Python deps
COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir -e .

# Demo samples
COPY demo_samples/ demo_samples/

# Built frontend
COPY --from=frontend-build /app/frontend/dist frontend/dist

EXPOSE 8000

CMD ["uvicorn", "hardware_sets_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
