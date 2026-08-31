from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.config import Settings, get_settings
from app.linkedin.errors import LinkedInBlocked, ProfileNotFound, RateLimited, VoyagerUnavailable
from app.linkedin.service import ProfileService
from app.linkedin.urls import InvalidProfileUrl, canonical_profile_url, extract_public_id
from app.models import HealthResponse, Profile, ProfileRequest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="LinkedIn Profile API",
    description=(
        "Reverse-engineered LinkedIn profile lookup. Accepts a profile URL and returns "
        "structured JSON from Voyager (authenticated) or public JSON-LD (guest fallback)."
    ),
    version="1.0.0",
)


@lru_cache
def get_service() -> ProfileService:
    return ProfileService(get_settings())


def require_api_key(
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health", response_model=HealthResponse)
def health(service: ProfileService = Depends(get_service)) -> HealthResponse:
    return HealthResponse(status="ok", voyager=service.health())


@app.get("/v1/profile", response_model=Profile, dependencies=[Depends(require_api_key)])
def get_profile(
    url: str = Query(..., description="LinkedIn profile URL, e.g. https://www.linkedin.com/in/slug"),
    service: ProfileService = Depends(get_service),
) -> Profile:
    return _lookup(url, service)


@app.post("/v1/profile", response_model=Profile, dependencies=[Depends(require_api_key)])
def post_profile(
    body: ProfileRequest,
    service: ProfileService = Depends(get_service),
) -> Profile:
    return _lookup(body.url, service)


def _lookup(url: str, service: ProfileService) -> Profile:
    try:
        public_id = extract_public_id(url)
    except InvalidProfileUrl as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        profile = service.get_profile(public_id)
    except ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except LinkedInBlocked as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except VoyagerUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not profile.url:
        profile.url = canonical_profile_url(public_id)
    return profile
