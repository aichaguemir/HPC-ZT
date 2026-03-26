FROM python:3.11-slim

WORKDIR /app

# تثبيت المكتبات الأساسية يدوياً لضمان العمل
RUN pip install --no-cache-dir uvicorn fastapi

# نسخ الملفات
COPY . .

# تشغيل السيرفر (لاحظي استخدام python -m uvicorn لتجنب مشاكل الـ PATH)
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
