from __future__ import annotations

from urllib.parse import unquote, urlparse

PROFILE_HOSTS = {
    "linkedin.com",
    "www.linkedin.com",
    "m.linkedin.com",
    "mobile.linkedin.com",
}

REJECT_PREFIXES = (
    "/company/",
    "/school/",
    "/showcase/",
    "/jobs/",
    "/feed",
    "/posts/",
    "/pulse/",
    "/learning/",
    "/groups/",
    "/newsletters/",
)


class InvalidProfileUrl(ValueError):
    pass


def extract_public_id(url: str) -> str:
    """Return the vanity slug from a LinkedIn member profile URL."""
    raw = (url or "").strip()
    if not raw:
        raise InvalidProfileUrl("A LinkedIn profile URL is required")

    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host not in {h.removeprefix("www.") for h in PROFILE_HOSTS} and not host.endswith(
        ".linkedin.com"
    ):
        raise InvalidProfileUrl("URL must be a linkedin.com profile")

    path = unquote(parsed.path or "")
    parts = [p for p in path.split("/") if p]

    if parts and parts[0] in {"mwlite", "m"}:
        parts = parts[1:]

    # Optional locale prefix: /in/slug or /en/in/slug or /in/slug/en
    if len(parts) >= 2 and parts[0] == "in":
        slug = parts[1]
    elif len(parts) >= 3 and parts[1] == "in":
        slug = parts[2]
    else:
        joined = "/" + "/".join(parts)
        for prefix in REJECT_PREFIXES:
            if joined.startswith(prefix.rstrip("/")):
                raise InvalidProfileUrl("URL is not a member profile (expected /in/{slug})")
        raise InvalidProfileUrl("URL is not a member profile (expected /in/{slug})")

    slug = slug.strip()
    if not slug or slug.lower() in {"edit", "details", "overlay"}:
        raise InvalidProfileUrl("Could not parse a profile identifier from the URL")
    if slug.startswith("ACoAA") and len(slug) > 10:
        return slug
    return slug


def canonical_profile_url(public_id: str) -> str:
    return f"https://www.linkedin.com/in/{public_id}/"
