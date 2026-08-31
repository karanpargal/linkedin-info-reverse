from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from app.linkedin.client import LinkedInClient, encode_member_identity
from app.linkedin.errors import ProfileNotFound, VoyagerUnavailable
from app.linkedin.parsers import parse_voyager_profile
from app.linkedin.urls import canonical_profile_url
from app.models import Profile

logger = logging.getLogger(__name__)

DECORATION_PREFIX = "com.linkedin.voyager.dash.deco.identity.profile."
DECORATIONS = (
    f"{DECORATION_PREFIX}FullProfileWithEntities-96",
    f"{DECORATION_PREFIX}FullProfileWithEntities-93",
    f"{DECORATION_PREFIX}FullProfileWithEntities-91",
    f"{DECORATION_PREFIX}FullProfileWithEntities-86",
    f"{DECORATION_PREFIX}WebTopCardCore-16",
)


def fetch_voyager_profile(client: LinkedInClient, public_id: str) -> Profile:
    url = canonical_profile_url(public_id)
    last_error: Exception | None = None

    for decoration in DECORATIONS:
        try:
            body = _dash_profiles(client, public_id, decoration)
        except VoyagerUnavailable as exc:
            if exc.status_code == 400:
                logger.info("Decoration %s rejected (400), trying next", decoration)
                last_error = exc
                continue
            raise
        profile = parse_voyager_profile(body, public_id=public_id, url=url)
        if profile:
            return profile
        last_error = VoyagerUnavailable("Dash profile response did not contain a Profile entity")

    try:
        body = _graphql_by_vanity(client, public_id)
        profile = parse_voyager_profile(body, public_id=public_id, url=url)
        if profile:
            return profile
    except (VoyagerUnavailable, ProfileNotFound) as exc:
        logger.info("GraphQL vanity resolve failed: %s", exc)
        last_error = exc

    try:
        body = _legacy_profile_view(client, public_id)
        profile = parse_voyager_profile(body, public_id=public_id, url=url)
        if profile:
            return profile
        profile = _parse_legacy_profile_view(body, public_id=public_id, url=url)
        if profile:
            return profile
    except VoyagerUnavailable as exc:
        logger.info("Legacy profileView failed: %s", exc)
        last_error = exc

    if last_error:
        raise last_error
    raise VoyagerUnavailable("Could not load profile from Voyager")


def _dash_profiles(client: LinkedInClient, public_id: str, decoration: str) -> dict[str, Any]:
    query = (
        f"q=memberIdentity&memberIdentity={encode_member_identity(public_id)}"
        f"&decorationId={decoration}"
    )
    return client.voyager_get("/identity/dash/profiles", query)


def _graphql_by_vanity(client: LinkedInClient, public_id: str) -> dict[str, Any]:
    # Parentheses stay literal; only the vanity value is encoded if needed.
    safe = quote(public_id, safe="")
    return client.graphql(
        variables=f"(vanityName:{safe})",
        query_name="voyagerIdentityDashProfiles",
    )


def _legacy_profile_view(client: LinkedInClient, public_id: str) -> dict[str, Any]:
    return client.voyager_get(f"/identity/profiles/{encode_member_identity(public_id)}/profileView")


def _parse_legacy_profile_view(body: dict[str, Any], *, public_id: str, url: str) -> Profile | None:
    """profileView used sibling *View collections instead of a flat included[]."""
    from app.linkedin.parsers import collect_entities, parse_voyager_profile

    wrapped = dict(body)
    extras: list[dict[str, Any]] = []
    for key, value in list(body.items()):
        if isinstance(value, dict) and isinstance(value.get("elements"), list):
            extras.extend(e for e in value["elements"] if isinstance(e, dict))
    if extras:
        included = list(wrapped.get("included") or [])
        included.extend(extras)
        wrapped["included"] = included
    profile = parse_voyager_profile(wrapped, public_id=public_id, url=url)
    if profile:
        return profile
    # Some payloads nest the person under `profile`
    person = body.get("profile")
    if isinstance(person, dict):
        synthetic = {"included": [person, *collect_entities(wrapped)]}
        return parse_voyager_profile(synthetic, public_id=public_id, url=url)
    return None
