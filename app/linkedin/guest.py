from __future__ import annotations

import json
import logging
import time
from typing import Any

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from app.linkedin.errors import (
    LinkedInBlocked,
    ProfileNotFound,
    RateLimited,
    SessionDead,
    VoyagerUnavailable,
)
from app.linkedin.urls import canonical_profile_url
from app.models import Education, Experience, Image, Location, Profile

logger = logging.getLogger(__name__)


def fetch_guest_profile(public_id: str) -> Profile:
    url = canonical_profile_url(public_id)
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            html, final_url = _get_public_html(url)
        except (LinkedInBlocked, VoyagerUnavailable) as exc:
            last_error = exc
            logger.info("Guest fetch attempt %s failed: %s", attempt + 1, exc)
            time.sleep(0.8 * (attempt + 1))
            continue
        if _is_authwall(html, final_url):
            last_error = SessionDead("LinkedIn served an authwall for the public profile page")
            logger.info("Guest fetch attempt %s hit authwall", attempt + 1)
            time.sleep(0.8 * (attempt + 1))
            continue
        person = extract_person_from_html(html)
        if person:
            return person_to_profile(person, public_id=public_id, url=url)
        last_error = VoyagerUnavailable("Public profile HTML did not contain JSON-LD Person data")
        logger.info("Guest fetch attempt %s had no JSON-LD Person", attempt + 1)
        time.sleep(0.8 * (attempt + 1))
    if last_error:
        raise last_error
    raise VoyagerUnavailable("Public profile HTML did not contain JSON-LD Person data")


def _get_public_html(url: str) -> tuple[str, str]:
    session = cffi_requests.Session(impersonate="chrome")
    try:
        response = session.get(
            url,
            headers={
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "accept-language": "en-US,en;q=0.9",
            },
            allow_redirects=True,
            timeout=25.0,
        )
    except cffi_requests.RequestsError as exc:
        raise VoyagerUnavailable(f"Public profile request failed: {exc}") from exc

    if response.status_code == 999:
        raise LinkedInBlocked("LinkedIn denied the public profile request (HTTP 999)", 999)
    if response.status_code == 404:
        raise ProfileNotFound("Profile not found", 404)
    if response.status_code == 429:
        raise RateLimited("LinkedIn rate-limited the public profile request", 429)
    if response.status_code >= 400:
        raise VoyagerUnavailable(
            f"Public profile request failed with HTTP {response.status_code}",
            response.status_code,
        )
    return response.text, str(response.url or url)


def _is_authwall(html: str, final_url: str) -> bool:
    lowered = (final_url or "").lower()
    if "/authwall" in lowered or "/uas/login" in lowered or "/checkpoint" in lowered:
        return True
    snippet = html[:4000].lower()
    return "authwall" in snippet and "sign in" in snippet


def extract_person_from_html(html: str) -> dict[str, Any] | None:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        person = _find_person(data)
        if person:
            return person
    return None


def _find_person(data: Any) -> dict[str, Any] | None:
    nodes: list[Any]
    if isinstance(data, list):
        nodes = data
    elif isinstance(data, dict) and isinstance(data.get("@graph"), list):
        nodes = data["@graph"]
    else:
        nodes = [data]
    for node in nodes:
        if not isinstance(node, dict):
            continue
        types = node.get("@type")
        type_list = types if isinstance(types, list) else [types]
        if "Person" in type_list:
            return node
        if "ProfilePage" in type_list and isinstance(node.get("mainEntity"), dict):
            main = node["mainEntity"]
            main_types = main.get("@type")
            main_list = main_types if isinstance(main_types, list) else [main_types]
            if "Person" in main_list:
                return main
            return main
    return None


def person_to_profile(person: dict[str, Any], *, public_id: str, url: str) -> Profile:
    name = _text(person.get("name"))
    first, last = _split_name(name)
    headline = _text(person.get("jobTitle")) or _text(person.get("description"))
    about = _text(person.get("description"))
    if about and headline and about == headline:
        about = None

    address = person.get("address") if isinstance(person.get("address"), dict) else {}
    location_name = _text(address.get("addressLocality")) or _text(address.get("name"))
    country = _text(address.get("addressCountry"))

    image = None
    raw_image = person.get("image")
    if isinstance(raw_image, str):
        image = Image(url=raw_image)
    elif isinstance(raw_image, dict) and isinstance(raw_image.get("url"), str):
        image = Image(url=raw_image["url"])
    elif isinstance(raw_image, list) and raw_image:
        first_img = raw_image[0]
        if isinstance(first_img, str):
            image = Image(url=first_img)
        elif isinstance(first_img, dict) and isinstance(first_img.get("url"), str):
            image = Image(url=first_img["url"])

    experience = [_org_to_experience(item) for item in _as_list(person.get("worksFor"))]
    experience = [e for e in experience if e.company or e.title]
    education = [_org_to_education(item) for item in _as_list(person.get("alumniOf"))]
    education = [e for e in education if e.school]

    return Profile(
        source="guest",
        url=_text(person.get("url")) or url,
        public_id=public_id,
        first_name=first,
        last_name=last,
        full_name=name,
        headline=headline,
        about=about,
        location=Location(name=location_name, country=country) if location_name or country else None,
        profile_picture=image,
        experience=experience,
        education=education,
    )


def _org_to_experience(item: Any) -> Experience:
    if isinstance(item, str):
        return Experience(company=item)
    if not isinstance(item, dict):
        return Experience()
    return Experience(
        title=_text(item.get("jobTitle")) or _text(item.get("description")),
        company=_text(item.get("name")),
        company_url=_text(item.get("url")),
        location=_text(item.get("address")),
    )


def _org_to_education(item: Any) -> Education:
    if isinstance(item, str):
        return Education(school=item)
    if not isinstance(item, dict):
        return Education()
    return Education(school=_text(item.get("name")))


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        return _text(value.get("name") or value.get("text") or value.get("value"))
    return None


def _split_name(name: str | None) -> tuple[str | None, str | None]:
    if not name:
        return None, None
    parts = name.split()
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])
