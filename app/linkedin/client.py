from __future__ import annotations

import json
import logging
import random
import threading
import time
from typing import Any
from urllib.parse import quote

from curl_cffi import requests as cffi_requests

from app.config import Settings
from app.linkedin.errors import (
    LinkedInBlocked,
    ProfileNotFound,
    RateLimited,
    SessionDead,
    VoyagerUnavailable,
)

logger = logging.getLogger(__name__)

VOYAGER_BASE = "https://www.linkedin.com/voyager/api"
LINKEDIN_ORIGIN = "https://www.linkedin.com"
TRACK = {
    "clientVersion": "1.13.45173",
    "mpVersion": "1.13.45173",
    "osName": "web",
    "timezoneOffset": 0,
    "timezone": "UTC",
    "deviceFormFactor": "DESKTOP",
    "mpName": "voyager-web",
    "displayDensity": 1,
    "displayWidth": 1440,
    "displayHeight": 900,
}


def normalize_jsessionid(value: str) -> str:
    return (value or "").strip().strip('"')


def parse_extra_cookies(raw: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in (raw or "").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _, value = part.partition("=")
        name, value = name.strip(), value.strip()
        if name:
            cookies[name] = value
    return cookies


class LinkedInClient:
    """Headless Voyager client. No browser. Chrome TLS via curl_cffi."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._last_call = 0.0
        self._session = cffi_requests.Session(impersonate="chrome")
        self._configure_cookies()

    @property
    def configured(self) -> bool:
        return bool(self.settings.linkedin_li_at and self.settings.linkedin_jsessionid)

    def _configure_cookies(self) -> None:
        cookies: dict[str, str] = {}
        cookies.update(parse_extra_cookies(self.settings.linkedin_extra_cookies))
        if self.settings.linkedin_li_at:
            cookies["li_at"] = self.settings.linkedin_li_at.strip()
        if self.settings.linkedin_jsessionid:
            # Keep quotes on the cookie value; LinkedIn sets JSESSIONID="ajax:…"
            jsid = self.settings.linkedin_jsessionid.strip()
            cookies["JSESSIONID"] = jsid
        for name, value in cookies.items():
            self._session.cookies.set(name, value, domain=".linkedin.com")

    def _headers(self, accept: str) -> dict[str, str]:
        csrf = normalize_jsessionid(self.settings.linkedin_jsessionid)
        headers = {
            "accept": accept,
            "x-restli-protocol-version": "2.0.0",
            "x-li-lang": "en_US",
            "x-li-track": json.dumps(TRACK, separators=(",", ":")),
            "accept-language": "en-US,en;q=0.9",
            "referer": f"{LINKEDIN_ORIGIN}/feed/",
            "origin": LINKEDIN_ORIGIN,
        }
        if csrf:
            headers["csrf-token"] = csrf
        return headers

    def _pace(self) -> None:
        interval = max(0.4, float(self.settings.linkedin_min_interval))
        jitter = random.gauss(interval, interval * 0.2)
        wait = max(0.3, jitter)
        with self._lock:
            elapsed = time.monotonic() - self._last_call
            if elapsed < wait:
                time.sleep(wait - elapsed)
            self._last_call = time.monotonic()

    def request(
        self,
        method: str,
        url: str,
        *,
        accept: str = "application/vnd.linkedin.normalized+json+2.1",
        authenticated: bool = True,
        allow_redirects: bool = False,
        timeout: float = 25.0,
    ) -> cffi_requests.Response:
        self._pace()
        headers = self._headers(accept)
        if not authenticated:
            headers.pop("csrf-token", None)
        logger.debug("%s %s", method, url)
        try:
            response = self._session.request(
                method,
                url,
                headers=headers,
                allow_redirects=allow_redirects,
                timeout=timeout,
            )
        except cffi_requests.RequestsError as exc:
            raise VoyagerUnavailable(f"LinkedIn request failed: {exc}") from exc
        self._raise_for_status(response)
        return response

    def _raise_for_status(self, response: cffi_requests.Response) -> None:
        status = response.status_code
        location = response.headers.get("location", "")
        if status in {301, 302, 303, 307, 308}:
            path = location.split("?", 1)[0]
            if "/uas/login" in path or "/checkpoint" in path or "/authwall" in path:
                raise SessionDead("LinkedIn session expired or was challenged", status)
        if status == 999:
            raise LinkedInBlocked("LinkedIn denied the request (HTTP 999)", status)
        if status == 429:
            raise RateLimited("LinkedIn rate-limited the request", status)
        if status in {401}:
            raise SessionDead("LinkedIn rejected the session cookie", status)
        if status == 403:
            # Malformed CSRF is also 403; treat as session/auth failure for the caller.
            raise SessionDead("LinkedIn returned 403 (CSRF or session)", status)

    def voyager_get(self, path: str, query: str = "") -> dict[str, Any]:
        url = f"{VOYAGER_BASE}{path}"
        if query:
            url = f"{url}?{query}"
        response = self.request("GET", url)
        return self._json(response)

    def graphql(self, variables: str, query_name: str) -> dict[str, Any]:
        # Rest.li tuples must keep parentheses literal — do not urlencode the whole query.
        url = (
            f"{VOYAGER_BASE}/graphql?includeWebMetadata=true"
            f"&variables={variables}&queryName={query_name}"
        )
        response = self.request("GET", url)
        return self._json(response)

    def probe_session(self) -> bool:
        if not self.configured:
            return False
        try:
            body = self.voyager_get("/me")
        except (SessionDead, LinkedInBlocked, RateLimited, VoyagerUnavailable):
            return False
        return isinstance(body, dict) and bool(body)

    def fetch_html(self, url: str, *, authenticated: bool = False) -> tuple[int, str]:
        response = self.request(
            "GET",
            url,
            accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            authenticated=authenticated,
            allow_redirects=True,
        )
        if response.status_code >= 400:
            raise VoyagerUnavailable(
                f"LinkedIn HTML fetch failed with HTTP {response.status_code}",
                response.status_code,
            )
        return response.status_code, response.text

    @staticmethod
    def _json(response: cffi_requests.Response) -> dict[str, Any]:
        content_type = (response.headers.get("content-type") or "").lower()
        text = response.text or ""
        if "html" in content_type or text.lstrip().startswith("<"):
            raise SessionDead("LinkedIn returned an HTML interstitial instead of JSON")
        if response.status_code == 410:
            raise VoyagerUnavailable("LinkedIn endpoint is gone (HTTP 410)", 410)
        if response.status_code == 404:
            raise ProfileNotFound("Profile not found", 404)
        if response.status_code == 400:
            raise VoyagerUnavailable("LinkedIn rejected the request (HTTP 400)", 400)
        if response.status_code >= 400:
            raise VoyagerUnavailable(
                f"LinkedIn returned HTTP {response.status_code}",
                response.status_code,
            )
        try:
            data = response.json()
        except Exception as exc:
            raise SessionDead("LinkedIn response was not JSON") from exc
        if not isinstance(data, dict):
            raise VoyagerUnavailable("LinkedIn response was not an object")
        if data.get("status") == 410:
            raise VoyagerUnavailable("LinkedIn endpoint is gone (HTTP 410)", 410)
        return data


def encode_member_identity(public_id: str) -> str:
    return quote(public_id, safe="")
