import json
from pathlib import Path

from app.linkedin.guest import extract_person_from_html, person_to_profile
from app.linkedin.parsers import parse_voyager_profile

FIXTURE = Path(__file__).parent / "fixtures" / "voyager_profile.json"

GUEST_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "ProfilePage",
  "mainEntity": {
    "@type": "Person",
    "name": "Ada Lovelace",
    "jobTitle": "Mathematician",
    "description": "Notes on the Analytical Engine.",
    "url": "https://www.linkedin.com/in/ada-lovelace",
    "image": "https://media.licdn.com/dms/image/ada.jpg",
    "address": {"@type": "PostalAddress", "addressLocality": "London"},
    "worksFor": {"@type": "Organization", "name": "Analytical Engine Project"},
    "alumniOf": [{"@type": "Organization", "name": "Home education"}]
  }
}
</script>
</head><body></body></html>
"""


def test_parse_voyager_normalized_json() -> None:
    body = json.loads(FIXTURE.read_text())
    profile = parse_voyager_profile(
        body,
        public_id="ada-lovelace",
        url="https://www.linkedin.com/in/ada-lovelace/",
    )
    assert profile is not None
    assert profile.source == "voyager"
    assert profile.first_name == "Ada"
    assert profile.last_name == "Lovelace"
    assert profile.full_name == "Ada Lovelace"
    assert profile.headline.startswith("Mathematician")
    assert profile.about is not None
    assert profile.location and profile.location.name == "London, England"
    assert profile.industry == "Research"
    assert profile.urn == "urn:li:fsd_profile:ACoAAAExample"
    assert profile.profile_picture is not None
    assert profile.profile_picture.url.endswith("800_800/0/1?e=1&v=beta&t=large")
    assert profile.background_image is not None
    assert profile.background_image.url.endswith("1400_350/0/1?e=1&v=beta&t=bg")
    assert [e.title for e in profile.experience] == ["Collaborator", "Analyst"]
    assert profile.experience[0].is_current is True
    assert profile.experience[1].start == "1842-01"
    assert profile.experience[1].end == "1843-12"
    assert profile.education[0].school == "Home education"
    assert profile.education[0].field == "Mathematics"
    assert [s.name for s in profile.skills] == ["Mathematics", "Programming"]
    assert profile.certifications[0].authority == "Royal Society"
    assert profile.certifications[0].issued == "1843-06"
    assert profile.languages[0].name == "English"


def test_guest_json_ld_person() -> None:
    person = extract_person_from_html(GUEST_HTML)
    assert person is not None
    profile = person_to_profile(
        person,
        public_id="ada-lovelace",
        url="https://www.linkedin.com/in/ada-lovelace/",
    )
    assert profile.source == "guest"
    assert profile.full_name == "Ada Lovelace"
    assert profile.headline == "Mathematician"
    assert profile.about == "Notes on the Analytical Engine."
    assert profile.location and profile.location.name == "London"
    assert profile.profile_picture and profile.profile_picture.url.endswith("ada.jpg")
    assert profile.experience[0].company == "Analytical Engine Project"
    assert profile.education[0].school == "Home education"
    assert profile.skills == []
    assert profile.certifications == []
