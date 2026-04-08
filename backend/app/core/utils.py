# backend/app/core/utils.py
from fastapi import Request
from typing import Optional

def get_client_ip(request: Optional[Request]) -> str:
    """
    Returns the real client IP.
    - Checks X-Forwarded-For first (proxies)
    - Falls back to request.client.host
    """
    if request is None:
        return "unknown"

    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()

    xri = request.headers.get("X-Real-IP")
    if xri:
        return xri.strip()

    if request.client:
        return request.client.host

    return "unknown"
