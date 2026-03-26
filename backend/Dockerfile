FROM python:3.11-slim
WORKDIR /app
# سنقوم بنسخ ملف المتطلبات إذا وجد، وإلا سيتجاهله
COPY requirements.txt* . 
RUN pip install --no-cache-dir -r requirements.txt || true
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
