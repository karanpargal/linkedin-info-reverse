from __future__ import annotations

import logging
import time

from app.config import Settings
from app.linkedin.client import LinkedInClient
from app.linkedin.embed import fetch_embedded_voyager_profile
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
        self._cache: dict[str, tuple[float, Profile]] = {}
        self._health: tuple[float, VoyagerStatus] | None = None
        if self.client.configured:
            self.client.warmup()

    def health(self) -> VoyagerStatus:
        if not self.client.configured:
            return VoyagerStatus(configured=False, session="unconfigured")
        now = time.monotonic()
        if self._health and now - self._health[0] < 120:
            return self._health[1]
        try:
            live = self.client.probe_session()
        except Exception:
            status = VoyagerStatus(configured=True, session="unknown")
        else:
            status = VoyagerStatus(configured=True, session="live" if live else "dead")
        self._health = (now, status)
        return status

    def get_profile(self, public_id: str) -> Profile:
        cached = self._from_cache(public_id)
        if cached:
            return cached
        self.limiter.acquire()
        try:
            profile = self._resolve(public_id)
        finally:
            self.limiter.release()
        self._to_cache(public_id, profile)
        return profile

    def _from_cache(self, public_id: str) -> Profile | None:
        hit = self._cache.get(public_id)
        if not hit:
            return None
        stored_at, profile = hit
        if time.monotonic() - stored_at > float(self.settings.linkedin_cache_ttl):
            self._cache.pop(public_id, None)
            return None
        logger.info("Cache hit for %s", public_id)
        return profile.model_copy()

    def _to_cache(self, public_id: str, profile: Profile) -> None:
        self._cache[public_id] = (time.monotonic(), profile)

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
                logger.warning("Voyager REST failed (%s); trying embedded payload", exc)
                voyager_error = exc
            try:
                return fetch_embedded_voyager_profile(self.client, public_id)
            except ProfileNotFound:
                raise
            except RateLimited:
                raise
            except (SessionDead, LinkedInBlocked, VoyagerUnavailable) as exc:
                logger.warning("Embedded Voyager HTML failed (%s)", exc)
                voyager_error = voyager_error or exc

            # Do not call the anonymous guest path after a challenge — HTTP 999
            # from that extra traffic makes the restriction last longer.
            if isinstance(voyager_error, (LinkedInBlocked, SessionDead)):
                raise LinkedInBlocked(
                    "LinkedIn challenged or redirected the Voyager session. "
                    "Open https://www.linkedin.com/feed/, pass any security check, "
                    "then recopy li_at, JSESSIONID, bcookie, bscookie, lidc and dfpfpt "
                    "from that same tab. Wait a few minutes before the next lookup. "
                    f"Detail: {voyager_error}"
                ) from voyager_error
        else:
            logger.info("Voyager cookies not configured; using guest path")

        try:
            return fetch_guest_profile(public_id)
        except ProfileNotFound:
            raise
        except RateLimited:
            raise
        except (SessionDead, LinkedInBlocked, VoyagerUnavailable) as guest_error:
            voyager_reason = str(voyager_error) if voyager_error else "not attempted"
            guest_reason = str(guest_error)
            logger.warning("Both paths failed: voyager=%s guest=%s", voyager_reason, guest_reason)
            if isinstance(guest_error, (LinkedInBlocked, SessionDead)) or isinstance(
                voyager_error, LinkedInBlocked
            ):
                raise LinkedInBlocked(
                    "LinkedIn blocked the request. Voyager: "
                    f"{voyager_reason}. Guest: {guest_reason}. "
                    "If /health shows session=dead, open linkedin.com/feed, "
                    "complete any security check, recopy li_at, JSESSIONID, bcookie and lidc."
                ) from guest_error
            raise VoyagerUnavailable(
                "Voyager session is unavailable and the public profile fallback failed. "
                f"Voyager: {voyager_reason}. Guest: {guest_reason}."
            ) from guest_error
