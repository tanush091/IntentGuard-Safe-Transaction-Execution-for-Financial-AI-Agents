"""
Dedicated HTTP Client Adapter for communicating with external payment simulators.
Decouples network transport from business services and simplifies testing.
"""

import httpx
from backend.app.config import settings


def send_payment_request(method: str, url: str, **kwargs) -> httpx.Response:
    timeout = kwargs.pop("timeout", settings.DEFAULT_TIMEOUT_SECONDS)
    with httpx.Client(timeout=timeout) as client:
        return client.request(method, url, **kwargs)
