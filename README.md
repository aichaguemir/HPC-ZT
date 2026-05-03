# Secure HPC Job Portal

A Zero Trust Web Gateway for legacy HPC infrastructure, built on IBM LSF 9.1.

## Stack
- **Backend**: FastAPI + PostgreSQL + Keycloak
- **Security**: CARTA risk engine, Email OTP MFA, Cryptographic audit chain
- **HPC**: IBM LSF 9.1 over SSH
- **Infrastructure**: Docker Compose + Nginx

## Run

```bash
cp backend/.env.example backend/.env
# Fill in your cluster and Keycloak credentials
docker compose up -d
```

## Access

| Service | URL |
|---|---|
| Frontend | http://localhost |
| API | https://localhost:8000/docs |
| Keycloak | https://localhost:8443 |
| Mailhog | http://localhost:8025 |
