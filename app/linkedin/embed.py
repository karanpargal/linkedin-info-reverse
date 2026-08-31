from __future__ import annotations

import json
from typing import Any

from bs4 import BeautifulSoup

from app.linkedin.client import LinkedInClient
from app.linkedin.errors import SessionDead, VoyagerUnavailable
from app.linkedin.parsers import parse_voyager_profile
from app.linkedin.urls import canonical_profile_url
from app.models import Profile


def fetch_embedded_voyager_profile(client: LinkedInClient, public_id: str) -> Profile:
    """Logged-in profile page still embeds Voyager JSON in <code id="bpr-guid-…"> tags."""
    url = canonical_profile_url(public_id)
    _, html = client.fetch_html(url, authenticated=True, referer=url)
    if _looks_like_checkpoint(html):
        raise SessionDead("Authenticated profile page was a checkpoint/login interstitial")
    for body in extract_bpr_payloads(html):
        profile = parse_voyager_profile(body, public_id=public_id, url=url)
        if profile:
            return profile
    raise VoyagerUnavailable("Authenticated profile HTML had no embedded Voyager profile payload")


def extract_bpr_payloads(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html or "", "html.parser")
    payloads: list[dict[str, Any]] = []
    for code in soup.find_all("code"):
        cid = (code.get("id") or "").lower()
        if not (cid.startswith("bpr-guid") or "bpr-guid" in cid):
            continue
        raw = (code.string or code.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and (
            "included" in data or isinstance(data.get("data"), dict) or "elements" in data
        ):
            payloads.append(data)
    return payloads


def _looks_like_checkpoint(html: str) -> bool:
    snippet = (html or "")[:5000].lower()
    return any(
        token in snippet
        for token in ("/checkpoint/", "/uas/login", "authwall", "security verification")
    )
