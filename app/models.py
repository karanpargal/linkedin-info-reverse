from typing import Literal

from pydantic import BaseModel, Field


class Location(BaseModel):
    name: str | None = None
    country: str | None = None


class Image(BaseModel):
    url: str
    width: int | None = None
    height: int | None = None
    expires_at: int | None = None


class Experience(BaseModel):
    title: str | None = None
    company: str | None = None
    company_url: str | None = None
    location: str | None = None
    description: str | None = None
    start: str | None = None
    end: str | None = None
    is_current: bool = False


class Education(BaseModel):
    school: str | None = None
    degree: str | None = None
    field: str | None = None
    start: str | None = None
    end: str | None = None


class Skill(BaseModel):
    name: str


class Certification(BaseModel):
    name: str | None = None
    authority: str | None = None
    issued: str | None = None


class Language(BaseModel):
    name: str | None = None
    proficiency: str | None = None


class Project(BaseModel):
    name: str | None = None
    description: str | None = None
    start: str | None = None
    end: str | None = None


class Volunteer(BaseModel):
    role: str | None = None
    organization: str | None = None
    description: str | None = None
    start: str | None = None
    end: str | None = None


class Honor(BaseModel):
    title: str | None = None
    issuer: str | None = None
    issued: str | None = None


class Profile(BaseModel):
    source: Literal["voyager", "guest"]
    url: str
    public_id: str
    urn: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    headline: str | None = None
    about: str | None = None
    location: Location | None = None
    industry: str | None = None
    profile_picture: Image | None = None
    background_image: Image | None = None
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    volunteer: list[Volunteer] = Field(default_factory=list)
    honors: list[Honor] = Field(default_factory=list)


class ProfileRequest(BaseModel):
    url: str


class VoyagerStatus(BaseModel):
    configured: bool
    session: Literal["live", "dead", "unknown", "unconfigured"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    voyager: VoyagerStatus
