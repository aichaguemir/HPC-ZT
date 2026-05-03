FROM python:3.11-slim


RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    python3-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app


# COPY ./keycloak.crt /usr/local/share/ca-certificates/keycloak.crt
# RUN update-ca-certificates


COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


RUN pip install --no-cache-dir pyotp qrcode sqlalchemy python-keycloak


COPY ./backend/ .

ENV PYTHONPATH=/app

EXPOSE 8000


CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
