FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uvicorn fastapi python-dotenv

COPY . .

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
