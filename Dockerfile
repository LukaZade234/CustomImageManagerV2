# Build frontend
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build && ls -la dist/

# Python app
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Copy built frontend
COPY --from=frontend /app/frontend/dist ./frontend/dist
RUN ls -la frontend/dist/ && test -f frontend/dist/index.html

ENV PORT=8080
EXPOSE 8080
WORKDIR /app
CMD ["sh", "-c", "cd /app && gunicorn --worker-tmp-dir /dev/shm --workers 2 --timeout 120 --bind 0.0.0.0:${PORT:-8080} app:app"]
