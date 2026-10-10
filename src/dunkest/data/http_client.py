from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

DEFAULT_HEADERS = {
    "User-Agent": "dunkest-optimizer/0.1 (+research)",
    "Accept": "application/json, text/html;q=0.9",
}


def _is_retryable_http_error(exc: BaseException) -> bool:
    """Retry transient transport failures and temporary HTTP responses only."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status in {408, 425, 429} or 500 <= status < 600
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


_RETRY = {
    "retry": retry_if_exception(_is_retryable_http_error),
    "stop": stop_after_attempt(3),
    "wait": wait_exponential(multiplier=1, min=1, max=8),
    "reraise": True,
}


@retry(**_RETRY)
def get_json(
    url: str,
    params: dict | list[tuple[str, str]] | None = None,
    timeout: float = 30.0,
) -> list | dict:
    with httpx.Client(headers=DEFAULT_HEADERS, timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


@retry(**_RETRY)
def get_text(url: str, timeout: float = 30.0) -> str:
    with httpx.Client(headers=DEFAULT_HEADERS, timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text
