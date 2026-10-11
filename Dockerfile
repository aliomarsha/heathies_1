# One-container deployment: builds the React app, then serves it and the API from FastAPI.
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY model/ model/
COPY --from=web /web/dist frontend/dist
WORKDIR /app/backend
ENV HEALTHIES_MODEL_BACKEND=fixture
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
