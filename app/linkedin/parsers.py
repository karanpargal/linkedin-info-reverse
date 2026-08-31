from __future__ import annotations

from typing import Any

from app.models import (
    Certification,
    Education,
    Experience,
    Honor,
    Image,
    Language,
    Location,
    Profile,
    Project,
    Skill,
    Volunteer,
)

PROFILE_TYPE_SUFFIX = "identity.profile.Profile"
POSITION_TYPE_SUFFIX = "identity.profile.Position"
EDUCATION_TYPE_SUFFIX = "identity.profile.Education"
SKILL_TYPE_SUFFIX = "identity.profile.Skill"
CERT_TYPE_SUFFIX = "identity.profile.Certification"
LANG_TYPE_SUFFIX = "identity.profile.Language"
PROJECT_TYPE_SUFFIX = "identity.profile.Project"
VOLUNTEER_TYPE_SUFFIX = "identity.profile.VolunteerExperience"
HONOR_TYPE_SUFFIX = "identity.profile.Honor"
def type_suffix(entity: dict[str, Any]) -> str:
    return str(entity.get("$type") or "")


def is_type(entity: dict[str, Any], suffix: str) -> bool:
    t = type_suffix(entity)
    return t.endswith(suffix) or t.endswith("." + suffix)


def included_index(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for entity in collect_entities(body):
        urn = entity.get("entityUrn") or entity.get("urn")
        if isinstance(urn, str):
            index[urn] = entity
    return index


def collect_entities(body: dict[str, Any]) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    included = body.get("included")
    if isinstance(included, list):
        entities.extend(e for e in included if isinstance(e, dict))
    data = body.get("data")
    if isinstance(data, dict):
        elements = data.get("elements")
        if isinstance(elements, list):
            entities.extend(e for e in elements if isinstance(e, dict))
        elif data.get("$type") or data.get("entityUrn") or data.get("firstName"):
            entities.append(data)
    elements = body.get("elements")
    if isinstance(elements, list):
        entities.extend(e for e in elements if isinstance(e, dict))
    return entities


def resolve(index: dict[str, dict[str, Any]], ref: Any) -> dict[str, Any] | None:
    if isinstance(ref, dict):
        return ref
    if isinstance(ref, str):
        return index.get(ref)
    return None


def resolve_many(index: dict[str, dict[str, Any]], refs: Any) -> list[dict[str, Any]]:
    if not isinstance(refs, list):
        return []
    out: list[dict[str, Any]] = []
    for ref in refs:
        entity = resolve(index, ref)
        if entity:
            out.append(entity)
    return out


def localized(obj: dict[str, Any] | None, *keys: str) -> str | None:
    if not obj:
        return None
    for key in keys:
        val = obj.get(key)
        text = coerce_text(val)
        if text:
            return text
    return None


def coerce_text(val: Any) -> str | None:
    if isinstance(val, str):
        text = val.strip()
        return text or None
    if isinstance(val, dict):
        for loc in ("en_US", "en", "en_GB"):
            inner = val.get(loc)
            if isinstance(inner, str) and inner.strip():
                return inner.strip()
        if isinstance(val.get("text"), str) and val["text"].strip():
            return val["text"].strip()
        if isinstance(val.get("value"), str) and val["value"].strip():
            return val["value"].strip()
        for inner in val.values():
            if isinstance(inner, str) and inner.strip():
                return inner.strip()
    return None


def format_date(part: Any) -> str | None:
    if not isinstance(part, dict):
        return None
    year = part.get("year")
    month = part.get("month")
    if not year:
        return None
    if month:
        return f"{int(year):04d}-{int(month):02d}"
    return f"{int(year):04d}"


def extract_dates(entity: dict[str, Any]) -> tuple[str | None, str | None, bool]:
    period = entity.get("dateRange") or entity.get("timePeriod") or {}
    if not isinstance(period, dict):
        return None, None, False
    start = format_date(period.get("start") or period.get("startDate"))
    end_src = period.get("end") or period.get("endDate")
    end = format_date(end_src)
    is_current = end is None and start is not None
    if entity.get("timePeriod") and not period.get("endDate"):
        is_current = start is not None
    return start, end, is_current


def unwrap_vector_image(obj: Any) -> dict[str, Any] | None:
    if not isinstance(obj, dict):
        return None
    if obj.get("rootUrl") and obj.get("artifacts"):
        return obj
    nested = obj.get("com.linkedin.common.VectorImage")
    if isinstance(nested, dict):
        return unwrap_vector_image(nested)
    for key in (
        "vectorImage",
        "displayImage",
        "displayImageReference",
        "photo",
        "image",
        "croppedImage",
    ):
        if key in obj:
            found = unwrap_vector_image(obj[key])
            if found:
                return found
    return None


def build_image(obj: Any) -> Image | None:
    if isinstance(obj, str) and obj.startswith("http"):
        return Image(url=obj)
    if not isinstance(obj, dict):
        return None
    plain = obj.get("url") or obj.get("imageUrl")
    if isinstance(plain, str) and plain.startswith("http"):
        return Image(url=plain)
    if isinstance(plain, dict) and isinstance(plain.get("url"), str):
        return Image(url=plain["url"])
    vector = unwrap_vector_image(obj)
    if not vector:
        return None
    artifacts = [a for a in vector.get("artifacts") or [] if isinstance(a, dict)]
    if not artifacts:
        return None
    artifacts.sort(key=lambda a: int(a.get("width") or 0), reverse=True)
    best = artifacts[0]
    segment = best.get("fileIdentifyingUrlPathSegment") or ""
    root = vector.get("rootUrl") or ""
    if not root or not segment:
        return None
    expires = best.get("expiresAt")
    return Image(
        url=f"{root}{segment}",
        width=best.get("width"),
        height=best.get("height"),
        expires_at=int(expires) if isinstance(expires, (int, float)) else None,
    )


def ordered_of_type(
    body: dict[str, Any],
    index: dict[str, dict[str, Any]],
    suffix: str,
    profile: dict[str, Any] | None,
    pointer_keys: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    if profile:
        for key in pointer_keys:
            refs = profile.get(key) or profile.get(key.lstrip("*"))
            resolved = resolve_many(index, refs)
            if resolved:
                return [e for e in resolved if is_type(e, suffix) or True]
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    refs = data.get("*elements") if isinstance(data, dict) else None
    if isinstance(refs, list):
        ordered = [e for e in resolve_many(index, refs) if is_type(e, suffix)]
        if ordered:
            return ordered
    return [e for e in collect_entities(body) if is_type(e, suffix)]


def find_profile_entity(entities: list[dict[str, Any]]) -> dict[str, Any] | None:
    for entity in entities:
        t = type_suffix(entity)
        if t.endswith(PROFILE_TYPE_SUFFIX) and "Card" not in t and "Component" not in t:
            return entity
    for entity in entities:
        if entity.get("firstName") and entity.get("lastName") and entity.get("publicIdentifier"):
            return entity
    return None


def company_name(entity: dict[str, Any], index: dict[str, dict[str, Any]]) -> tuple[str | None, str | None]:
    name = localized(entity, "companyName", "companyNameV2", "multiLocaleCompanyName")
    company = resolve(index, entity.get("*company") or entity.get("company"))
    url = None
    if company:
        name = name or localized(company, "name", "multiLocaleName", "universalName")
        vanity = localized(company, "universalName", "url")
        if vanity and not str(vanity).startswith("http"):
            url = f"https://www.linkedin.com/company/{vanity}/"
        elif isinstance(company.get("url"), str):
            url = company["url"]
        elif isinstance(company.get("companyUrl"), str):
            url = company["companyUrl"]
    if isinstance(entity.get("companyUrn"), str) and not url:
        pass
    company_url = localized(entity, "companyUrl") or url
    return name, company_url


def parse_experience(entity: dict[str, Any], index: dict[str, dict[str, Any]]) -> Experience:
    start, end, is_current = extract_dates(entity)
    company, company_url = company_name(entity, index)
    return Experience(
        title=localized(entity, "title", "multiLocaleTitle"),
        company=company,
        company_url=company_url,
        location=localized(entity, "locationName", "geoLocationName", "multiLocaleGeoLocationName"),
        description=localized(entity, "description", "multiLocaleDescription"),
        start=start,
        end=end,
        is_current=is_current,
    )


def parse_education(entity: dict[str, Any], index: dict[str, dict[str, Any]]) -> Education:
    start, end, _ = extract_dates(entity)
    school = localized(entity, "schoolName", "multiLocaleSchoolName")
    school_ref = resolve(index, entity.get("*school") or entity.get("school"))
    if school_ref:
        school = school or localized(school_ref, "name", "multiLocaleName")
    return Education(
        school=school,
        degree=localized(entity, "degreeName", "degree", "multiLocaleDegreeName"),
        field=localized(entity, "fieldOfStudy", "multiLocaleFieldOfStudy"),
        start=start,
        end=end,
    )


def _issued_date(entity: dict[str, Any]) -> str | None:
    start, _, _ = extract_dates(entity)
    if start:
        return start
    return format_date(entity.get("issuedOn") or entity.get("issueDate"))


def parse_voyager_profile(body: dict[str, Any], *, public_id: str, url: str) -> Profile | None:
    entities = collect_entities(body)
    if not entities:
        return None
    index = included_index(body)
    profile = find_profile_entity(entities)
    if not profile:
        return None

    first = localized(profile, "firstName", "multiLocaleFirstName")
    last = localized(profile, "lastName", "multiLocaleLastName")
    full = localized(profile, "name") or " ".join(p for p in (first, last) if p) or None
    about = localized(profile, "summary", "about", "multiLocaleAbout", "multiLocaleSummary")
    location_name = localized(
        profile,
        "geoLocationName",
        "locationName",
        "multiLocaleGeoLocationName",
    )
    country = None
    geo = profile.get("geoLocation") or profile.get("location") or {}
    if isinstance(geo, dict):
        location_name = location_name or localized(
            geo, "defaultLocalizedName", "geoLocationName"
        )
        basic = geo.get("basicLocation") or geo.get("geo") or {}
        if isinstance(basic, dict):
            country = localized(basic, "countryCode", "country")
            location_name = location_name or localized(basic, "defaultLocalizedName")

    picture = build_image(
        profile.get("profilePicture")
        or profile.get("displayPicture")
        or profile.get("picture")
        or profile.get("miniProfile")
    )
    background = build_image(
        profile.get("backgroundImage")
        or profile.get("profileBackgroundImage")
        or profile.get("backgroundPicture")
    )

    experience = [
        parse_experience(e, index)
        for e in ordered_of_type(
            body,
            index,
            POSITION_TYPE_SUFFIX,
            profile,
            ("*profilePositionGroups", "*profilePositions", "*positions"),
        )
        if is_type(e, POSITION_TYPE_SUFFIX)
    ]
    # PositionGroups sometimes wrap positions
    if not experience:
        for group in [e for e in entities if is_type(e, "identity.profile.PositionGroup")]:
            for pos in resolve_many(index, group.get("*profilePositionInPositionGroup") or group.get("*positions")):
                if is_type(pos, POSITION_TYPE_SUFFIX):
                    experience.append(parse_experience(pos, index))

    education = [
        parse_education(e, index)
        for e in ordered_of_type(
            body, index, EDUCATION_TYPE_SUFFIX, profile, ("*profileEducations", "*educations")
        )
        if is_type(e, EDUCATION_TYPE_SUFFIX)
    ]
    skills = [
        Skill(name=name)
        for e in ordered_of_type(body, index, SKILL_TYPE_SUFFIX, profile, ("*profileSkills", "*skills"))
        if (name := localized(e, "name", "skillName", "multiLocaleName"))
    ]
    certifications = [
        Certification(
            name=localized(e, "name", "multiLocaleName"),
            authority=localized(e, "authority", "companyName", "multiLocaleAuthority"),
            issued=_issued_date(e),
        )
        for e in ordered_of_type(
            body, index, CERT_TYPE_SUFFIX, profile, ("*profileCertifications", "*certifications")
        )
        if is_type(e, CERT_TYPE_SUFFIX)
    ]
    languages = [
        Language(
            name=localized(e, "name", "multiLocaleName"),
            proficiency=localized(e, "proficiency", "proficiencyLevel"),
        )
        for e in ordered_of_type(
            body, index, LANG_TYPE_SUFFIX, profile, ("*profileLanguages", "*languages")
        )
        if is_type(e, LANG_TYPE_SUFFIX)
    ]
    projects = [
        Project(
            name=localized(e, "title", "name", "multiLocaleTitle"),
            description=localized(e, "description", "multiLocaleDescription"),
            start=extract_dates(e)[0],
            end=extract_dates(e)[1],
        )
        for e in ordered_of_type(body, index, PROJECT_TYPE_SUFFIX, profile, ("*profileProjects", "*projects"))
        if is_type(e, PROJECT_TYPE_SUFFIX)
    ]
    volunteer = [
        Volunteer(
            role=localized(e, "role", "title", "multiLocaleRole"),
            organization=localized(e, "companyName", "organizationName", "multiLocaleCompanyName"),
            description=localized(e, "description", "multiLocaleDescription"),
            start=extract_dates(e)[0],
            end=extract_dates(e)[1],
        )
        for e in ordered_of_type(
            body,
            index,
            VOLUNTEER_TYPE_SUFFIX,
            profile,
            ("*profileVolunteerExperiences", "*volunteerExperiences"),
        )
        if is_type(e, VOLUNTEER_TYPE_SUFFIX)
    ]
    honors = [
        Honor(
            title=localized(e, "title", "name", "multiLocaleTitle"),
            issuer=localized(e, "issuer", "occupation", "multiLocaleIssuer"),
            issued=format_date(e.get("issuedOn") or e.get("issueDate")),
        )
        for e in ordered_of_type(body, index, HONOR_TYPE_SUFFIX, profile, ("*profileHonors", "*honors"))
        if is_type(e, HONOR_TYPE_SUFFIX)
    ]

    resolved_id = localized(profile, "publicIdentifier") or public_id
    return Profile(
        source="voyager",
        url=url,
        public_id=resolved_id,
        urn=profile.get("entityUrn") or profile.get("dashEntityUrn"),
        first_name=first,
        last_name=last,
        full_name=full,
        headline=localized(profile, "headline", "multiLocaleHeadline", "occupation"),
        about=about,
        location=Location(name=location_name, country=country) if location_name or country else None,
        industry=localized(profile, "industry", "industryName", "multiLocaleIndustry"),
        profile_picture=picture,
        background_image=background,
        experience=experience,
        education=education,
        skills=skills,
        certifications=certifications,
        languages=languages,
        projects=projects,
        volunteer=volunteer,
        honors=honors,
    )
