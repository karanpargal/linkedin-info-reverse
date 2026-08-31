import pytest

from app.linkedin.urls import InvalidProfileUrl, extract_public_id


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.linkedin.com/in/williamhgates", "williamhgates"),
        ("https://www.linkedin.com/in/williamhgates/", "williamhgates"),
        ("http://linkedin.com/in/williamhgates?trk=people", "williamhgates"),
        ("https://www.linkedin.com/in/williamhgates/overlay/contact-info/", "williamhgates"),
        ("https://www.linkedin.com/in/williamhgates/en", "williamhgates"),
        ("www.linkedin.com/in/ada-lovelace", "ada-lovelace"),
        ("https://www.linkedin.com/mwlite/in/satyanadella", "satyanadella"),
        ("https://de.linkedin.com/in/someone", "someone"),
    ],
)
def test_extract_public_id(url: str, expected: str) -> None:
    assert extract_public_id(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https://example.com/in/foo",
        "https://www.linkedin.com/company/google",
        "https://www.linkedin.com/school/mit",
        "https://www.linkedin.com/feed/",
        "https://www.linkedin.com/jobs/view/123",
        "not a url",
    ],
)
def test_reject_non_profile_urls(url: str) -> None:
    with pytest.raises(InvalidProfileUrl):
        extract_public_id(url)
