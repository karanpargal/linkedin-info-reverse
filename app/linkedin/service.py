from __future__ import annotations

import logging

from app.config import Settings
from app.linkedin.client import LinkedInClient
from app.linkedin.errors import (
    LinkedInBlocked,
    ProfileNotFound,
    RateLimited,
    SessionDead,
    VoyagerUnavailable,
)
from app.linkedin.guest import fetch_guest_profile
from app.linkedin.limiter import InProcessLimiter
from app.linkedin.voyager import fetch_voyager_profile
from app.models import Profile, VoyagerStatus

logger = logging.getLogger(__name__)


class ProfileService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = LinkedInClient(settings)
        self.limiter = InProcessLimiter()

    def health(self) -> VoyagerStatus:
        if not self.client.configured:
            return VoyagerStatus(configured=False, session="unconfigured")
        try:
            live = self.client.probe_session()
        except Exception:
            return VoyagerStatus(configured=True, session="unknown")
        return VoyagerStatus(configured=True, session="live" if live else "dead")

    def get_profile(self, public_id: str) -> Profile:
        self.limiter.acquire()
        try:
            return self._resolve(public_id)
        finally:
            self.limiter.release()

    def _resolve(self, public_id: str) -> Profile:
        voyager_error: Exception | None = None
        if self.client.configured:
            try:
                return fetch_voyager_profile(self.client, public_id)
            except ProfileNotFound:
                raise
            except RateLimited:
                raise
            except (SessionDead, LinkedInBlocked, VoyagerUnavailable) as exc:
                logger.warning("Voyager path failed (%s); trying guest fallback", exc)
                voyager_error = exc
        else:
            logger.info("Voyager cookies not configured; using guest path")

        try:
            return fetch_guest_profile(public_id)
        except ProfileNotFound:
            raise
        except RateLimited:
            raise
        except (SessionDead, LinkedInBlocked, VoyagerUnavailable) as guest_error:
            if isinstance(guest_error, (LinkedInBlocked, SessionDead)) or isinstance(
                voyager_error, LinkedInBlocked
            ):
                raise LinkedInBlocked(
                    "LinkedIn blocked both the Voyager and public profile paths"
                ) from guest_error
            raise VoyagerUnavailable(
                "Voyager session is unavailable and the public profile fallback failed"
            ) from guest_error
