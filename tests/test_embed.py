import json
from pathlib import Path

from app.linkedin.embed import extract_bpr_payloads
from app.linkedin.parsers import parse_voyager_profile

FIXTURE = Path(__file__).parent / "fixtures" / "voyager_profile.json"


def test_extract_bpr_guid_payload() -> None:
    body = json.loads(FIXTURE.read_text())
    html = f"""
    <html><body>
      <code id="datalet-bpr-guid-1">{{"request":"/voyager/api/identity/dash/profiles","status":200}}</code>
      <code id="bpr-guid-2">{json.dumps(body)}</code>
    </body></html>
    """
    payloads = extract_bpr_payloads(html)
    assert payloads
    profile = parse_voyager_profile(
        payloads[0],
        public_id="ada-lovelace",
        url="https://www.linkedin.com/in/ada-lovelace/",
    )
    assert profile is not None
    assert profile.full_name == "Ada Lovelace"
    assert profile.experience
