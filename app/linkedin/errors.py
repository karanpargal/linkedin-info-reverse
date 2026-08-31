from __future__ import annotations


class LinkedInError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class SessionDead(LinkedInError):
    pass


class RateLimited(LinkedInError):
    pass


class ProfileNotFound(LinkedInError):
    pass


class LinkedInBlocked(LinkedInError):
    pass


class VoyagerUnavailable(LinkedInError):
    pass
