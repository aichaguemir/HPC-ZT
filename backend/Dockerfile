FROM python:3.11-slim

# تثبيت مكتبات النظام اللازمة لـ psycopg2 و paramiko
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. نسخ ملف المكتبات وتثبيتها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. تثبيت المكتبات اللي ناقصين في الملف نتاعك بصح يسحقهم الكود
RUN pip install --no-cache-dir pyotp qrcode sqlalchemy python-keycloak

# 3. نسخ كل الكود (بما فيه مجلد app)
COPY . .

# 4. إعداد المسار (بزاف مهمة باش يلقى مجلد app)
ENV PYTHONPATH=/app

EXPOSE 8000

# 5. تشغيل السيرفر (تأكد أن main.py موجود مباشرة داخل backend)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
