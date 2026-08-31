from __future__ import annotations

import logging
from typing import Any

from app.linkedin.client import LinkedInClient, encode_member_identity
from app.linkedin.errors import VoyagerUnavailable
from app.linkedin.parsers import parse_voyager_profile
from app.linkedin.urls import canonical_profile_url
from app.models import Profile

logger = logging.getLogger(__name__)

DECORATION_PREFIX = "com.linkedin.voyager.dash.deco.identity.profile."
# Try current schema first; only walk neighbours on HTTP 400 (rotated version).
DECORATIONS = (
    f"{DECORATION_PREFIX}FullProfileWithEntities-96",
    f"{DECORATION_PREFIX}FullProfileWithEntities-93",
    f"{DECORATION_PREFIX}WebTopCardCore-16",
)


def fetch_voyager_profile(client: LinkedInClient, public_id: str) -> Profile:
    url = canonical_profile_url(public_id)
    last_error: Exception | None = None

    for decoration in DECORATIONS:
        try:
            body = _dash_profiles(client, public_id, decoration, referer=url)
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
        # 200 with an unexpected shape — do not fire extra Voyager calls; they burn the session.
        break

    if last_error:
        raise last_error
    raise VoyagerUnavailable("Could not load profile from Voyager")


def _dash_profiles(
    client: LinkedInClient, public_id: str, decoration: str, *, referer: str
) -> dict[str, Any]:
    query = (
        f"q=memberIdentity&memberIdentity={encode_member_identity(public_id)}"
        f"&decorationId={decoration}"
    )
    return client.voyager_get("/identity/dash/profiles", query, referer=referer)
