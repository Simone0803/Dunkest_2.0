from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

DEFAULT_HEADERS = {
    "User-Agent": "dunkest-optimizer/0.1 (+research)",
    "Accept": "application/json, text/html;q=0.9",
}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def get_json(
    url: str,
    params: dict | list[tuple[str, str]] | None = None,
    timeout: float = 30.0,
) -> list | dict:
    with httpx.Client(headers=DEFAULT_HEADERS, timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def get_text(url: str, timeout: float = 30.0) -> str:
    with httpx.Client(headers=DEFAULT_HEADERS, timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text
