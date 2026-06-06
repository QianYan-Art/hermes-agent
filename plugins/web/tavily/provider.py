"""Tavily web search + content extraction — plugin form.

Subclasses :class:`agent.web_search_provider.WebSearchProvider`. Two
capabilities advertised:

- ``supports_search()``  -> True (Tavily ``/search``)
- ``supports_extract()`` -> True (Tavily ``/extract``)

Both are sync — the underlying call is ``httpx.post(...)``.

Config keys this provider responds to::

    web:
      search_backend: "tavily"     # explicit per-capability
      extract_backend: "tavily"    # explicit per-capability
      backend: "tavily"            # shared fallback for both

Env vars::

    TAVILY_API_KEY=...           # https://app.tavily.com/home (required)
    TAVILY_BASE_URL=...          # optional override of https://api.tavily.com
"""

from __future__ import annotations

import logging
import os
import re
import threading
from typing import Any, Dict, List

from agent.web_search_provider import WebSearchProvider

logger = logging.getLogger(__name__)

_TAVILY_KEY_LOCK = threading.Lock()
_TAVILY_KEY_INDEX = 0


def _split_tavily_api_keys(raw_value: str | None) -> List[str]:
    """Return configured Tavily keys from a comma/newline separated env value."""
    if not raw_value:
        return []
    return [part.strip() for part in re.split(r"[,\n]+", raw_value) if part.strip()]


def _ordered_tavily_api_keys(keys: List[str]) -> List[str]:
    """Pick a rotating first key, then append the remaining keys as failover."""
    global _TAVILY_KEY_INDEX

    if len(keys) <= 1:
        return keys

    with _TAVILY_KEY_LOCK:
        start = _TAVILY_KEY_INDEX % len(keys)
        _TAVILY_KEY_INDEX += 1
    return keys[start:] + keys[:start]


def _tavily_request(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """POST to the Tavily API and return the parsed JSON response.

    Mirrors :func:`tools.web_tools._tavily_request`. Raises ``ValueError``
    when ``TAVILY_API_KEY`` is unset; the caller catches and surfaces as
    a typed error response.
    """
    import httpx

    api_keys = _ordered_tavily_api_keys(
        _split_tavily_api_keys(os.getenv("TAVILY_API_KEY"))
    )
    if not api_keys:
        raise ValueError(
            "TAVILY_API_KEY environment variable not set. "
            "Get your API key at https://app.tavily.com/home"
        )

    base_url = os.getenv("TAVILY_BASE_URL", "https://api.tavily.com")
    url = f"{base_url}/{endpoint.lstrip('/')}"
    last_error: Exception | None = None

    for index, api_key in enumerate(api_keys):
        request_payload = dict(payload)  # don't mutate caller's dict
        request_payload["api_key"] = api_key
        logger.info(
            "Tavily %s request to %s (key %d/%d)",
            endpoint,
            url,
            index + 1,
            len(api_keys),
        )

        try:
            if endpoint.strip("/") == "crawl":
                response = httpx.post(
                    url,
                    json=request_payload,
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=60,
                )
            else:
                response = httpx.post(url, json=request_payload, timeout=60)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            last_error = exc
            status_code = exc.response.status_code if exc.response is not None else None
            should_retry = (
                status_code in (401, 403, 429)
                or (status_code is not None and status_code >= 500)
            )
            if should_retry and index + 1 < len(api_keys):
                logger.warning(
                    "Tavily %s request failed with HTTP %s on key %d/%d; trying next key",
                    endpoint,
                    status_code,
                    index + 1,
                    len(api_keys),
                )
                continue
            raise
        except httpx.HTTPError as exc:
            last_error = exc
            if index + 1 < len(api_keys):
                logger.warning(
                    "Tavily %s request failed with %s on key %d/%d; trying next key",
                    endpoint,
                    exc.__class__.__name__,
                    index + 1,
                    len(api_keys),
                )
                continue
            raise

    if last_error is not None:
        raise last_error
    raise RuntimeError("Tavily request failed without an explicit error")


def _normalize_tavily_search_results(response: Dict[str, Any]) -> Dict[str, Any]:
    """Map Tavily ``/search`` response to ``{success, data: {web: [...]}}``."""
    web_results = []
    for i, result in enumerate(response.get("results", [])):
        web_results.append(
            {
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "description": result.get("content", ""),
                "position": i + 1,
            }
        )
    return {"success": True, "data": {"web": web_results}}


def _normalize_tavily_documents(
    response: Dict[str, Any], fallback_url: str = ""
) -> List[Dict[str, Any]]:
    """Map Tavily ``/extract`` response to standard documents.

    Documents follow the legacy LLM post-processing shape::

        {"url", "title", "content", "raw_content", "metadata"}

    Failures (``failed_results``, ``failed_urls``) become result entries
    with an ``error`` field rather than raising.
    """
    documents: List[Dict[str, Any]] = []
    for result in response.get("results", []):
        url = result.get("url", fallback_url)
        raw = result.get("raw_content", "") or result.get("content", "")
        documents.append(
            {
                "url": url,
                "title": result.get("title", ""),
                "content": raw,
                "raw_content": raw,
                "metadata": {"sourceURL": url, "title": result.get("title", "")},
            }
        )
    for fail in response.get("failed_results", []):
        documents.append(
            {
                "url": fail.get("url", fallback_url),
                "title": "",
                "content": "",
                "raw_content": "",
                "error": fail.get("error", "extraction failed"),
                "metadata": {"sourceURL": fail.get("url", fallback_url)},
            }
        )
    for fail_url in response.get("failed_urls", []):
        url_str = fail_url if isinstance(fail_url, str) else str(fail_url)
        documents.append(
            {
                "url": url_str,
                "title": "",
                "content": "",
                "raw_content": "",
                "error": "extraction failed",
                "metadata": {"sourceURL": url_str},
            }
        )
    return documents


class TavilyWebSearchProvider(WebSearchProvider):
    """Tavily search + extract provider."""

    @property
    def name(self) -> str:
        return "tavily"

    @property
    def display_name(self) -> str:
        return "Tavily"

    def is_available(self) -> bool:
        """Return True when ``TAVILY_API_KEY`` is set to a non-empty value."""
        return bool(os.getenv("TAVILY_API_KEY", "").strip())

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return True

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Execute a Tavily search."""
        try:
            from tools.interrupt import is_interrupted

            if is_interrupted():
                return {"success": False, "error": "Interrupted"}

            logger.info("Tavily search: '%s' (limit=%d)", query, limit)
            raw = _tavily_request(
                "search",
                {
                    "query": query,
                    "max_results": min(limit, 20),
                    "include_raw_content": False,
                    "include_images": False,
                },
            )
            return _normalize_tavily_search_results(raw)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 — including httpx errors
            logger.warning("Tavily search error: %s", exc)
            return {"success": False, "error": f"Tavily search failed: {exc}"}

    def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        """Extract content from one or more URLs via Tavily.

        Sync — the underlying call is httpx.post(...). Returns the legacy
        list-of-results shape; per-URL failures become items with ``error``.
        """
        try:
            from tools.interrupt import is_interrupted

            if is_interrupted():
                return [
                    {"url": u, "error": "Interrupted", "title": ""} for u in urls
                ]

            logger.info("Tavily extract: %d URL(s)", len(urls))
            raw = _tavily_request(
                "extract",
                {
                    "urls": urls,
                    "include_images": False,
                },
            )
            return _normalize_tavily_documents(
                raw, fallback_url=urls[0] if urls else ""
            )
        except ValueError as exc:
            return [{"url": u, "title": "", "content": "", "error": str(exc)} for u in urls]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tavily extract error: %s", exc)
            return [
                {"url": u, "title": "", "content": "", "error": f"Tavily extract failed: {exc}"}
                for u in urls
            ]

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Tavily",
            "badge": "paid",
            "tag": "Search + extract in one provider.",
            "env_vars": [
                {
                    "key": "TAVILY_API_KEY",
                    "prompt": "Tavily API key",
                    "url": "https://app.tavily.com/home",
                },
            ],
        }
