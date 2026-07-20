FROM python:3.13-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY samples/ ./samples/

WORKDIR /app/backend

CMD ["python", "-m", "app.main"]
