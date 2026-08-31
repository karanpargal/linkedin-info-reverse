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
        proxy = (settings.linkedin_proxy or "").strip() or None
        kwargs: dict[str, Any] = {"impersonate": "chrome"}
        if proxy:
            kwargs["proxy"] = proxy
        self._session = cffi_requests.Session(**kwargs)
        self._configure_cookies()
        self._warmed = False

    @property
    def configured(self) -> bool:
        return bool(self.settings.linkedin_li_at and self.settings.linkedin_jsessionid)

    def _configure_cookies(self) -> None:
        cookies: dict[str, str] = {}
        cookies.update(parse_extra_cookies(self.settings.linkedin_extra_cookies))
        if self.settings.linkedin_li_at:
            cookies["li_at"] = self.settings.linkedin_li_at.strip()
        if self.settings.linkedin_jsessionid:
            cookies["JSESSIONID"] = self.settings.linkedin_jsessionid.strip()
        for name, value in cookies.items():
            self._session.cookies.set(name, value, domain=".linkedin.com")

    def live_csrf(self) -> str:
        """CSRF must match the *current* JSESSIONID, including Set-Cookie rotations."""
        value = None
        jar = self._session.cookies
        getter = getattr(jar, "get", None)
        if callable(getter):
            value = getter("JSESSIONID")
        if not value:
            for cookie in jar:
                if getattr(cookie, "name", None) == "JSESSIONID":
                    value = cookie.value
                    break
        return normalize_jsessionid(value or self.settings.linkedin_jsessionid)

    def _headers(self, accept: str, referer: str | None) -> dict[str, str]:
        html = "text/html" in accept
        headers = {
            "accept": accept,
            "x-restli-protocol-version": "2.0.0",
            "x-li-lang": "en_US",
            "x-li-track": json.dumps(TRACK, separators=(",", ":")),
            "accept-language": "en-US,en;q=0.9",
            "referer": referer or f"{LINKEDIN_ORIGIN}/",
            "origin": LINKEDIN_ORIGIN,
            "sec-fetch-dest": "document" if html else "empty",
            "sec-fetch-mode": "navigate" if html else "cors",
            "sec-fetch-site": "same-origin",
        }
        csrf = self.live_csrf()
        if csrf:
            headers["csrf-token"] = csrf
        return headers

    def _pace(self) -> None:
        interval = max(2.0, float(self.settings.linkedin_min_interval))
        jitter = random.gauss(interval, interval * 0.25)
        wait = max(2.0, jitter)
        with self._lock:
            elapsed = time.monotonic() - self._last_call
            if elapsed < wait:
                time.sleep(wait - elapsed)
            self._last_call = time.monotonic()

    def warmup(self) -> None:
        """HTTP GET only — refreshes lidc / JSESSIONID from Set-Cookie. No browser."""
        if self._warmed or not self.configured:
            return
        self._warmed = True
        try:
            self.request(
                "GET",
                f"{LINKEDIN_ORIGIN}/",
                accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                allow_redirects=False,
            )
        except (SessionDead, LinkedInBlocked, RateLimited, VoyagerUnavailable) as exc:
            logger.info("Session warmup skipped: %s", exc)

    def request(
        self,
        method: str,
        url: str,
        *,
        accept: str = "application/vnd.linkedin.normalized+json+2.1",
        authenticated: bool = True,
        allow_redirects: bool = False,
        timeout: float = 25.0,
        referer: str | None = None,
    ) -> cffi_requests.Response:
        self._pace()
        headers = self._headers(accept, referer)
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
            if "redirect" in str(exc).lower():
                raise SessionDead("LinkedIn redirect loop (session challenged)") from exc
            raise VoyagerUnavailable(f"LinkedIn request failed: {exc}") from exc
        self._raise_for_status(response)
        return response

    def _raise_for_status(self, response: cffi_requests.Response) -> None:
        status = response.status_code
        location = response.headers.get("location") or ""
        if 300 <= status < 400:
            logger.warning("LinkedIn HTTP %s Location=%s", status, location or "(empty)")
            raise SessionDead(
                "LinkedIn redirected the API (login/checkpoint). Recopy cookies from a fresh /feed/ load.",
                status,
            )
        if status == 999:
            raise LinkedInBlocked("LinkedIn denied the request (HTTP 999)", status)
        if status == 429:
            raise RateLimited("LinkedIn rate-limited the request", status)
        if status in {401}:
            raise SessionDead("LinkedIn rejected the session cookie", status)
        if status == 403:
            raise SessionDead("LinkedIn returned 403 (CSRF or session)", status)

    def voyager_get(
        self,
        path: str,
        query: str = "",
        *,
        referer: str | None = None,
        retries: int = 2,
    ) -> dict[str, Any]:
        url = f"{VOYAGER_BASE}{path}"
        if query:
            url = f"{url}?{query}"
        last_error: Exception | None = None
        for attempt in range(max(1, retries)):
            try:
                response = self.request("GET", url, referer=referer)
                return self._json(response)
            except SessionDead as exc:
                last_error = exc
                if exc.status_code and 300 <= exc.status_code < 400:
                    raise
                if attempt + 1 >= retries:
                    break
                delay = 5.0 * (attempt + 1)
                logger.info("Voyager interstitial/session glitch, retrying in %.0fs: %s", delay, exc)
                time.sleep(delay)
        assert last_error is not None
        raise last_error

    def graphql(self, variables: str, query_name: str, *, referer: str | None = None) -> dict[str, Any]:
        url = (
            f"{VOYAGER_BASE}/graphql?includeWebMetadata=true"
            f"&variables={variables}&queryName={query_name}"
        )
        response = self.request("GET", url, referer=referer)
        return self._json(response)

    def probe_session(self) -> bool:
        if not self.configured:
            return False
        try:
            body = self.voyager_get("/me", retries=1)
        except (SessionDead, LinkedInBlocked, RateLimited, VoyagerUnavailable):
            return False
        return isinstance(body, dict) and bool(body)

    def fetch_html(
        self,
        url: str,
        *,
        authenticated: bool = False,
        referer: str | None = None,
    ) -> tuple[int, str]:
        response = self.request(
            "GET",
            url,
            accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            authenticated=authenticated,
            allow_redirects=False,
            referer=referer or f"{LINKEDIN_ORIGIN}/",
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
            preview = text[:180].replace("\n", " ")
            logger.warning(
                "Non-JSON Voyager body status=%s content-type=%s preview=%s",
                response.status_code,
                content_type,
                preview,
            )
            raise SessionDead("LinkedIn response was not JSON") from exc
        if not isinstance(data, dict):
            raise VoyagerUnavailable("LinkedIn response was not an object")
        if data.get("status") == 410:
            raise VoyagerUnavailable("LinkedIn endpoint is gone (HTTP 410)", 410)
        return data


def encode_member_identity(public_id: str) -> str:
    return quote(public_id, safe="")
